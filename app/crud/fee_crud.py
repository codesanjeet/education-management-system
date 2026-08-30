import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from sqlalchemy.orm import selectinload
from ..crud.class_crud import get_all_class
from ..models.fee_model import (
    FeeStructureDB, InvoiceDB, InvoiceItemDB,
    PaymentDB, DiscountDB, FineDB, RefundDB, InvoiceStatus
)
from ..models.institution_model import InstitutionDB
from ..models.classes_model import ClassDB
from ..models.user_model import UserDB
from ..models.role_specific.student_model import StudentDB
from ..core.exceptions import (
    DatabaseError, InstitutionNotFoundError, ClassNotFoundError,DuplicateFeeStructureError,BadRequestError,
    NotFoundError
)
from ..schemas.fee_schema import (
    FeeStructureCreate, FeeStructureUpdate,
    InvoiceCreate, PaymentCreate,
    DiscountCreate, DiscountUpdate,
    FineCreate, RefundCreate,
    BillingSettingsUpdate,
    InvoiceStudentInfo, PaymentStudentInfo,MONTH_NAMES
)
import logging

logger = logging.getLogger(__name__)

_ALLOWED_DISCOUNT_FIELDS = frozenset({
    "title", "reason", "discount_type",
    "value", "start_date", "end_date", "is_active"
})
# ==================================================
# HELPERS
# ==================================================

def _generate_invoice_number(tenant_id: str) -> str:
    prefix = tenant_id[:4].upper()
    uid = uuid.uuid4().hex[:8].upper()
    return f"INV-{prefix}-{uid}"


def _generate_receipt_number(tenant_id: str) -> str:
    prefix = tenant_id[:4].upper()
    uid = uuid.uuid4().hex[:8].upper()
    return f"RCP-{prefix}-{uid}"


def _recalculate_invoice(invoice: InvoiceDB) -> None:
    """Recalculate invoice totals from items, discounts, fines, and payments."""
    subtotal = sum(item.total for item in invoice.items)
    fine_total = sum(fine.amount for fine in invoice.fines)
    paid_total = sum(
        p.amount_paid for p in invoice.payments if p.payment_status == "SUCCESS"
    )

    invoice.subtotal = subtotal
    invoice.fine_total = fine_total
    invoice.paid_total = paid_total
    invoice.grand_total = subtotal - invoice.discount_total + fine_total
    invoice.balance_due = invoice.grand_total - paid_total

    if invoice.balance_due <= 0:
        invoice.status = InvoiceStatus.PAID
    elif invoice.paid_total > 0:
        invoice.status = InvoiceStatus.PARTIAL
    elif invoice.due_date and invoice.due_date < datetime.utcnow():
        invoice.status = InvoiceStatus.OVERDUE
    else:
        invoice.status = InvoiceStatus.UNPAID


async def _build_student_info(db: AsyncSession, user_id: int) -> InvoiceStudentInfo | None:
    """Fetch and build embedded student info for a given user_id, including class display name and parent info."""
    try:
        result = await db.execute(
            select(UserDB, StudentDB, ClassDB)
            .join(StudentDB, StudentDB.user_id == UserDB.id)
            .join(ClassDB, ClassDB.class_code == StudentDB.class_code)
            .where(UserDB.id == user_id)
        )
        row = result.one_or_none()
        if not row:
            return None
        user, student, cls = row

        # Build a human-readable class label e.g. "Class 10 – A"
        if cls:
            class_display_name = cls.class_or_year_or_name
            if cls.section:
                class_display_name += f" – {cls.section}"
            if cls.batch:
                class_display_name += f" ({cls.batch})"
        else:
            class_display_name = student.class_code  # fallback

        return InvoiceStudentInfo(
            user_id=user.id,
            full_name=f"{user.first_name} {user.last_name}".strip(),
            email=user.email,
            roll_number=student.roll_number,
            class_code=student.class_code,
            class_display_name=class_display_name,
            contact_num=user.contact_num,
            profile_image={
            "thumb": f"/api/institutions/users/{user.id}/profile-image?type=thumb",
            "main": f"/api/institutions/users/{user.id}/profile-image?type=main"
        },
            father_name=student.father_name,
            mother_name=student.mother_name,
            guardian_name=student.guardian_name,
            guardian_contact_num=student.guardian_contact_num,
        )
    except Exception as e:
        logger.error(
            f"Failed to build student info for user_id={user_id}: {e}",
            exc_info=True
        )
        return None


async def _build_payment_student_info(db: AsyncSession, user_id: int) -> PaymentStudentInfo | None:
    try:
        result = await db.execute(
            select(UserDB, StudentDB)
            .join(StudentDB, StudentDB.user_id == UserDB.id)
            .where(UserDB.id == user_id)
        )
        row = result.one_or_none()
        if not row:
            return None
        user, student = row
        return PaymentStudentInfo(
            user_id=user.id,
            full_name=f"{user.first_name} {user.last_name}".strip(),
            email=user.email,
            roll_number=student.roll_number,
            class_code=student.class_code,
        )
    except Exception as e:
        logger.error(
            f"Failed to build payment student info for user_id={user_id}: {e}",
            exc_info=True
        )
        return None


async def _resolve_invoice_number(
    db: AsyncSession, institution_id: int, invoice_number: str
) -> int:
    result = await db.execute(
        select(InvoiceDB.id).where(
            InvoiceDB.invoice_number == invoice_number,
            InvoiceDB.institution_id == institution_id,
        )
    )
    internal_id = result.scalar_one_or_none()
    if not internal_id:
        from ..core.exceptions import NotFoundError
        raise NotFoundError("Invoice not found")
    return internal_id


async def _resolve_receipt_number(
    db: AsyncSession, institution_id: int, receipt_number: str
) -> int:
    result = await db.execute(
        select(PaymentDB.id).where(
            PaymentDB.receipt_number == receipt_number,
            PaymentDB.institution_id == institution_id,
        )
    )
    internal_id = result.scalar_one_or_none()
    if not internal_id:
        from ..core.exceptions import NotFoundError
        raise NotFoundError("Payment not found")
    return internal_id


# ==================================================
# BILLING SETTINGS
# ==================================================

async def get_billing_settings(
    db: AsyncSession,
    institution_id: int,
) -> dict:
    result = await db.execute(
        select(InstitutionDB.billing_day, InstitutionDB.due_day).where(
            InstitutionDB.id == institution_id
        )
    )
    row = result.one_or_none()
    if not row:
        return {"billing_day": 25, "due_day": 5}
    return {"billing_day": row.billing_day or 25, "due_day": row.due_day or 5}


async def update_billing_settings(
    db: AsyncSession,
    institution_id: int,
    data: BillingSettingsUpdate,
) -> dict:
    result = await db.execute(
        select(InstitutionDB).where(InstitutionDB.id == institution_id)
    )
    institution = result.scalar_one_or_none()
    if not institution:
        raise InstitutionNotFoundError("Institution not found")

    if data.billing_day is not None:
        institution.billing_day = data.billing_day
    if data.due_day is not None:
        institution.due_day = data.due_day

    try:
        await db.commit()
        await db.refresh(institution)
        return {
            "billing_day": institution.billing_day,
            "due_day": institution.due_day,
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating billing settings: {e}", exc_info=True)
        raise DatabaseError("Failed to update billing settings")


# ==================================================
# FEE STRUCTURE CRUD
# ==================================================

async def get_fee_structure_by_id(
    db: AsyncSession,
    institution_id: int,
    fee_structure_id: int
) -> FeeStructureDB:
    result = await db.execute(
        select(FeeStructureDB).where(
            FeeStructureDB.id == fee_structure_id,
            FeeStructureDB.institution_id == institution_id
        )
    )
    fee_structure = result.scalar_one_or_none()
    if not fee_structure:
        from ..core.exceptions import NotFoundError
        raise NotFoundError(f"Fee structure not found")
    return fee_structure


async def create_fee_structure(
    db: AsyncSession,
    tenant_id: str,
    institution_id: int,
    data: FeeStructureCreate,
) -> list:
    """
    Duplicate = same name + class + any overlapping month in same academic year.
    """
    try:
        structure_json = {
            "items": [{"name": i.name, "amount": float(i.amount)} for i in data.items]
        }
        months = sorted(set(data.applicable_months))

        if data.apply_to_all:
            all_classes = await get_all_class(db=db, tenant_id=tenant_id)
            active_classes = [c for c in all_classes if c.is_active]
            if not active_classes:
                raise ClassNotFoundError("No active classes found")

     
            class_codes = [c.class_code for c in active_classes]
            rows = await db.execute(
                select(ClassDB.id, ClassDB.class_code)
                .where(ClassDB.class_code.in_(class_codes))
            )
            code_to_id: dict[str, int] = {row.class_code: row.id for row in rows}

            # Duplicate check: same name + academic_year + same class
            # then check if any month overlaps in Python (JSONB overlap)
            existing_rows = await db.execute(
                select(FeeStructureDB.class_id, FeeStructureDB.applicable_months)
                .where(
                    FeeStructureDB.institution_id == institution_id,
                    FeeStructureDB.name == data.name,
                    FeeStructureDB.academic_year == data.academic_year,
                    FeeStructureDB.is_active == True,
                    FeeStructureDB.class_id.in_(list(code_to_id.values())),
                )
            )
            # Build map: class_id → set of already-used months
            class_used_months: dict[int, set] = {}
            for row in existing_rows:
                class_used_months[row.class_id] = set(row.applicable_months or [])

            created, skipped = [], []

            for cls in active_classes:
                class_id = code_to_id.get(cls.class_code)
                if not class_id:
                    logger.warning(f"class_id not found for {cls.class_code}, skipping")
                    continue

                used = class_used_months.get(class_id, set())
                overlap = used & set(months)
                if overlap:
                    month_names = [MONTH_NAMES[m] for m in sorted(overlap)]
                    logger.warning(
                        f"Fee '{data.name}' already has months {month_names} "
                        f"for class '{cls.class_code}' in {data.academic_year}, skipping"
                    )
                    skipped.append(cls.class_code)
                    continue

                fee_structure = FeeStructureDB(
                    institution_id=institution_id,
                    class_id=class_id,
                    name=data.name,
                    academic_year=data.academic_year,
                    applicable_months=months,
                    currency=data.currency,
                    description=data.description,
                    structure_json=structure_json,
                )
                db.add(fee_structure)
                created.append(fee_structure)

            if not created:
                overlap_names = [MONTH_NAMES[m] for m in months]
                raise DuplicateFeeStructureError(
                    f"Fee '{data.name}' already exists for all active classes "
                    f"in months: {', '.join(overlap_names)} ({data.academic_year})"
                )

            await db.commit()
            for fs in created:
                await db.refresh(fs)
            if skipped:
                logger.info(f"Skipped fee structure for classes: {skipped}")
            return created

        else:
            result = await db.execute(
                select(ClassDB.id).where(ClassDB.class_code == data.class_code)
            )
            class_id = result.scalar_one_or_none()
            if not class_id:
                raise ClassNotFoundError("Class does not exist")

            #  Single class duplicate check — any month overlap
            existing_rows = await db.execute(
                select(FeeStructureDB.applicable_months).where(
                    FeeStructureDB.institution_id == institution_id,
                    FeeStructureDB.class_id == class_id,
                    FeeStructureDB.name == data.name,
                    FeeStructureDB.academic_year == data.academic_year,
                    FeeStructureDB.is_active == True,
                )
            )
            used_months: set[int] = set()
            for row in existing_rows:
                used_months.update(row.applicable_months or [])

            overlap = used_months & set(months)
            if overlap:
                overlap_names = [MONTH_NAMES[m] for m in sorted(overlap)]
                raise DuplicateFeeStructureError(
                    f"Fee '{data.name}' already exists for class '{data.class_code}' "
                    f"in months: {', '.join(overlap_names)} ({data.academic_year}). "
                    f"Choose different months or a different name."
                )

            fee_structure = FeeStructureDB(
                institution_id=institution_id,
                class_id=class_id,
                name=data.name,
                academic_year=data.academic_year,
                applicable_months=months,
                currency=data.currency,
                description=data.description,
                structure_json=structure_json,
            )
            db.add(fee_structure)
            await db.commit()
            await db.refresh(fee_structure)
            return [fee_structure]

    except (ClassNotFoundError, DuplicateFeeStructureError):
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating fee structure: {e}", exc_info=True)
        raise DatabaseError("Failed to create fee structure")


async def get_fee_structures(
    db: AsyncSession,
    institution_id: int,
    class_code: str | None = None,
    month: int | None = None,        # ← filter by specific month
    academic_year: str | None = None,
) -> list[FeeStructureDB]:

    query = select(FeeStructureDB).where(
        FeeStructureDB.institution_id == institution_id,
        FeeStructureDB.is_active == True,
    )

    if class_code:
        class_id_q = await db.execute(
            select(ClassDB.id).where(ClassDB.class_code == class_code)
        )
        class_id = class_id_q.scalar_one_or_none()
        if not class_id:
            raise ClassNotFoundError("Class does not exist")
        query = query.where(FeeStructureDB.class_id == class_id)

    if academic_year:
        query = query.where(FeeStructureDB.academic_year == academic_year)

    #  Filter: only structures that include this month
    # PostgreSQL JSONB contains operator: applicable_months @> '[month]'
    if month is not None:
        query = query.where(
            FeeStructureDB.applicable_months.contains([month])
        )

    result = await db.execute(query)
    return result.scalars().all()


async def update_fee_structure(
    db: AsyncSession,
    institution_id: int,
    fee_structure_id: int,
    data: FeeStructureUpdate,
) -> FeeStructureDB:
    fee_structure = await get_fee_structure_by_id(db, institution_id, fee_structure_id)

    #If months are being updated, check for overlap with other records
    if data.applicable_months is not None:
        new_months = set(data.applicable_months)
        existing_rows = await db.execute(
            select(FeeStructureDB.applicable_months).where(
                FeeStructureDB.institution_id == institution_id,
                FeeStructureDB.class_id == fee_structure.class_id,
                FeeStructureDB.name == fee_structure.name,
                FeeStructureDB.academic_year == fee_structure.academic_year,
                FeeStructureDB.is_active == True,
                FeeStructureDB.id != fee_structure_id,   # exclude self
            )
        )
        used_months: set[int] = set()
        for row in existing_rows:
            used_months.update(row.applicable_months or [])

        overlap = used_months & new_months
        if overlap:
            overlap_names = [MONTH_NAMES[m] for m in sorted(overlap)]
            raise DuplicateFeeStructureError(
                f"Months {', '.join(overlap_names)} already exist in another "
                f"'{fee_structure.name}' structure for this class in {fee_structure.academic_year}"
            )
        fee_structure.applicable_months = sorted(new_months)

    if data.name          is not None: fee_structure.name          = data.name
    if data.academic_year is not None: fee_structure.academic_year = data.academic_year
    if data.description   is not None: fee_structure.description   = data.description
    if data.is_active     is not None: fee_structure.is_active     = data.is_active
    if data.items         is not None:
        fee_structure.structure_json = {
            "items": [{"name": i.name, "amount": float(i.amount)} for i in data.items]
        }

    try:
        await db.commit()
        await db.refresh(fee_structure)
        return fee_structure
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating fee structure: {e}", exc_info=True)
        raise DatabaseError("Failed to update fee structure")

async def delete_fee_structure(
    db: AsyncSession,
    institution_id: int,
    fee_structure_id: int
) -> dict:
    fee_structure = await get_fee_structure_by_id(db, institution_id, fee_structure_id)
    fee_structure.is_active = False
    try:
        await db.commit()
        return {"message": "Fee structure deactivated successfully", "id": fee_structure_id}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deactivating fee structure: {e}", exc_info=True)
        raise DatabaseError("Failed to deactivate fee structure")


# ==================================================
# INVOICE CRUD
# ==================================================

async def create_invoice(
    db: AsyncSession,
    institution_id: int,
    tenant_id: str,
    data: InvoiceCreate
) -> InvoiceDB:
    try:
        items = []
        subtotal = Decimal("0.00")

        for item_data in data.items:
            total = item_data.unit_amount * item_data.quantity
            subtotal += total
            items.append(
                InvoiceItemDB(
                    item_name=item_data.item_name,
                    description=item_data.description,
                    quantity=item_data.quantity,
                    unit_amount=item_data.unit_amount,
                    total=total
                )
            )

        # Auto-apply best active discount
        now = datetime.utcnow()
        discount_result = await db.execute(
            select(DiscountDB).where(
                DiscountDB.institution_id == institution_id,
                DiscountDB.student_user_id == data.student_user_id,
                DiscountDB.is_active == True,
            ).where(
                (DiscountDB.end_date == None) | (DiscountDB.end_date >= now)
            ).where(
                (DiscountDB.start_date == None) | (DiscountDB.start_date <= now)
            )
        )
        active_discounts = discount_result.scalars().all()

        discount_total = Decimal("0.00")
        if active_discounts:
            best_discount_amount = Decimal("0.00")
            for d in active_discounts:
                if d.discount_type == "PERCENTAGE":
                    amount = (subtotal * d.value / 100).quantize(Decimal("0.01"))
                else:
                    amount = min(Decimal(str(d.value)), subtotal)
                if amount > best_discount_amount:
                    best_discount_amount = amount
            discount_total = best_discount_amount

        grand_total = subtotal - discount_total
        balance_due = grand_total

        invoice = InvoiceDB(
            institution_id=institution_id,
            student_user_id=data.student_user_id,
            fee_structure_id=data.fee_structure_id,
            invoice_number=_generate_invoice_number(tenant_id),
            due_date=data.due_date,
            notes=data.notes,
            subtotal=subtotal,
            discount_total=discount_total,
            grand_total=grand_total,
            balance_due=balance_due
        )

        db.add(invoice)
        await db.flush()

        for item in items:
            item.invoice_id = invoice.id
            db.add(item)

        await db.commit()

        result = await db.execute(
            select(InvoiceDB)
            .options(selectinload(InvoiceDB.items))
            .where(InvoiceDB.id == invoice.id)
        )
        return result.scalar_one()

    except (BadRequestError, NotFoundError, ClassNotFoundError):
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error("create_invoice failed | institution=%s student=%s",
                    institution_id, data.student_user_id, exc_info=True)
        raise DatabaseError("Failed to create invoice")


async def get_invoices(
    db: AsyncSession,
    institution_id: int,
    student_user_id: int | None = None,
    status: InvoiceStatus | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[InvoiceDB], int]:
    """
    Returns (invoices, total_count). When search is provided it matches
    invoice_number, student name, or student email via a join.
    """
    base_query = (
        select(InvoiceDB)
        .where(InvoiceDB.institution_id == institution_id)
        .options(selectinload(InvoiceDB.items))
        .order_by(InvoiceDB.created_at.desc())
    )
    count_query = (
        select(func.count(InvoiceDB.id))
        .where(InvoiceDB.institution_id == institution_id)
    )

    if student_user_id:
        base_query = base_query.where(InvoiceDB.student_user_id == student_user_id)
        count_query = count_query.where(InvoiceDB.student_user_id == student_user_id)

    if status:
        base_query = base_query.where(InvoiceDB.status == status)
        count_query = count_query.where(InvoiceDB.status == status)

    if search:
        # Join with user for name/email search
        search_term = f"%{search}%"
        base_query = (
            base_query
            .join(UserDB, UserDB.id == InvoiceDB.student_user_id)
            .where(
                (InvoiceDB.invoice_number.ilike(search_term)) |
                (UserDB.first_name.ilike(search_term)) |
                (UserDB.last_name.ilike(search_term)) |
                (UserDB.email.ilike(search_term))
            )
        )
        count_query = (
            count_query
            .join(UserDB, UserDB.id == InvoiceDB.student_user_id)
            .where(
                (InvoiceDB.invoice_number.ilike(search_term)) |
                (UserDB.first_name.ilike(search_term)) |
                (UserDB.last_name.ilike(search_term)) |
                (UserDB.email.ilike(search_term))
            )
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar_one() or 0

    offset = (page - 1) * page_size
    base_query = base_query.offset(offset).limit(page_size)
    result = await db.execute(base_query)
    return result.scalars().all(), total


async def get_invoice_by_id(
    db: AsyncSession,
    institution_id: int,
    invoice_id: int
) -> InvoiceDB:
    result = await db.execute(
        select(InvoiceDB)
        .where(InvoiceDB.id == invoice_id, InvoiceDB.institution_id == institution_id)
        .options(
            selectinload(InvoiceDB.items),
            selectinload(InvoiceDB.payments),
            selectinload(InvoiceDB.fines)
        )
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        from ..core.exceptions import NotFoundError
        raise NotFoundError(f"Invoice not found")
    return invoice


async def cancel_invoice(
    db: AsyncSession,
    institution_id: int,
    invoice_id: int
) -> dict:
    invoice = await get_invoice_by_id(db, institution_id, invoice_id)
    if invoice.paid_total > 0:
        active_paid = sum(
            p.amount_paid for p in invoice.payments
            if p.payment_status not in ("REFUNDED", "PARTIALLY_REFUNDED")
        )
        if active_paid > 0:
            raise BadRequestError("Cannot cancel invoice with existing payments")
    invoice.status = InvoiceStatus.CANCELLED
    try:
        await db.commit()
        # Return invoice_number (public identifier) instead of internal id
        return {"message": "Invoice cancelled", "invoice_number": invoice.invoice_number}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error cancelling invoice: {e}", exc_info=True)
        raise DatabaseError("Failed to cancel invoice")


# ==================================================
# PAYMENT CRUD
# ==================================================

async def create_payment(
    db: AsyncSession,
    institution_id: int,
    tenant_id: str,
    invoice_id: int,
    data: PaymentCreate
) -> PaymentDB:
    invoice = await get_invoice_by_id(db, institution_id, invoice_id)

    if invoice.status == InvoiceStatus.CANCELLED:
        from ..core.exceptions import BadRequestError
        raise BadRequestError("Cannot record payment on a cancelled invoice")

    if invoice.status == InvoiceStatus.PAID:
        from ..core.exceptions import BadRequestError
        raise BadRequestError("Invoice is already fully paid")

    if data.amount_paid > invoice.balance_due:
        from ..core.exceptions import BadRequestError
        raise BadRequestError(
            f"Payment amount {data.amount_paid} exceeds balance due {invoice.balance_due}"
        )

    try:
        payment = PaymentDB(
            institution_id=institution_id,
            invoice_id=invoice_id,
            student_user_id=invoice.student_user_id,
            receipt_number=_generate_receipt_number(tenant_id),
            amount_paid=data.amount_paid,
            payment_method=data.payment_method,
            transaction_ref=data.transaction_ref,
            payment_status="SUCCESS",
            notes=data.notes
        )
        db.add(payment)
        await db.flush()

        invoice.payments.append(payment)
        _recalculate_invoice(invoice)

        await db.commit()
        await db.refresh(payment)
        return payment
    except Exception as e:
        await db.rollback()
        logger.error(
    "create_payment failed | institution=%s invoice=%s",
    institution_id, invoice_id, exc_info=True
)
        raise DatabaseError("Failed to record payment")


async def get_payments_by_invoice(
    db: AsyncSession,
    institution_id: int,
    invoice_id: int
) -> list[PaymentDB]:
    result = await db.execute(
        select(PaymentDB).where(
            PaymentDB.institution_id == institution_id,
            PaymentDB.invoice_id == invoice_id
        ).order_by(PaymentDB.paid_at.desc())
    )
    return result.scalars().all()


async def get_payments_by_student(
    db: AsyncSession,
    institution_id: int,
    student_user_id: int,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PaymentDB], int]:
    base_query = (
        select(PaymentDB)
        .where(
            PaymentDB.institution_id == institution_id,
            PaymentDB.student_user_id == student_user_id,
        )
        .order_by(PaymentDB.paid_at.desc())
    )
    count_query = (
        select(func.count(PaymentDB.id))
        .where(
            PaymentDB.institution_id == institution_id,
            PaymentDB.student_user_id == student_user_id,
        )
    )

    if search:
        search_term = f"%{search}%"
        base_query = base_query.where(
            PaymentDB.receipt_number.ilike(search_term) |
            PaymentDB.transaction_ref.ilike(search_term) |
            PaymentDB.payment_method.ilike(search_term)
        )
        count_query = count_query.where(
            PaymentDB.receipt_number.ilike(search_term) |
            PaymentDB.transaction_ref.ilike(search_term) |
            PaymentDB.payment_method.ilike(search_term)
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar_one() or 0

    offset = (page - 1) * page_size
    result = await db.execute(base_query.offset(offset).limit(page_size))
    return result.scalars().all(), total


async def get_all_payments(
    db: AsyncSession,
    institution_id: int,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PaymentDB], int]:
    """Fetch all payments for institution with optional student name/email search."""
    base_query = (
        select(PaymentDB)
        .where(PaymentDB.institution_id == institution_id)
        .order_by(PaymentDB.paid_at.desc())
    )
    count_query = (
        select(func.count(PaymentDB.id))
        .where(PaymentDB.institution_id == institution_id)
    )

    if search:
        search_term = f"%{search}%"
        base_query = (
            base_query
            .join(UserDB, UserDB.id == PaymentDB.student_user_id)
            .where(
                PaymentDB.receipt_number.ilike(search_term) |
                PaymentDB.transaction_ref.ilike(search_term) |
                UserDB.first_name.ilike(search_term) |
                UserDB.last_name.ilike(search_term) |
                UserDB.email.ilike(search_term)
            )
        )
        count_query = (
            count_query
            .join(UserDB, UserDB.id == PaymentDB.student_user_id)
            .where(
                PaymentDB.receipt_number.ilike(search_term) |
                PaymentDB.transaction_ref.ilike(search_term) |
                UserDB.first_name.ilike(search_term) |
                UserDB.last_name.ilike(search_term) |
                UserDB.email.ilike(search_term)
            )
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar_one() or 0

    offset = (page - 1) * page_size
    result = await db.execute(base_query.offset(offset).limit(page_size))
    return result.scalars().all(), total


# ==================================================
# DISCOUNT CRUD
# ==================================================

async def create_discount(
    db: AsyncSession,
    institution_id: int,
    data: DiscountCreate
) -> DiscountDB:
    try:
        discount = DiscountDB(
            institution_id=institution_id,
            student_user_id=data.student_user_id,
            title=data.title,
            reason=data.reason,
            discount_type=data.discount_type,
            value=data.value,
            start_date=data.start_date,
            end_date=data.end_date
        )
        db.add(discount)
        await db.commit()
        await db.refresh(discount)
        return discount
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating discount: {e}", exc_info=True)
        raise DatabaseError("Failed to create discount")


async def get_discounts_by_student(
    db: AsyncSession,
    institution_id: int,
    student_user_id: int
) -> list[DiscountDB]:
    result = await db.execute(
        select(DiscountDB).where(
            DiscountDB.institution_id == institution_id,
            DiscountDB.student_user_id == student_user_id
        ).order_by(DiscountDB.created_at.desc())
    )
    return result.scalars().all()


async def update_discount(
    db: AsyncSession,
    institution_id: int,
    discount_id: int,
    data: DiscountUpdate
) -> DiscountDB:
    result = await db.execute(
        select(DiscountDB).where(
            DiscountDB.id == discount_id,
            DiscountDB.institution_id == institution_id
        )
    )
    discount = result.scalar_one_or_none()
    if not discount:
        from ..core.exceptions import NotFoundError
        raise NotFoundError(f"Discount {discount_id} not found")

    for field, value in data.model_dump(exclude_none=True).items():
        if field not in _ALLOWED_DISCOUNT_FIELDS:
            logger.warning(f"Attempted to set unknown discount field: {field}")
            continue
        setattr(discount, field, value)

    try:
        await db.commit()
        await db.refresh(discount)
        return discount
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating discount: {e}", exc_info=True)
        raise DatabaseError("Failed to update discount")


async def apply_discount_to_invoice(
    db: AsyncSession,
    institution_id: int,
    invoice_id: int,
    discount_id: int
) -> InvoiceDB:
    invoice = await get_invoice_by_id(db, institution_id, invoice_id)

    result = await db.execute(
        select(DiscountDB).where(
            DiscountDB.id == discount_id,
            DiscountDB.institution_id == institution_id,
            DiscountDB.student_user_id == invoice.student_user_id,
            DiscountDB.is_active == True
        )
    )
    discount = result.scalar_one_or_none()
    if not discount:
        from ..core.exceptions import NotFoundError
        raise NotFoundError("Active discount not found for this student")

    if discount.discount_type == "PERCENTAGE":
        discount_amount = (invoice.subtotal * discount.value / 100).quantize(Decimal("0.01"))
    else:
        discount_amount = min(discount.value, invoice.subtotal)

    invoice.discount_total = discount_amount
    _recalculate_invoice(invoice)

    try:
        await db.commit()
        await db.refresh(invoice)
        return invoice
    except Exception as e:
        await db.rollback()
        logger.error(f"Error applying discount: {e}", exc_info=True)
        raise DatabaseError("Failed to apply discount")


# ==================================================
# FINE CRUD
# ==================================================

async def add_fine_to_invoice(
    db: AsyncSession,
    institution_id: int,
    invoice_id: int,
    data: FineCreate
) -> FineDB:
    invoice = await get_invoice_by_id(db, institution_id, invoice_id)
    if invoice.status == InvoiceStatus.CANCELLED:
        from ..core.exceptions import BadRequestError
        raise BadRequestError("Cannot add fine to a cancelled invoice")

    try:
        fine = FineDB(
            invoice_id=invoice_id,
            title=data.title,
            reason=data.reason,
            amount=data.amount
        )
        db.add(fine)
        await db.flush()

        invoice.fines.append(fine)
        _recalculate_invoice(invoice)

        await db.commit()
        await db.refresh(fine)
        return fine
    except Exception as e:
        await db.rollback()
        logger.error(f"Error adding fine: {e}", exc_info=True)
        raise DatabaseError("Failed to add fine")


async def get_fines_by_invoice(
    db: AsyncSession,
    invoice_id: int
) -> list[FineDB]:
    result = await db.execute(
        select(FineDB).where(FineDB.invoice_id == invoice_id)
    )
    return result.scalars().all()


# ==================================================
# REFUND CRUD
# ==================================================

async def create_refund(
    db: AsyncSession,
    institution_id: int,
    payment_id: int,
    data: RefundCreate
) -> RefundDB:
    result = await db.execute(
        select(PaymentDB).where(
            PaymentDB.id == payment_id,
            PaymentDB.institution_id == institution_id
        )
    )
    payment = result.scalar_one_or_none()
    if not payment:
        from ..core.exceptions import NotFoundError
        raise NotFoundError(f"Payment not found")

    if payment.payment_status != "SUCCESS":
        from ..core.exceptions import BadRequestError
        raise BadRequestError("Can only refund successful payments")

    existing_refunds = await db.execute(
        select(RefundDB).where(RefundDB.payment_id == payment_id)
    )
    already_refunded = sum(r.amount for r in existing_refunds.scalars().all())
    if already_refunded + data.amount > payment.amount_paid:
        from ..core.exceptions import BadRequestError
        raise BadRequestError(
            f"Refund amount exceeds refundable amount. Already refunded: {already_refunded}"
        )

    try:
        refund = RefundDB(
            payment_id=payment_id,
            amount=data.amount,
            reason=data.reason,
            refund_status="SUCCESS"
        )
        db.add(refund)

        remaining = payment.amount_paid - already_refunded - data.amount
        payment.payment_status = "REFUNDED" if remaining == 0 else "PARTIALLY_REFUNDED"

        invoice = await get_invoice_by_id(db, institution_id, payment.invoice_id)
        _recalculate_invoice(invoice)

        await db.commit()
        await db.refresh(refund)
        return refund
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating refund: {e}", exc_info=True)
        raise DatabaseError("Failed to create refund")


# ==================================================
# DASHBOARD
# ==================================================
# cron job needed
async def get_fee_dashboard(
    db: AsyncSession,
    institution_id: int,
    tenant_id: str,
) -> dict:
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ── Query 1 ── main invoice aggregation + student counts (was 3 queries) ──
    inv_agg = await db.execute(
        select(
            func.count(InvoiceDB.id.distinct()).label("total_invoices"),
            func.sum(InvoiceDB.grand_total).label("total_invoiced"),
            func.sum(InvoiceDB.paid_total).label("total_collected"),
            func.sum(
                case(
                    (
                        (InvoiceDB.due_date < now)
                        & (InvoiceDB.balance_due > 0)
                        & (
                            InvoiceDB.status.in_([
                                InvoiceStatus.UNPAID,
                                InvoiceStatus.PARTIAL,
                                InvoiceStatus.OVERDUE,
                            ])
                        ),
                        InvoiceDB.balance_due,
                    ),
                    else_=0,
                )
            ).label("overdue_amount"),
            func.sum(
                case(
                    (
                        InvoiceDB.status.in_([
                            InvoiceStatus.UNPAID,
                            InvoiceStatus.PARTIAL,
                            InvoiceStatus.OVERDUE,
                        ]),
                        InvoiceDB.balance_due,
                    ),
                    else_=0,
                )
            ).label("pending_amount"),
            # student counts merged in
            func.count(
                InvoiceDB.student_user_id.distinct()
            ).label("total_students"),
            func.count(
                case(
                    (InvoiceDB.status == InvoiceStatus.PAID, InvoiceDB.student_user_id)
                )
            ).label("fully_paid_students"),
        ).where(
            InvoiceDB.institution_id == institution_id,
            InvoiceDB.status != InvoiceStatus.CANCELLED,
        )
    )
    agg = inv_agg.mappings().one()

    total_collected = agg["total_collected"] or Decimal("0.00")
    total_invoiced  = agg["total_invoiced"]  or Decimal("0.00")
    pending_amount  = agg["pending_amount"]  or Decimal("0.00")
    overdue_amount  = agg["overdue_amount"]  or Decimal("0.00")
    total_students  = agg["total_students"]  or 0
    fully_paid_students = agg["fully_paid_students"] or 0

    collection_rate = (
        float(total_collected / total_invoiced * 100) if total_invoiced > 0 else 0.0
    )

    # ── Query 2 ── this-month stats (was 2 queries) ───────────────────────────
    month_agg = await db.execute(
        select(
            func.count(InvoiceDB.id).label("invoices_this_month"),
            func.count(
                case(
                    (InvoiceDB.discount_total > 0, InvoiceDB.id)
                )
            ).label("discounts_applied_this_month"),
        ).where(
            InvoiceDB.institution_id == institution_id,
            InvoiceDB.issue_date >= month_start,
        )
    )
    month_row = month_agg.mappings().one()
    invoices_this_month          = month_row["invoices_this_month"]          or 0
    discounts_applied_this_month = month_row["discounts_applied_this_month"] or 0

    # ── Query 3 ── class-level aggregation ────────────────────────────────────
    classes = await get_all_class(db=db, tenant_id=tenant_id)

    class_agg_rows = await db.execute(
        select(
            ClassDB.class_code.label("class_code"),
            func.sum(InvoiceDB.grand_total).label("total_invoiced"),
            func.sum(InvoiceDB.paid_total).label("total_collected"),
        )
        .join(FeeStructureDB, InvoiceDB.fee_structure_id == FeeStructureDB.id)
        .join(ClassDB, FeeStructureDB.class_id == ClassDB.id)
        .where(
            InvoiceDB.institution_id == institution_id,
            InvoiceDB.status != InvoiceStatus.CANCELLED,
        )
        .group_by(ClassDB.class_code)
    )
    class_agg_map: dict[str, dict] = {
        row.class_code: {
            "total_invoiced":  row.total_invoiced  or Decimal("0.00"),
            "total_collected": row.total_collected or Decimal("0.00"),
        }
        for row in class_agg_rows.mappings().all()
    }

    class_collection = []
    for cls in classes:
        agg_data = class_agg_map.get(cls.class_code, {
            "total_invoiced":  Decimal("0.00"),
            "total_collected": Decimal("0.00"),
        })
        ti   = agg_data["total_invoiced"]
        tc   = agg_data["total_collected"]
        rate = float(tc / ti * 100) if ti > 0 else 0.0
        class_collection.append({
            "class_code":           cls.class_code,
            "class_or_year_or_name": cls.class_or_year_or_name,
            "section":              cls.section,
            "total_invoiced":       ti,
            "total_collected":      tc,
            "collection_rate":      round(rate, 1),
        })
    print(class_agg_map)
    # ── Query 4 ── payment method breakdown ───────────────────────────────────
    method_rows = await db.execute(
        select(
            PaymentDB.payment_method.label("method"),
            func.sum(PaymentDB.amount_paid).label("total_amount"),
            func.count(PaymentDB.id).label("transaction_count"),
        )
        .where(
            PaymentDB.institution_id == institution_id,
            PaymentDB.payment_status == "SUCCESS",
        )
        .group_by(PaymentDB.payment_method)
    )
    method_rows_list = method_rows.mappings().all()

    grand_paid = (
        sum(r["total_amount"] or Decimal("0.00") for r in method_rows_list)
        or Decimal("1")
    )
    payment_methods = [
        {
            "method":            row["method"],
            "total_amount":      row["total_amount"] or Decimal("0.00"),
            "transaction_count": row["transaction_count"],
            "percentage": round(
                float((row["total_amount"] or Decimal("0.00")) / grand_paid * 100), 1
            ),
        }
        for row in method_rows_list
    ]

    # ── Query 5 ── upcoming deadlines (next 30 days) ──────────────────────────
    window_end = now + timedelta(days=30)
    deadline_rows = await db.execute(
        select(
            func.date(InvoiceDB.due_date).label("due_date"),
            func.count(InvoiceDB.id).label("invoice_count"),
            func.sum(InvoiceDB.balance_due).label("total_balance_due"),
        )
        .where(
            InvoiceDB.institution_id == institution_id,
            InvoiceDB.status.in_([
                InvoiceStatus.UNPAID,
                InvoiceStatus.PARTIAL,
                InvoiceStatus.OVERDUE,
            ]),
            InvoiceDB.due_date.isnot(None),
            InvoiceDB.due_date <= window_end,
        )
        .group_by(func.date(InvoiceDB.due_date))
        .order_by(func.date(InvoiceDB.due_date).asc())
        .limit(10)
    )

    upcoming_deadlines = [
        {
            "due_date":        (due_dt := datetime.combine(row["due_date"], datetime.min.time())),
            "invoice_count":   row["invoice_count"],
            "total_balance_due": row["total_balance_due"] or Decimal("0.00"),
            "days_until_due":  (due_dt - now).days,
        }
        for row in deadline_rows.mappings().all()
    ]

    return {
        "total_collected":              total_collected,
        "pending_amount":               pending_amount,
        "overdue_amount":               overdue_amount,
        "total_students_with_invoices": total_students,
        "fully_paid_students":          fully_paid_students,
        "collection_rate":              round(collection_rate, 1),
        "invoices_this_month":          invoices_this_month,
        "discounts_applied_this_month": discounts_applied_this_month,
        "class_collection":             class_collection,
        "payment_methods":              payment_methods,
        "upcoming_deadlines":           upcoming_deadlines,
    }