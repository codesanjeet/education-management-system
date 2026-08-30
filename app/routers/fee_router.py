from fastapi import APIRouter, HTTPException, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from math import ceil

from ..crud.fee_crud import (
    get_fee_dashboard,
    get_billing_settings, update_billing_settings,
    create_fee_structure, get_fee_structures, get_fee_structure_by_id,
    update_fee_structure, delete_fee_structure,
    create_invoice, get_invoices, get_invoice_by_id, cancel_invoice,
    create_payment, get_payments_by_invoice, get_payments_by_student,
    get_all_payments,
    create_discount, get_discounts_by_student, update_discount, apply_discount_to_invoice,
    add_fine_to_invoice, get_fines_by_invoice,
    create_refund,
    _build_student_info, _build_payment_student_info,
    _resolve_invoice_number, _resolve_receipt_number,
)
from ..schemas.fee_schema import (
    FeeDashboardResponse,
    BillingSettingsResponse, BillingSettingsUpdate,
    FeeStructureCreate, FeeStructureUpdate, FeeStructureResponse,
    InvoiceCreate, InvoiceResponse, InvoiceListResponse, PaginatedInvoiceResponse,
    PaymentCreate, PaymentResponse, PaginatedPaymentResponse,
    DiscountCreate, DiscountUpdate, DiscountResponse,
    FineCreate, FineResponse,
    RefundCreate, RefundResponse,
    InvoiceStatusEnum, PaginationMeta,
)
from ..core.database import get_db
from ..schemas.user_schema import CurrentUserResponse
from ..deps import get_current_user, require_permission
from ..models.institution_model import InstitutionDB
from ..models.fee_model import InvoiceStatus

import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# ==================================================
# HELPER — resolve institution_id from tenant_id
# ==================================================

async def get_institution_id(db: AsyncSession, tenant_id: str) -> int:
    result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = result.scalar_one_or_none()
    if institution_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Institution not found for this tenant"
        )
    return institution_id


# ==================================================
# BILLING SETTINGS ROUTES
# ==================================================

@router.get(
    "/institutions/billing-settings",
    status_code=status.HTTP_200_OK,
    response_model=BillingSettingsResponse,
)
async def get_billing_settings_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
) -> BillingSettingsResponse:
    institution_id = await get_institution_id(db, current_user.tenant_id)
    data = await get_billing_settings(db=db, institution_id=institution_id)
    return BillingSettingsResponse(**data)


@router.patch(
    "/institutions/billing-settings",
    status_code=status.HTTP_200_OK,
    response_model=BillingSettingsResponse,
)
async def update_billing_settings_endpoint(
    data: BillingSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("system:settings")),
) -> BillingSettingsResponse:
    institution_id = await get_institution_id(db, current_user.tenant_id)
    result = await update_billing_settings(
        db=db, institution_id=institution_id, data=data
    )
    return BillingSettingsResponse(**result)


# ==================================================
# FEE STRUCTURE ROUTES
# ==================================================

@router.post(
    "/institutions/fee-structures",
    status_code=status.HTTP_201_CREATED,
    response_model=List[FeeStructureResponse],
)
async def create_fee_structure_endpoint(
    data: FeeStructureCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:structure_manage")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    fee_structures = await create_fee_structure(
        db=db,
        tenant_id=current_user.tenant_id,
        institution_id=institution_id,
        data=data,
    )
    return [FeeStructureResponse.model_validate(fs, from_attributes=True) for fs in fee_structures]


@router.get(
    "/institutions/fee-structures",
    status_code=status.HTTP_200_OK,
    response_model=List[FeeStructureResponse],
)
async def get_fee_structures_endpoint(
    class_code: Optional[str] = Query(None, description="Filter by class"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:structure_manage")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    fee_structures = await get_fee_structures(
        db=db,
        institution_id=institution_id,
        class_code=class_code,
    )
    return [FeeStructureResponse.model_validate(fs, from_attributes=True) for fs in fee_structures]


@router.get(
    "/institutions/fee-structures/{fee_structure_id}",
    status_code=status.HTTP_200_OK,
    response_model=FeeStructureResponse,
)
async def get_fee_structure_endpoint(
    fee_structure_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    fee_structure = await get_fee_structure_by_id(
        db=db, institution_id=institution_id, fee_structure_id=fee_structure_id
    )
    return FeeStructureResponse.model_validate(fee_structure, from_attributes=True)


@router.patch(
    "/institutions/fee-structures/{fee_structure_id}",
    status_code=status.HTTP_200_OK,
    response_model=FeeStructureResponse,
)
async def update_fee_structure_endpoint(
    fee_structure_id: int,
    data: FeeStructureUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:structure_manage")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    fee_structure = await update_fee_structure(
        db=db, institution_id=institution_id,
        fee_structure_id=fee_structure_id, data=data,
    )
    return FeeStructureResponse.model_validate(fee_structure, from_attributes=True)


@router.delete(
    "/institutions/fee-structures/{fee_structure_id}",
    status_code=status.HTTP_200_OK,
)
async def deactivate_fee_structure_endpoint(
    fee_structure_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:structure_manage")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await delete_fee_structure(
        db=db, institution_id=institution_id, fee_structure_id=fee_structure_id
    )


# ==================================================
# INVOICE ROUTES

# ==================================================

@router.post(
    "/institutions/invoices",
    status_code=status.HTTP_201_CREATED,
    response_model=InvoiceResponse,
)
async def create_invoice_endpoint(
    data: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    invoice = await create_invoice(
        db=db, institution_id=institution_id,
        tenant_id=current_user.tenant_id, data=data,
    )
    response = InvoiceResponse.model_validate(invoice, from_attributes=True)
    response.student = await _build_student_info(db, invoice.student_user_id)
    return response


@router.get(
    "/institutions/invoices",
    status_code=status.HTTP_200_OK,
    response_model=PaginatedInvoiceResponse,
)
async def get_invoices_endpoint(
    student_user_id: Optional[int] = Query(None, description="Filter by student"),
    status_filter: Optional[InvoiceStatusEnum] = Query(None, alias="status", description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by name, email, or invoice number"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)

    if current_user.role == "student":
        student_user_id = current_user.id

    invoice_status = InvoiceStatus(status_filter.value) if status_filter else None
    invoices, total = await get_invoices(
        db=db,
        institution_id=institution_id,
        student_user_id=student_user_id,
        status=invoice_status,
        search=search,
        page=page,
        page_size=page_size,
    )

    # Enrich with student data
    enriched = []
    for inv in invoices:
        item = InvoiceListResponse.model_validate(inv, from_attributes=True)
        item.student = await _build_student_info(db, inv.student_user_id)
        enriched.append(item)

    total_pages = ceil(total / page_size) if page_size else 1
    return PaginatedInvoiceResponse(
        items=enriched,
        meta=PaginationMeta(total=total, page=page, page_size=page_size, total_pages=total_pages),
    )


@router.get(
    "/institutions/invoices/{invoice_number}",
    status_code=status.HTTP_200_OK,
    response_model=InvoiceResponse,
)
async def get_invoice_endpoint(
    invoice_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_invoice_number(db, institution_id, invoice_number)
    invoice = await get_invoice_by_id(
        db=db, institution_id=institution_id, invoice_id=internal_id
    )
    if current_user.role == "student" and invoice.student_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    response = InvoiceResponse.model_validate(invoice, from_attributes=True)
    response.student = await _build_student_info(db, invoice.student_user_id)
    return response


@router.patch(
    "/institutions/invoices/{invoice_number}/cancel",
    status_code=status.HTTP_200_OK,
)
async def cancel_invoice_endpoint(
    invoice_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_invoice_number(db, institution_id, invoice_number)
    return await cancel_invoice(
        db=db, institution_id=institution_id, invoice_id=internal_id
    )


# ==================================================
# PAYMENT ROUTES
# ==================================================

@router.post(
    "/institutions/invoices/{invoice_number}/payments",
    status_code=status.HTTP_201_CREATED,
    response_model=PaymentResponse,
)
async def create_payment_endpoint(
    invoice_number: str,
    data: PaymentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_invoice_number(db, institution_id, invoice_number)
    payment = await create_payment(
        db=db, institution_id=institution_id,
        tenant_id=current_user.tenant_id,
        invoice_id=internal_id, data=data,
    )
    response = PaymentResponse.model_validate(payment, from_attributes=True)
    response.student = await _build_payment_student_info(db, payment.student_user_id)
    # Fetch invoice number for context (already known from path param)
    response.invoice_number = invoice_number
    return response


@router.get(
    "/institutions/invoices/{invoice_number}/payments",
    status_code=status.HTTP_200_OK,
    response_model=List[PaymentResponse],
)
async def get_invoice_payments_endpoint(
    invoice_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends((require_permission("fee:collection"))),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_invoice_number(db, institution_id, invoice_number)
    payments = await get_payments_by_invoice(
        db=db, institution_id=institution_id, invoice_id=internal_id
    )
    result = []
    for p in payments:
        item = PaymentResponse.model_validate(p, from_attributes=True)
        item.student = await _build_payment_student_info(db, p.student_user_id)
        item.invoice_number = invoice_number
        result.append(item)
    return result


@router.get(
    "/institutions/payments",
    status_code=status.HTTP_200_OK,
    response_model=PaginatedPaymentResponse,
)
async def get_all_payments_endpoint(
    search: Optional[str] = Query(None, description="Search by name, email, or receipt number"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    payments, total = await get_all_payments(
        db=db, institution_id=institution_id,
        search=search, page=page, page_size=page_size,
    )

    # Batch-enrich student info
    enriched = []
    for p in payments:
        item = PaymentResponse.model_validate(p, from_attributes=True)
        item.student = await _build_payment_student_info(db, p.student_user_id)
        enriched.append(item)

    total_pages = ceil(total / page_size) if page_size else 1
    return PaginatedPaymentResponse(
        items=enriched,
        meta=PaginationMeta(total=total, page=page, page_size=page_size, total_pages=total_pages),
    )


@router.get(
    "/institutions/students/{student_user_id}/payments",
    status_code=status.HTTP_200_OK,
    response_model=PaginatedPaymentResponse,
)
async def get_student_payments_endpoint(
    student_user_id: int,
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    if current_user.role == "student" and current_user.id != student_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    institution_id = await get_institution_id(db, current_user.tenant_id)
    payments, total = await get_payments_by_student(
        db=db, institution_id=institution_id,
        student_user_id=student_user_id,
        search=search, page=page, page_size=page_size,
    )

    enriched = []
    student_info = await _build_payment_student_info(db, student_user_id)
    for p in payments:
        item = PaymentResponse.model_validate(p, from_attributes=True)
        item.student = student_info
        enriched.append(item)

    total_pages = ceil(total / page_size) if page_size else 1
    return PaginatedPaymentResponse(
        items=enriched,
        meta=PaginationMeta(total=total, page=page, page_size=page_size, total_pages=total_pages),
    )


# ==================================================
# REFUND ROUTES
# Path param is now receipt_number (string) instead of payment_id (int).
# ==================================================

@router.post(
    "/institutions/payments/{receipt_number}/refunds",
    status_code=status.HTTP_201_CREATED,
    response_model=RefundResponse,
)
async def create_refund_endpoint(
    receipt_number: str,
    data: RefundCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_receipt_number(db, institution_id, receipt_number)
    refund = await create_refund(
        db=db, institution_id=institution_id, payment_id=internal_id, data=data
    )
    return RefundResponse.model_validate(refund, from_attributes=True)


# ==================================================
# DISCOUNT ROUTES
# ==================================================

@router.post(
    "/institutions/discounts",
    status_code=status.HTTP_201_CREATED,
    response_model=DiscountResponse,
)
async def create_discount_endpoint(
    data: DiscountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    discount = await create_discount(db=db, institution_id=institution_id, data=data)
    return DiscountResponse.model_validate(discount, from_attributes=True)


@router.get(
    "/institutions/students/{student_user_id}/discounts",
    status_code=status.HTTP_200_OK,
    response_model=List[DiscountResponse],
)
async def get_student_discounts_endpoint(
    student_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    if current_user.role in ["student", "parent"] and current_user.id != student_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    institution_id = await get_institution_id(db, current_user.tenant_id)
    discounts = await get_discounts_by_student(
        db=db, institution_id=institution_id, student_user_id=student_user_id
    )
    return [DiscountResponse.model_validate(d, from_attributes=True) for d in discounts]


@router.patch(
    "/institutions/discounts/{discount_id}",
    status_code=status.HTTP_200_OK,
    response_model=DiscountResponse,
)
async def update_discount_endpoint(
    discount_id: int,
    data: DiscountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    discount = await update_discount(
        db=db, institution_id=institution_id, discount_id=discount_id, data=data
    )
    return DiscountResponse.model_validate(discount, from_attributes=True)


@router.post(
    "/institutions/invoices/{invoice_number}/apply-discount/{discount_id}",
    status_code=status.HTTP_200_OK,
    response_model=InvoiceResponse,
)
async def apply_discount_endpoint(
    invoice_number: str,
    discount_id: int,   # discount_id stays int — staff-only internal reference
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_invoice_number(db, institution_id, invoice_number)
    invoice = await apply_discount_to_invoice(
        db=db, institution_id=institution_id,
        invoice_id=internal_id, discount_id=discount_id,
    )
    response = InvoiceResponse.model_validate(invoice, from_attributes=True)
    response.student = await _build_student_info(db, invoice.student_user_id)
    return response


# ==================================================
# FINE ROUTES
# ==================================================

@router.post(
    "/institutions/invoices/{invoice_number}/fines",
    status_code=status.HTTP_201_CREATED,
    response_model=FineResponse,
)
async def add_fine_endpoint(
    invoice_number: str,
    data: FineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_invoice_number(db, institution_id, invoice_number)
    fine = await add_fine_to_invoice(
        db=db, institution_id=institution_id, invoice_id=internal_id, data=data
    )
    return FineResponse.model_validate(fine, from_attributes=True)


@router.get(
    "/institutions/invoices/{invoice_number}/fines",
    status_code=status.HTTP_200_OK,
    response_model=List[FineResponse],
)
async def get_invoice_fines_endpoint(
    invoice_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:collection")),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    internal_id = await _resolve_invoice_number(db, institution_id, invoice_number)
    fines = await get_fines_by_invoice(db=db, invoice_id=internal_id)
    return [FineResponse.model_validate(f, from_attributes=True) for f in fines]


# ==================================================
# DASHBOARD
# ==================================================

@router.get(
    "/institutions/fees/dashboard",
    status_code=status.HTTP_200_OK,
    response_model=FeeDashboardResponse,
)
async def get_fee_dashboard_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("fee:report")),
) -> FeeDashboardResponse:
    institution_id = await get_institution_id(db, current_user.tenant_id)
    data = await get_fee_dashboard(
        db=db, institution_id=institution_id, tenant_id=current_user.tenant_id,
    )
    return FeeDashboardResponse(**data)