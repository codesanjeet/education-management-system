from enum import Enum
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..schemas.class_schema import (
    ClassBasicResponse, ClassResponse, 
    ClassScheduleCreate, ClassScheduleResponse, ClassUpdate, 
    ClassScheduleUpdate, ClassDataResponse,CreateClassWithSchedule
)
from ..schemas.user_schema import CurrentUserResponse
from ..crud.class_crud import (
    create_class, get_all_class,
      get_basic_class,
        get_full_class,
    update_class, mark_as_deleted_class, get_class_schedule,
    create_class_schedule, update_class_schedule, delete_class_schedule,get_staff_schedule,get_today_class_schedule,get_today_staff_schedule
)
from ..core.exceptions import InsufficientPermissionError
from typing import List
import logging
from ..deps import get_current_user, require_permission
from ..crud.dashboard_crud import create_recent_activity_log
router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== CLASS ROUTES ====================

@router.post("/institutions/classes", status_code=status.HTTP_201_CREATED, response_model=ClassBasicResponse)
async def create_class_endpoint(
    request: CreateClassWithSchedule,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("class:management"))

):
    class_ = await create_class(
        db=db,
        tenant_id=current_user.tenant_id,
        class_data=request.class_data,
        class_schedule_data=request.class_schedule_data
    )
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="class_created",
        message=f"Class created: {class_.class_or_year_or_name} (section: {class_.section})"
    )
    result = ClassBasicResponse.model_validate(class_, from_attributes=True)
    return result


@router.get(
    "/institutions/classes",
    status_code=status.HTTP_200_OK,
    response_model=List[ClassBasicResponse]
)
async def get_all_classes_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
):
    if current_user.role not in ("student", "parent"):
        classes = await get_all_class(db=db, tenant_id=current_user.tenant_id)
        return [ClassBasicResponse.model_validate(cls, from_attributes=True) for cls in classes]

@router.get(
    "/institutions/classes/{class_code}",
    status_code=status.HTTP_200_OK,
    response_model=ClassResponse
)
async def get_class_endpoint(
    class_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
):
    class_ = await get_full_class(
        db=db,
        tenant_id=current_user.tenant_id,
        class_code=class_code
    )
    return class_


@router.patch(
    "/institutions/classes/{class_code}",
    status_code=status.HTTP_200_OK,
    response_model=ClassDataResponse
)
async def update_class_endpoint(
    class_code: str,
    updated_data: ClassUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("class:management"))
):

    class_ = await update_class(
        db=db,
        tenant_id=current_user.tenant_id,
        class_code=class_code,
        updated_data=updated_data
    )
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="class_updated",
        message=f"Class updated: {class_.class_or_year_or_name} (section: {class_.section})"
    )
    return ClassDataResponse.model_validate(class_, from_attributes=True)


@router.delete(
    "/institutions/classes/{class_code}",
    status_code=status.HTTP_200_OK
)
async def soft_delete_class_endpoint(
    class_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("class:management"))
):
    
    result = await mark_as_deleted_class(
        db=db,
        tenant_id=current_user.tenant_id,
        class_code=class_code
    )
    class_ = await get_basic_class(db=db, tenant_id=current_user.tenant_id, class_code=class_code)
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="class_deleted",
        message=f"Class deleted/restore: {class_.class_or_year_or_name} (section: {class_.section})"
    )
    return result


# ==================== CLASS SCHEDULE ROUTES ====================

@router.post(
    "/institutions/classes/{class_code}/schedules",
    status_code=status.HTTP_201_CREATED,
    response_model=List[ClassScheduleResponse]
)
async def create_class_schedule_endpoint(
    class_code: str,
    class_schedule_data: List[ClassScheduleCreate],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("class:management"))
):
    schedules = await create_class_schedule(
        db=db,
        tenant_id=current_user.tenant_id,
        class_code=class_code,
        class_schedule_data=class_schedule_data
    )
    class_ = await get_basic_class(db=db, tenant_id=current_user.tenant_id, class_code=class_code)
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="schedule_created",
        message=f"Class schedule created: {class_.class_or_year_or_name} (section: {class_.section}) - {len(schedules)} schedule(s) added"
    )
    return [
        ClassScheduleResponse.model_validate(schedule, from_attributes=True)
        for schedule in schedules
    ]


class ScheduleType(str, Enum):
    TODAY = "today"
    ALL = "all"


@router.get(
    "/institutions/classes/{class_code}/schedules",
    status_code=status.HTTP_200_OK,
    response_model=List[ClassScheduleResponse]
)
async def get_class_schedule_endpoint(
    class_code: str,
    type: ScheduleType = ScheduleType.ALL,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
):
    
    if type == ScheduleType.TODAY:
        schedules = await get_today_class_schedule(
        tenant_id=current_user.tenant_id,
        class_code=class_code,
        db=db
    )
    else:
        schedules = await get_class_schedule(
            tenant_id=current_user.tenant_id,
            class_code=class_code,
            db=db
        )
    return [
        ClassScheduleResponse.model_validate(schedule, from_attributes=True)
        for schedule in schedules
    ]


@router.get(
    "/institutions/staff/{user_id}/schedules",
    status_code=status.HTTP_200_OK,
    response_model=List[ClassScheduleResponse]
)
async def get_staff_schedule_endpoint(
    user_id: int,
    type: ScheduleType = ScheduleType.ALL,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
):
    if current_user.role in ["student", "parent"]:
        raise InsufficientPermissionError("Access denied: insufficient permissions")
    if type == ScheduleType.TODAY:
        schedules = await get_today_staff_schedule(
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        db=db
    )
    else:
        schedules = await get_staff_schedule(
            tenant_id=current_user.tenant_id,
            user_id=user_id,
            db=db
        )
    return [
        ClassScheduleResponse.model_validate(schedule, from_attributes=True)
        for schedule in schedules
    ]



@router.patch(
    "/institutions/classes/{class_code}/schedules/{schedule_id}",
    status_code=status.HTTP_200_OK,
    response_model=ClassScheduleResponse
)
async def update_class_schedule_endpoint(
    class_code: str,
    schedule_id: int,
    updated_data: ClassScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("class:management"))
):

    schedule = await update_class_schedule(
        db=db,
        tenant_id=current_user.tenant_id,
        class_code=class_code,
        updated_data=updated_data,
        schedule_id=schedule_id
    )
    class_ = await get_basic_class(db=db, tenant_id=current_user.tenant_id, class_code=class_code)
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="schedule_updated",
        message=f"Class schedule updated: {class_.class_or_year_or_name} (section: {class_.section})"
    )
    return ClassScheduleResponse.model_validate(schedule, from_attributes=True)


@router.delete(
    "/institutions/classes/{class_code}/schedules/{schedule_id}",
    status_code=status.HTTP_200_OK
)
async def delete_class_schedule_endpoint(
    class_code: str,
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("class:management"))
):

    class_ = await get_basic_class(db=db, tenant_id=current_user.tenant_id, class_code=class_code)
    result = await delete_class_schedule(
        db=db,
        tenant_id=current_user.tenant_id,
        class_code=class_code,
        schedule_id=schedule_id
    )
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="schedule_deleted",
        message=f"Class schedule deleted: {class_.class_or_year_or_name} (section: {class_.section})"
    )
    return result
