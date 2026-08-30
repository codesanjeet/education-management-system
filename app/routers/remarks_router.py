from fastapi import APIRouter, status, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..schemas.remarks_schema import RemarkCreate, RemarkUpdate, RemarkResponse  ,  DisciplinaryRecordCreate,DisciplinaryRecordUpdate, DisciplinaryRecordResponse
from ..schemas.user_schema import CurrentUserResponse
from ..crud.remarks_crud import (
    create_remark,
    get_all_remarks,
    get_remarks_by_target,
    update_remark,
    delete_remark,
#   diciplinary record imports
    create_disciplinary_record,
    get_all_disciplinary_records,
    get_disciplinary_records_by_student,
    get_disciplinary_record_by_recorder,
    update_disciplinary_record,

)
from ..deps import get_current_user

from typing import List
import logging
from ..deps import require_permission
from ..crud.dashboard_crud import create_recent_activity_log
router = APIRouter()
logger = logging.getLogger(__name__)


# ==================== REMARKS ROUTES ====================

@router.post(
    "/institutions/remarks",
    status_code=status.HTTP_201_CREATED,
    response_model=RemarkResponse,
)
async def create_remark_endpoint(
    request: RemarkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    remark = await create_remark(
            db=db,
            tenant_id=current_user.tenant_id,
            given_by_id=current_user.id,
            given_by_role=current_user.role,
            remark_data=request,
        )

    return RemarkResponse.model_validate(remark, from_attributes=True)
 
@router.get(
    "/institutions/remarks",
    status_code=status.HTTP_200_OK,
    response_model=List[RemarkResponse],
)
async def get_all_remarks_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    """Returns only remarks created by the current user."""
    remarks = await get_all_remarks(
            db=db,
            tenant_id=current_user.tenant_id,
            current_user_id=current_user.id,
        )
    return [RemarkResponse.model_validate(r, from_attributes=True) for r in remarks]

@router.get(
    "/institutions/remarks/target",
    status_code=status.HTTP_200_OK,
    response_model=List[RemarkResponse],
)
async def get_remarks_by_target_endpoint(
    target_id: int = Query(..., description="Target entity ID"),
    target_type: str = Query(..., description="Target type e.g. 'student', 'class'"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    """Returns remarks for a specific target created by the current user."""

    remarks = await get_remarks_by_target(
            db=db,
            tenant_id=current_user.tenant_id,
            target_id=target_id,
            target_type=target_type,
            current_user_id=current_user.id,
        )
    return [RemarkResponse.model_validate(r, from_attributes=True) for r in remarks]


@router.patch(
    "/institutions/remarks/{remark_id}",
    status_code=status.HTTP_200_OK,
    response_model=RemarkResponse,
)
async def update_remark_endpoint(
    remark_id: int,
    updated_data: RemarkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):

    remark = await update_remark(
            db=db,
            tenant_id=current_user.tenant_id,
            remark_id=remark_id,
            updated_data=updated_data,
            current_user_id=current_user.id,
        )
    return RemarkResponse.model_validate(remark, from_attributes=True)


@router.delete(
    "/institutions/remarks/{remark_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_remark_endpoint(
    remark_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    
    result = await delete_remark(
            db=db,
            tenant_id=current_user.tenant_id,
            remark_id=remark_id,
            current_user_id=current_user.id,
        )
    return result













# ==================== DISCIPLINARY RECORD ROUTES ====================

@router.post(
    "/institutions/disciplinary-records",
    status_code=status.HTTP_201_CREATED,
    response_model=DisciplinaryRecordResponse,
)
async def create_disciplinary_record_endpoint(
    request: DisciplinaryRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("discipline:management")),
):

    record = await create_disciplinary_record(
            db=db,
            tenant_id=current_user.tenant_id,
            record_data=request,
            creator_user_id = current_user.id
        )
    await create_recent_activity_log(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action_type="disciplinary_record_created",
            message=f"Disciplinary record created for student id: {record.student_id} (level: {record.incident_level})",
        )
    return DisciplinaryRecordResponse.model_validate(record, from_attributes=True)
 

@router.get(
    "/institutions/disciplinary-records",
    status_code=status.HTTP_200_OK,
    response_model=List[DisciplinaryRecordResponse],
)
async def get_all_disciplinary_records_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("discipline:management")),
):
    """Returns all disciplinary records across the institution. Staff/admin only."""

    records = await get_all_disciplinary_records(
            db=db,
            tenant_id=current_user.tenant_id,
        )
    return [DisciplinaryRecordResponse.model_validate(r, from_attributes=True) for r in records]

@router.get(
    "/institutions/students/{student_id}/disciplinary-records",
    status_code=status.HTTP_200_OK,
    response_model=List[DisciplinaryRecordResponse],
)
async def get_disciplinary_records_by_student_endpoint(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    """Returns all disciplinary records for a specific student."""
    
    records = await get_disciplinary_records_by_student(
            db=db,
            tenant_id=current_user.tenant_id,
            student_id=student_id,
        )
    return [DisciplinaryRecordResponse.model_validate(r, from_attributes=True) for r in records]


@router.get(
    "/institutions/disciplinary-records/recorded-by/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=list[DisciplinaryRecordResponse],
)
async def get_disciplinary_record_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):

    records = await get_disciplinary_record_by_recorder(
            db=db,
            tenant_id=current_user.tenant_id,
            recorder_id = user_id,
        )
    return [DisciplinaryRecordResponse.model_validate(r, from_attributes=True) for r in records]


@router.patch(
    "/institutions/disciplinary-records/{record_id}",
    status_code=status.HTTP_200_OK,
    response_model=DisciplinaryRecordResponse,
)
async def update_disciplinary_record_endpoint(
    record_id: int,
    updated_data: DisciplinaryRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("discipline:management")),
):

    record = await update_disciplinary_record(
            db=db,
            tenant_id=current_user.tenant_id,
            record_id=record_id,
            updated_data=updated_data,
        )

    return DisciplinaryRecordResponse.model_validate(record, from_attributes=True)

