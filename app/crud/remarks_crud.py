from sqlalchemy.future import select
from sqlalchemy import and_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.remarks_schema import RemarkCreate, RemarkUpdate, RemarkResponse  , DisciplinaryRecordCreate,DisciplinaryRecordUpdate,DisciplinaryRecordResponse
from app.models.user_model import RemarkDB
from app.models.institution_model import InstitutionDB
from ..core.exceptions import (
    DatabaseError,
    InstitutionNotFoundError,
    RemarkNotFoundError,
    InsufficientPermissionError,
    UserNotFoundException,
    DisciplinaryRecordNotFoundError
)
from app.models.user_model import UserDB,UserRoleEnum

from app.models.role_specific.student_model import DisciplinaryRecordDB,StudentDB
from typing import List
import logging

logger = logging.getLogger(__name__)


async def create_remark(
    db: AsyncSession,
    tenant_id: str,
    given_by_id: int,
    given_by_role: str,
    remark_data: RemarkCreate,
) -> RemarkDB:
    """Create a new remark."""

    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_result.scalar_one_or_none()
    if not institution_id:
        raise InstitutionNotFoundError("Institution not found")

    try:
        db_remark = RemarkDB(
            **remark_data.model_dump(),
            given_by_id=given_by_id,
            given_by_role=given_by_role,
            institution_id=institution_id,
        )
        db.add(db_remark)
        await db.commit()
        await db.refresh(db_remark)
        return db_remark
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating remark: {e}", exc_info=True)
        raise DatabaseError("Unable to create remark")


async def get_all_remarks(
    db: AsyncSession,
    tenant_id: str,
    current_user_id: int,
) -> List[RemarkDB]:
    """Get all remarks created by the current user within their institution."""

    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_result.scalar_one_or_none()
    if not institution_id:
        raise InstitutionNotFoundError("Institution not found")

    result = await db.execute(
        select(RemarkDB)
        .where(
            and_(
                RemarkDB.institution_id == institution_id,
                RemarkDB.given_by_id == current_user_id,
            )
        )
        .order_by(RemarkDB.created_at.desc())
        .limit(7)
    )
    return result.scalars().all()



async def get_remarks_by_target(
    db: AsyncSession,
    tenant_id: str,
    target_id: int,
    target_type: str,
    current_user_id: int,
) -> List[RemarkDB]:
    """Get all remarks for a specific target created by the current user."""

    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_result.scalar_one_or_none()
    if not institution_id:
        raise InstitutionNotFoundError("Institution not found")

    result = await db.execute(
        select(RemarkDB)
        .where(
            and_(
                RemarkDB.institution_id == institution_id,
                RemarkDB.given_by_id == current_user_id,
                RemarkDB.target_id == target_id,
                RemarkDB.target_type == target_type,
            )
        )
        .order_by(RemarkDB.created_at.desc())
    )
    return result.scalars().all()


async def update_remark(
    db: AsyncSession,
    tenant_id: str,
    remark_id: int,
    updated_data: RemarkUpdate,
    current_user_id: int,
) -> RemarkDB:
    """Update a remark — only the creator can update it."""

    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")

    result = await db.execute(
        select(RemarkDB).where(RemarkDB.id == remark_id)
    )
    remark = result.scalars().first()

    if not remark:
        raise RemarkNotFoundError(f"Remark {remark_id} not found")

    if remark.given_by_id != current_user_id:
        raise InsufficientPermissionError("You do not have permission to update this remark")

    update_dict = updated_data.model_dump(exclude_unset=True)
    if not update_dict:
        raise ValueError("No fields provided for update")

    for key, value in update_dict.items():
        setattr(remark, key, value)

    try:
        await db.commit()
        await db.refresh(remark)
        return remark
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating remark: {e}", exc_info=True)
        raise DatabaseError("Unable to update remark")


async def delete_remark(
    db: AsyncSession,
    tenant_id: str,
    remark_id: int,
    current_user_id: int,
) -> dict:
    """Delete a remark — only the creator can delete it."""

    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")

    result = await db.execute(
        select(RemarkDB).where(RemarkDB.id == remark_id)
    )
    remark = result.scalars().first()

    if not remark:
        raise RemarkNotFoundError(f"Remark {remark_id} not found")

    if remark.given_by_id != current_user_id:
        raise InsufficientPermissionError("You do not have permission to delete this remark")

    try:
        await db.delete(remark)
        await db.commit()
        return {"message": f"Remark {remark_id} deleted successfully"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting remark: {e}", exc_info=True)
        raise DatabaseError("Unable to delete remark")
    









# Diciplinary things
# ==================== HELPERS ====================

async def _get_institution_id(db: AsyncSession, tenant_id: str) -> int:
    """Resolve institution_id from tenant_id, raise if not found."""
    result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = result.scalar_one_or_none()
    if not institution_id:
        raise InstitutionNotFoundError("Institution not found")
    return institution_id


async def _get_student(db: AsyncSession, student_user_id: int) -> StudentDB:
    """Fetch a student by PK, raise if not found."""

    result = await db.execute(
        select(StudentDB).join(UserDB, UserDB.id ==StudentDB.user_id).where(StudentDB.user_id == student_user_id,UserDB.role ==UserRoleEnum.STUDENT.value)
    )
    student = result.scalars().first()
    if not student:
        raise UserNotFoundException(f"Student not found")
    return student


async def _get_record(db: AsyncSession, record_id: int) -> DisciplinaryRecordDB:
    """Fetch a disciplinary record by PK, raise if not found."""
    result = await db.execute(
        select(DisciplinaryRecordDB).where(DisciplinaryRecordDB.id == record_id)
    )
    record = result.scalars().first()
    if not record:
        raise DisciplinaryRecordNotFoundError(f"Disciplinary record {record_id} not found")
    return record


# ==================== CRUD OPERATIONS ====================

async def create_disciplinary_record(
    db: AsyncSession,
    tenant_id: str,
    creator_user_id: int,
    record_data: DisciplinaryRecordCreate,
) -> DisciplinaryRecordDB:
    """Create a new disciplinary record for a student."""

    await _get_institution_id(db, tenant_id)
    student = await _get_student(db, record_data.student_user_id)

    try:
        db_record = DisciplinaryRecordDB(student_id = student.id,incident_date=record_data.incident_date,incident_level=record_data.incident_level,description= record_data.description,action_taken = record_data.action_taken,reported_by = creator_user_id,is_locked= record_data.is_locked)
        db.add(db_record)
        await db.commit()
        await db.refresh(db_record)
        return db_record
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating disciplinary record: {e}", exc_info=True)
        raise DatabaseError("Unable to create disciplinary record")


async def get_all_disciplinary_records(
    db: AsyncSession,
    tenant_id: str,
) -> List[DisciplinaryRecordDB]:
    """Get all disciplinary records across the institution."""

    await _get_institution_id(db, tenant_id)

    result = await db.execute(
        select(DisciplinaryRecordDB).order_by(DisciplinaryRecordDB.incident_date.desc())
    )
    return result.scalars().all()


async def get_disciplinary_records_by_student(
    db: AsyncSession,
    tenant_id: str,
    student_id: int,
) -> List[DisciplinaryRecordDB]:
    """Get all disciplinary records for a specific student."""

    await _get_institution_id(db, tenant_id)

    result = await db.execute(
        select(DisciplinaryRecordDB)
        .where(DisciplinaryRecordDB.student_id == student_id)
        .order_by(DisciplinaryRecordDB.incident_date.desc())
    )
    student = result.scalars().all()
    if not student:
        raise UserNotFoundException("User not found")
    
    return student


async def get_disciplinary_record_by_recorder(
    db: AsyncSession,
    tenant_id: str,
    recorder_id: int,
) -> List[DisciplinaryRecordDB]:
    """Get a single disciplinary record by ID."""

    await _get_institution_id(db, tenant_id)
    result = await db.execute(
        select(DisciplinaryRecordDB)
        .where(DisciplinaryRecordDB.reported_by == recorder_id)
        .order_by(DisciplinaryRecordDB.incident_date.desc())
    )
    return result.scalars().all()


async def update_disciplinary_record(
    db: AsyncSession,
    tenant_id: str,
    record_id: int,
    updated_data: DisciplinaryRecordUpdate,
) -> DisciplinaryRecordDB:
    """Update a disciplinary record."""

    await _get_institution_id(db, tenant_id)
    record = await _get_record(db, record_id)

    update_dict = updated_data.model_dump(exclude_unset=True)
    if not update_dict:
        raise ValueError("No fields provided for update")

    for key, value in update_dict.items():
        setattr(record, key, value)

    try:
        await db.commit()
        await db.refresh(record)
        return record
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating disciplinary record: {e}", exc_info=True)
        raise DatabaseError("Unable to update disciplinary record")
