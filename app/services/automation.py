# app/services/invoice_scheduler_service.py

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.user_model import UserDB
from app.models.fee_model import FeeStructureDB, InvoiceDB, InvoiceItemDB
from app.schemas.fee_schema import InvoiceCreate, InvoiceItemCreate
from app.crud.fee_crud import create_invoice


async def generate_due_invoices():
    """
    Run this manually now.
    Later use cron / Azure scheduler.
    """

    async with AsyncSessionLocal() as db:  # type: AsyncSession
        today = datetime.utcnow().date()

        # Get active fee structures
        result = await db.execute(
            select(FeeStructureDB).where(
                FeeStructureDB.is_active == True
            )
        )
        fee_structures = result.scalars().all()

        for fee in fee_structures:

            # Get active students of this class
            students_result = await db.execute(
                select(UserDB).where(
                    UserDB.class_code == fee.class_id,   # adjust if needed
                    UserDB.is_block == False
                )
            )
            students = students_result.scalars().all()

            items_data = fee.structure_json.get("items", [])

            for student in students:

                # Prevent duplicate monthly invoice (basic check)
                exists_result = await db.execute(
                    select(InvoiceDB).where(
                        InvoiceDB.student_id == student.id,
                        InvoiceDB.fee_structure_id == fee.id,
                    )
                )
                already_exists = exists_result.scalars().first()

                if already_exists:
                    continue

                invoice_items = [
                    InvoiceItemCreate(
                        item_name=item["name"],
                        description=None,
                        quantity=1,
                        unit_amount=item["amount"]
                    )
                    for item in items_data
                ]

                invoice_data = InvoiceCreate(
                    student_id=student.id,
                    fee_structure_id=fee.id,
                    due_date=None,
                    notes=f"Auto generated on {today}",
                    items=invoice_items
                )

                await create_invoice(
                    db=db,
                    institution_id=fee.institution_id,
                    tenant_id="TEN00001",   # replace dynamically
                    data=invoice_data
                )

        print("Invoices generated successfully.")


















