from sqlalchemy.future import select
from sqlalchemy import and_, exists,func
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.class_schema import (
    ClassCreate, ClassBasicResponse, ClassResponse, ClassUpdate,
    ClassScheduleCreate, ClassScheduleResponse, ClassScheduleUpdate
)
from app.models.classes_model import ClassDB, ClassScheduleDB
from app.models.institution_model import InstitutionDB
from ..core.exceptions import (
    DatabaseError, 
    ClassNotFoundError, 
    ClassAlreadyExistsError,
    InstitutionNotFoundError,
    ScheduleNotFoundError,
    ScheduleConflictError,
    UserNotFoundException
)
from app.models.role_specific.student_model import StudentDB
from app.models.user_model import UserDB
import secrets
from datetime import datetime, timezone
from typing import List,Dict,Any
import string
import logging

logger = logging.getLogger(__name__)


def create_class_code() -> str:
    return "EDU" + ''.join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(5)
    )


async def _fetch_teacher_map(
    db: AsyncSession,
    tenant_id: str,
    teacher_ids: List[int]
) -> Dict[int, Any]:

    if not teacher_ids:
        return {}

    teachers_q = await db.execute(
        select(UserDB.id, UserDB.first_name, UserDB.last_name).where(
            UserDB.id.in_(teacher_ids),
            UserDB.tenant_id == tenant_id
        )
    )
    teachers = teachers_q.mappings().all()
    teacher_map = {t["id"]: t for t in teachers}

    missing = set(teacher_ids) - set(teacher_map.keys())
    if missing:
        raise UserNotFoundException(f"Teachers not found: {missing}")

    return teacher_map


async def create_class(
    db: AsyncSession,
    class_data: ClassCreate,
    tenant_id: str,
    class_schedule_data: List[ClassScheduleCreate],
):
    """Create a new class with schedules."""
    
    # Normalize schedule data
    for schedule in class_schedule_data:
        schedule.subject_name = schedule.subject_name.capitalize()
        schedule.day = schedule.day.capitalize()
    
    # Check institution exists (optimized - only fetch ID)
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_result.scalar_one_or_none()
    
    if not institution_id:
        logger.warning(f"Institution not found for tenant: {tenant_id}")
        raise InstitutionNotFoundError("Institution not found")
    
    # Generate and check class code uniqueness
    class_code = create_class_code()
    code_check = await db.execute(
        select(exists().where(ClassDB.class_code == class_code))
    )
    if code_check.scalar():
        # Retry once with new code
        class_code = create_class_code()
        code_check = await db.execute(
            select(exists().where(ClassDB.class_code == class_code))
        )
        if code_check.scalar():
            raise ClassAlreadyExistsError("Failed to generate unique class code")


    actual_schedule_data = [schedule.model_dump() for schedule in class_schedule_data]
    # Collect all teacher IDs
    teacher_ids = [s["teacher_user_id"] for s in actual_schedule_data if s["teacher_user_id"] is not None]

    # Single query to fetch all teachers at once
    teachers_q = await db.execute(
            select(UserDB.id, UserDB.first_name, UserDB.last_name).where(
                UserDB.id.in_(teacher_ids),
                UserDB.tenant_id == tenant_id
            )
        )
    teachers = teachers_q.mappings().all()

    # Build a lookup dict  {user_id: {first_name, last_name}}
    teacher_map = {t["id"]: t for t in teachers}

        # Check all teachers exist before proceeding
    missing = set(teacher_ids) - set(teacher_map.keys())
    if missing:
        raise UserNotFoundException(f"Teachers not found: {missing}")

        # Enrich schedule dicts
    for schedule in actual_schedule_data:
        teacher = teacher_map[schedule["teacher_user_id"]]
        schedule.update({
                "teacher_first_name": teacher["first_name"],
                "teacher_last_name": teacher["last_name"]
            })
            
    # Create class with schedules
    try:

        db_class = ClassDB(
            **class_data.model_dump(),
            class_code=class_code,
            institution_id=institution_id
        )
        
        # Create schedules
        db_class.class_schedule = [
            ClassScheduleDB(**schedule) 
            for schedule in actual_schedule_data
        ]
        
        db.add(db_class)
        await db.commit()
        await db.refresh(db_class)
        
        return db_class
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating class: {e}", exc_info=True)
        raise DatabaseError("Unable to create class")


async def get_basic_class(
    db: AsyncSession, 
    tenant_id: str, 
    class_code: str
) -> ClassBasicResponse:
    """Get basic class information."""

    inst_id_q = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_id_q.scalar_one_or_none()
    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")
    
    
    query = select(ClassDB).where(
        and_(
           ClassDB.institution_id == inst_id,
            ClassDB.class_code == class_code
        )
    )
    
    result = await db.execute(query)
    class_ = result.scalars().first()

    if not class_:
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    return class_


async def get_all_class(
    db: AsyncSession, 
    tenant_id: str
) -> List[ClassBasicResponse]:
    """Get all classes for an institution."""
    
    # Check institution exists (optimized - only check existence)
    inst_id_q = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_id_q.scalar_one_or_none()
    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")
    
    # Get all classes
    query = await db.execute(
        select(ClassDB)
        .where(ClassDB.institution_id == inst_id)
    )
    classes = query.scalars().all()
    
    if not classes:
        raise ClassNotFoundError("No classes found")
    
    return [ClassBasicResponse.model_validate(cls, from_attributes=True) for cls in classes]


async def get_full_class(
    db: AsyncSession, 
    tenant_id: str, 
    class_code: str
) -> dict:
    """Get full class information including schedules."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Get class with schedules
    query = await db.execute(
        select(ClassDB).where(ClassDB.class_code == class_code)
    )
    class_ = query.scalars().first()
    
    if not class_:
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    return {
        "class_data": class_,
        "class_schedule": class_.class_schedule
    }


async def update_class(
    db: AsyncSession, 
    tenant_id: str, 
    class_code: str, 
    updated_data: ClassUpdate
):
    """Update class information."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Get class
    query = await db.execute(
        select(ClassDB).where(ClassDB.class_code == class_code)
    )
    class_ = query.scalars().first()
    
    if not class_:
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    # Update fields
    update_dict = updated_data.model_dump(exclude_unset=True)
    if not update_dict:
        raise ValueError("No fields provided for update")
    
    for key, value in update_dict.items():
        setattr(class_, key, value)
    
    try:
        await db.commit()
        await db.refresh(class_)
        return class_
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating class: {e}", exc_info=True)
        raise DatabaseError("Unable to update class")


async def delete_class(
    db: AsyncSession, 
    tenant_id: str, 
    class_code: str
):
    """Hard delete a class (permanently remove)."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Get class
    query = await db.execute(
        select(ClassDB).where(ClassDB.class_code == class_code)
    )
    class_ = query.scalars().first()
    
    if not class_:
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    try:
        await db.delete(class_)
        await db.commit()
        return {"message": "Class deleted successfully"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting class: {e}", exc_info=True)
        raise DatabaseError("Unable to delete class")


async def mark_as_deleted_class(
    db: AsyncSession, 
    tenant_id: str, 
    class_code: str
):
    """Soft delete/restore a class (toggle deleted_date)."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Get class
    query = await db.execute(
        select(ClassDB).where(ClassDB.class_code == class_code)
    )
    class_to_delete = query.scalars().first()
    
    if not class_to_delete:
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    # Toggle soft delete
    if class_to_delete.deleted_date is None:
        class_to_delete.deleted_date = datetime.now(timezone.utc).date()
        message = f"Class {class_code} has been soft-deleted"
    else:
        class_to_delete.deleted_date = None
        message = f"Class {class_code} has been restored"
    
    try:
        await db.commit()
        await db.refresh(class_to_delete)
        return {"message": message}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error toggling class deletion: {e}", exc_info=True)
        raise DatabaseError("Unable to update class status")


# ==================== CLASS SCHEDULE OPERATIONS ====================

async def create_class_schedule(
    db: AsyncSession,
    class_schedule_data: List[ClassScheduleCreate],
    class_code: str,
    tenant_id: str
):
    """Create class schedules."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Get class ID
    class_query = await db.execute(
        select(ClassDB.id).where(ClassDB.class_code == class_code)
    )
    class_id = class_query.scalar_one_or_none()
    
    if not class_id:
        raise ClassNotFoundError(f"Class {class_code} not found")
    

    
    actual_schedule_data = [schedule.model_dump() for schedule in class_schedule_data]
    # Collect all teacher IDs
    teacher_ids = [s["teacher_user_id"] for s in actual_schedule_data if s["teacher_user_id"] is not None]

    # Single query to fetch all teachers at once
    teachers_q = await db.execute(
            select(UserDB.id, UserDB.first_name, UserDB.last_name).where(
                UserDB.id.in_(teacher_ids),
                UserDB.tenant_id == tenant_id
            )
        )
    teachers = teachers_q.mappings().all()

    # Build a lookup dict  {user_id: {first_name, last_name}}
    teacher_map = {t["id"]: t for t in teachers}

        # Check all teachers exist before proceeding
    missing = set(teacher_ids) - set(teacher_map.keys())
    if missing:
        raise UserNotFoundException(f"Teachers not found: {missing}")

        # Enrich schedule dicts
    for schedule in actual_schedule_data:
        teacher = teacher_map[schedule["teacher_user_id"]]
        schedule.update({
                "teacher_first_name": teacher["first_name"],
                "teacher_last_name": teacher["last_name"]
            })
            
    
    try:
        schedules = [
            ClassScheduleDB(
                **schedule,
                class_id=class_id
            )
            for schedule in actual_schedule_data
        ]
        
        db.add_all(schedules)
        await db.commit()
        
        # Refresh to get IDs
        for schedule in schedules:
            await db.refresh(schedule)
        
        return schedules
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating class schedule: {e}", exc_info=True)
        raise DatabaseError("Unable to create class schedule")


async def get_class_schedule(
    class_code: str,
    db: AsyncSession,
    tenant_id: str
):
    """Get all schedules for a class."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Get class ID
    class_query = await db.execute(
        select(ClassDB.id).where(ClassDB.class_code == class_code)
    )
    class_id = class_query.scalar_one_or_none()
    
    if not class_id:
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    # Get schedules
    schedule_query = await db.execute(
        select(
            ClassScheduleDB.teacher_user_id,
            ClassScheduleDB.id,
            ClassScheduleDB.subject_code,
            ClassScheduleDB.subject_name,
            ClassScheduleDB.teacher_first_name,
            ClassScheduleDB.teacher_last_name,
            ClassScheduleDB.class_room,
            ClassScheduleDB.start_time,
            ClassScheduleDB.end_time,
            ClassScheduleDB.day,
            ClassScheduleDB.is_class_teacher,
        )
        .where(ClassScheduleDB.class_id == class_id)
        .order_by(ClassScheduleDB.day, ClassScheduleDB.start_time)
    )
    
    schedules = schedule_query.mappings().all()
    
    if not schedules:
        return []  
    
    return [ClassScheduleResponse(**schedule) for schedule in schedules]


async def get_today_class_schedule(
    user_id: int,
    db: AsyncSession,
    tenant_id: str
):
    """Get today's schedule for a class."""

    # Check institution exists
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # get class code
    student_q = await db.execute(select(StudentDB.class_code).where(user_id == StudentDB.user_id))
    class_code = student_q.scalar_one_or_none()
    # Get class ID
    class_query = await db.execute(
        select(ClassDB.id).where(ClassDB.class_code == class_code)
    )
    class_id = class_query.scalar_one_or_none()

    if not class_id:
        raise ClassNotFoundError(f"Class {class_code} not found")

    #  Get today's day
    today_day = datetime.utcnow().strftime("%A").lower()

    #  Get only today's schedules
    schedule_query = await db.execute(
        select(
            ClassScheduleDB.teacher_user_id,
            ClassScheduleDB.id,
            ClassScheduleDB.subject_code,
            ClassScheduleDB.subject_name,
            ClassScheduleDB.teacher_first_name,
            ClassScheduleDB.teacher_last_name,
            ClassScheduleDB.class_room,
            ClassScheduleDB.start_time,
            ClassScheduleDB.end_time,
            ClassScheduleDB.day,
            ClassScheduleDB.is_class_teacher,
        )
        .where(
            ClassScheduleDB.class_id == class_id,
            func.lower(ClassScheduleDB.day) == today_day.lower()  
        )
        .order_by(ClassScheduleDB.start_time)
    )

    schedules = schedule_query.mappings().all()

    if not schedules:
        return []

    return [ClassScheduleResponse(**schedule) for schedule in schedules]

async def update_class_schedule(
    db: AsyncSession, 
    tenant_id: str, 
    class_code: str, 
    updated_data: ClassScheduleUpdate, 
    schedule_id: int
):
    """Update a specific class schedule."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Check class exists (optimized)
    class_check = await db.execute(
        select(exists().where(ClassDB.class_code == class_code))
    )
    if not class_check.scalar():
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    # Get schedule
    query = await db.execute(
        select(ClassScheduleDB).where(ClassScheduleDB.id == schedule_id)
    )
    class_schedule = query.scalars().first()
    
    if not class_schedule:
        raise ScheduleNotFoundError(f"Schedule {schedule_id} not found")
    
    # Update fields
    update_dict = updated_data.model_dump(exclude_unset=True)
    if not update_dict:
        raise ValueError("No fields provided for update")
    
    new_teacher_id = update_dict.get("teacher_user_id")
    if new_teacher_id is not None and new_teacher_id != class_schedule.teacher_user_id:
        teacher_map = await _fetch_teacher_map(db, tenant_id, [new_teacher_id])
        teacher = teacher_map[new_teacher_id]
        update_dict["teacher_first_name"] = teacher["first_name"]
        update_dict["teacher_last_name"]  = teacher["last_name"]
    
    for key, value in update_dict.items():
        setattr(class_schedule, key, value)
    
    try:
        await db.commit()
        await db.refresh(class_schedule)
        return class_schedule
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating schedule: {e}", exc_info=True)
        raise DatabaseError("Unable to update schedule")


async def delete_class_schedule(
    db: AsyncSession, 
    tenant_id: str, 
    class_code: str, 
    schedule_id: int
):
    """Delete a class schedule."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Check class exists (optimized)
    class_check = await db.execute(
        select(exists().where(ClassDB.class_code == class_code))
    )
    if not class_check.scalar():
        raise ClassNotFoundError(f"Class {class_code} not found")
    
    # Get schedule
    query = await db.execute(
        select(ClassScheduleDB).where(ClassScheduleDB.id == schedule_id)
    )
    class_schedule = query.scalars().first()
    
    if not class_schedule:
        raise ScheduleNotFoundError(f"Schedule {schedule_id} not found")
    
    try:
        await db.delete(class_schedule)
        await db.commit()
        return {"message": f"Schedule {schedule_id} deleted successfully"}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting schedule: {e}", exc_info=True)
        raise DatabaseError("Unable to delete schedule")


async def check_teacher_availability(
    db: AsyncSession, 
    teacher_user_id: int,
    day: str, 
    start_time: int, 
    end_time: int
):
    """Check if teacher is available at given time slot."""
    
    query = await db.execute(
        select(ClassScheduleDB)
        .where(ClassScheduleDB.teacher_user_id == teacher_user_id)
        .where(ClassScheduleDB.day == day)
        .where(
            (ClassScheduleDB.start_time < end_time) & 
            (ClassScheduleDB.end_time > start_time)
        )
    )
    conflict = query.scalars().first()
    
    if conflict:
        raise ScheduleConflictError(
            f"Teacher {teacher_user_id} is not available on {day} "
            f"from {start_time} to {end_time}"
        )

    return True


# get schedule for staff 

async def get_today_staff_schedule(
    user_id: int,
    db: AsyncSession,
    tenant_id: str
):
    """Get today's schedule for a class."""

    # Check institution exists
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")

    #  Get today's day
    today_day = datetime.utcnow().strftime("%A").lower()

    #  Get only today's schedules
    schedule_query = await db.execute(
        select(
            ClassScheduleDB.teacher_user_id,
            ClassScheduleDB.id,
            ClassScheduleDB.subject_code,
            ClassScheduleDB.subject_name,
            ClassScheduleDB.teacher_first_name,
            ClassScheduleDB.teacher_last_name,
            ClassScheduleDB.class_room,
            ClassScheduleDB.start_time,
            ClassScheduleDB.end_time,
            ClassScheduleDB.day,
            ClassScheduleDB.is_class_teacher,
        )
        .where(
            ClassScheduleDB.teacher_user_id == user_id,
            func.lower(ClassScheduleDB.day) == today_day.lower()  
        )
        .order_by(ClassScheduleDB.start_time)
    )

    schedules = schedule_query.mappings().all()

    if not schedules:
        return []

    return [ClassScheduleResponse(**schedule) for schedule in schedules]



async def get_staff_schedule(
    user_id: int,
    db: AsyncSession,
    tenant_id: str
):
    """Get all schedules for a class."""
    
    # Check institution exists (optimized)
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Get schedules
    schedule_query = await db.execute(
        select(
            ClassScheduleDB.teacher_user_id,
            ClassScheduleDB.id,
            ClassScheduleDB.subject_code,
            ClassScheduleDB.subject_name,
            ClassScheduleDB.teacher_first_name,
            ClassScheduleDB.teacher_last_name,
            ClassScheduleDB.class_room,
            ClassScheduleDB.start_time,
            ClassScheduleDB.end_time,
            ClassScheduleDB.day,
            ClassScheduleDB.is_class_teacher,
        )
        .where(ClassScheduleDB.teacher_user_id == user_id)
        .order_by(ClassScheduleDB.day, ClassScheduleDB.start_time)
    )
    
    schedules = schedule_query.mappings().all()
    
    if not schedules:
        return []  
    
    return [ClassScheduleResponse(**schedule) for schedule in schedules]

