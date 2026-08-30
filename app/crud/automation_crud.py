"""
invoice_scheduler_service.py
─────────────────────────────
Generates invoices automatically for every active student in every active class.

Structure resolution order (per class):
  1. Fee structures where class_id matches this class exactly
       → if multiple, use the most recently created one (latest id)
  2. If none found for this class → fall back to the single global structure
       (i.e. there is exactly one active structure in the whole institution)
  3. If still none, or more than one global structure with no class match → error

Duplicate guard:
  Skips a student if an invoice already exists for the same
  (student_user_id, fee_structure_id) combination, preventing double-billing
  on re-runs.

Usage
─────
Manual / dev:
    from app.services.invoice_scheduler_service import run_invoice_generation
    result = await run_invoice_generation(tenant_id="TEN00001")

Future cron (Linux crontab / Windows Task Scheduler / APScheduler):
    # Linux crontab  — runs at 08:00 on the 1st of every month
    0 8 1 * * /usr/bin/python /app/scripts/run_invoice_job.py

    # APScheduler
    scheduler.add_job(
        _scheduler_wrapper,
        trigger="cron", day=1, hour=8,
        id="auto_invoice_generation",
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import AsyncSessionLocal
from ..models.fee_model import FeeStructureDB, InvoiceDB
from ..models.classes_model import ClassDB
from ..models.institution_model import InstitutionDB
from ..schemas.fee_schema import InvoiceCreate, InvoiceItemCreate
from ..crud.fee_crud import create_invoice
from ..crud.class_crud import get_all_class
from ..crud.student_curd import get_student_all
from ..core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


# ─── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class InvoiceJobResult:
    tenant_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    classes_processed: int = 0
    invoices_created: int = 0
    invoices_skipped: int = 0          # already existed
    errors: list[str] = field(default_factory=list)
    success: bool = False

    @property
    def duration_ms(self) -> Optional[float]:
        if self.finished_at:
            return (self.finished_at - self.started_at).total_seconds() * 1000
        return None

    def summary(self) -> str:
        status = "✓ OK" if self.success else "✗ FAILED"
        dur = f"{self.duration_ms:.1f}ms" if self.duration_ms is not None else "—"
        return (
            f"[auto_invoice_generation | {self.tenant_id}] {status} | "
            f"classes={self.classes_processed} | "
            f"created={self.invoices_created} | "
            f"skipped={self.invoices_skipped} | "
            f"errors={len(self.errors)} | "
            f"duration={dur}"
        )


# ─── Structure resolver ───────────────────────────────────────────────────────

def _resolve_structure(
    class_db_id: int,
    class_structures: list[FeeStructureDB],   # structures for this specific class
    all_structures: list[FeeStructureDB],      # every active structure in institution
) -> Optional[FeeStructureDB]:
    """
    Returns the fee structure to use for a given class, or None if undecidable.

    Priority:
      1. Structures tied to this class  → pick the most recently created one
      2. No class-specific match        → use the sole institution-wide structure
      3. Otherwise                      → None  (caller must log an error)
    """
    if class_structures:
        # Pick the latest (highest id = most recently created)
        return max(class_structures, key=lambda s: s.id)

    # Fallback: if exactly one structure exists institution-wide, use it for all classes
    if len(all_structures) == 1:
        return all_structures[0]

    # Multiple structures exist but none mapped to this class → ambiguous
    return None


# ─── Core generation logic ────────────────────────────────────────────────────

async def _generate_invoices_for_tenant(
    db: AsyncSession,
    tenant_id: str,
    result: InvoiceJobResult,
) -> None:
    today = datetime.utcnow().date()

    # ── 1. Resolve institution_id from tenant_id ──────────────────────────────
    inst_row = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id: Optional[int] = inst_row.scalar_one_or_none()
    if not institution_id:
        raise ValueError(f"Institution not found for tenant_id={tenant_id!r}")

    # ── 2. Fetch all active classes ───────────────────────────────────────────
    # get_all_class returns List[ClassBasicResponse] (no .id field).
    # We need the raw ClassDB rows to get the integer primary key for the
    # FeeStructureDB.class_id FK join, so we query ClassDB directly here.
    class_rows = await db.execute(
        select(ClassDB).where(
            ClassDB.institution_id == institution_id,
            ClassDB.is_active == True,
        )
    )
    classes: list[ClassDB] = list(class_rows.scalars().all())

    if not classes:
        logger.warning("No active classes found for tenant_id=%s", tenant_id)
        return

    # ── 3. Fetch all active fee structures for this institution ───────────────
    struct_rows = await db.execute(
        select(FeeStructureDB).where(
            FeeStructureDB.institution_id == institution_id,
            FeeStructureDB.is_active == True,
        ).order_by(FeeStructureDB.id.asc())
    )
    all_structures: list[FeeStructureDB] = list(struct_rows.scalars().all())

    if not all_structures:
        raise ValueError(
            f"No active fee structures found for institution_id={institution_id}. "
            "Please create at least one fee structure before running invoice generation."
        )

    # Pre-index structures by class_id for O(1) lookup
    structures_by_class: dict[int, list[FeeStructureDB]] = {}
    for s in all_structures:
        structures_by_class.setdefault(s.class_id, []).append(s)

    # ── 4. For each class: resolve structure → fetch students → create invoices ─
    for cls in classes:
        result.classes_processed += 1

        # Resolve which fee structure to use for this class
        class_specific = structures_by_class.get(cls.id, [])
        structure = _resolve_structure(cls.id, class_specific, all_structures)

        if structure is None:
            msg = (
                f"Class '{cls.class_code}' (id={cls.id}): cannot resolve fee structure. "
                f"{len(all_structures)} active structures exist but none map to this class "
                "and there is more than one global structure. "
                "Please create a structure specifically for this class."
            )
            logger.error(msg)
            result.errors.append(msg)
            continue

        logger.info(
            "Class '%s' → using structure '%s' (id=%d)",
            cls.class_code, structure.name, structure.id,
        )

        # Fetch students for this class using the existing crud helper
        try:
            students = await get_student_all(
                db=db,
                tenant_id=tenant_id,
                class_code=cls.class_code,
            )
        except Exception as exc:
            # get_student_all raises UserNotFoundException when no students found —
            # that is not an error for invoice generation, just skip the class.
            logger.info(
                "Class '%s': no students found, skipping. (%s)",
                cls.class_code, exc,
            )
            continue

        # Build invoice items from the structure's JSON
        items_data: list[dict] = structure.structure_json.get("items", [])
        if not items_data:
            msg = (
                f"Class '{cls.class_code}': fee structure '{structure.name}' "
                "has no items in structure_json. Skipping."
            )
            logger.warning(msg)
            result.errors.append(msg)
            continue

        invoice_items = [
            InvoiceItemCreate(
                item_name=item["name"],
                description=None,
                quantity=1,
                unit_amount=item["amount"],
            )
            for item in items_data
        ]

        # ── 5. Per-student: duplicate check then create ───────────────────────
        for student in students:
            try:
                # Duplicate guard — skip if (student, structure) invoice already exists
                exists_q = await db.execute(
                    select(InvoiceDB.id).where(
                        InvoiceDB.student_user_id == student.id,
                        InvoiceDB.fee_structure_id == structure.id,
                        InvoiceDB.institution_id == institution_id,
                    )
                )
                if exists_q.scalar_one_or_none() is not None:
                    logger.debug(
                        "Invoice already exists for student_id=%d structure_id=%d — skipping.",
                        student.id, structure.id,
                    )
                    result.invoices_skipped += 1
                    continue

                invoice_data = InvoiceCreate(
                    student_user_id=student.id,
                    fee_structure_id=structure.id,
                    due_date=None,
                    notes=f"Auto-generated on {today}",
                    items=invoice_items,
                )

                # create_invoice already auto-applies the best active discount
                await create_invoice(
                    db=db,
                    institution_id=institution_id,
                    tenant_id=tenant_id,
                    data=invoice_data,
                )
                result.invoices_created += 1
                logger.debug(
                    "Invoice created: student_id=%d class='%s' structure='%s'",
                    student.id, cls.class_code, structure.name,
                )

            except Exception as exc:
                msg = (
                    f"Failed to create invoice for student_id={student.id} "
                    f"class='{cls.class_code}': {exc}"
                )
                logger.error(msg, exc_info=True)
                result.errors.append(msg)
                # Continue with the next student — don't abort the whole run


# ─── Public entry point ───────────────────────────────────────────────────────

async def run_invoice_generation(
    tenant_id: str,
    db: Optional[AsyncSession] = None,
) -> InvoiceJobResult:
    """
    Generate invoices for all active students across all active classes.

    Parameters
    ----------
    tenant_id   The institution's tenant identifier.
    db          Optional existing AsyncSession.  If omitted a new session is
                opened and closed automatically (use this for cron / scripts).

    Returns
    -------
    InvoiceJobResult  — inspect .summary() for a one-line log string.

    Examples
    --------
    # From a FastAPI endpoint or test:
    result = await run_invoice_generation(tenant_id="TEN00001")
    print(result.summary())

    # Injecting an existing session (e.g. inside a request):
    result = await run_invoice_generation(tenant_id="TEN00001", db=db)
    """
    job = InvoiceJobResult(tenant_id=tenant_id, started_at=datetime.utcnow())

    async def _run(session: AsyncSession) -> None:
        try:
            await _generate_invoices_for_tenant(session, tenant_id, job)
            job.success = not bool(job.errors) or job.invoices_created > 0
        except Exception as exc:
            msg = f"Fatal error in run_invoice_generation: {exc}"
            logger.error(msg, exc_info=True)
            job.errors.append(msg)
            job.success = False
        finally:
            job.finished_at = datetime.utcnow()
            logger.info(job.summary())

    if db is not None:
        await _run(db)
    else:
        async with AsyncSessionLocal() as session:
            await _run(session)

    return job

if __name__ == "__main__":
    import asyncio

    TENANT_ID = "TEN00001"   # change if needed

    result = asyncio.run(run_invoice_generation(tenant_id=TENANT_ID))
    print(result.summary())