from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from ..models.institution_model import ExamSeatingDB
from typing import List
from ..core.database import get_db
from ..schemas.institution_schema import (
    CreateClassRoom,
    ClassRoomResponse,
    UpdateClassRoom,
)
from ..crud.exam_result_crud import (
    create_class_room,
    get_class_room,
    update_class_room,
    delete_class_room,
    generate_seating_arrangement,
    get_seating_by_classroom
)
from ..schemas.user_schema import CurrentUserResponse
from ..deps import require_permission
from ..schemas.exam_result_schema import SeatingResponse,ClassRoomAndClassCodes

router = APIRouter()


# ==================== CLASSROOM ROUTES ====================

@router.post(
    "/institutions/classrooms",
    response_model=ClassRoomResponse,
    status_code=status.HTTP_201_CREATED
)
async def create_classroom_endpoint(
    class_data: CreateClassRoom,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("exam:full_management"))
):
    """
    Create a new classroom.

    """
    classroom = await create_class_room(
        tenant_id=current_user.tenant_id,
        class_data=class_data,
        db=db
    )
    return classroom


@router.get(
    "/institutions/classrooms",
    response_model=List[ClassRoomResponse],
    status_code=status.HTTP_200_OK
)
async def get_classrooms_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("exam:full_management"))
):
    """
    Get all classrooms for an institution.

    """
    classrooms = await get_class_room(tenant_id=current_user.tenant_id, db=db)
    return classrooms


@router.patch(
    "/institutions/classrooms/{classroom_id}",
    response_model=ClassRoomResponse,
    status_code=status.HTTP_200_OK
)
async def update_classroom_endpoint(
    classroom_id: int,
    class_data: UpdateClassRoom,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("exam:full_management"))
):
    """
    Update a classroom.
    
    """
    class_data.id = classroom_id
    
    classroom = await update_class_room(
        tenant_id=current_user.tenant_id,
        class_data=class_data,
        db=db
    )
    return classroom


@router.delete(
    "/institutions/classrooms/{classroom_id}",
    status_code=status.HTTP_200_OK
)
async def delete_classroom_endpoint(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("exam:full_management"))
):
    """
    Delete a classroom.

    """
    result = await delete_class_room(
        tenant_id=current_user.tenant_id,
        class_room_id=classroom_id,
        db=db
    )
    return result


# ==================== SEATING ARRANGEMENT ROUTES ====================

@router.post(
    "/institutions/seating-arrangements",
    status_code=status.HTTP_201_CREATED
)
async def generate_seating_endpoint(
    class_data: ClassRoomAndClassCodes,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("exam:full_management"))
):
    """
    Generate exam seating arrangement.

    """
    result = await generate_seating_arrangement(tenant_id=current_user.tenant_id, db=db, class_room_id=class_data.class_room_id, class_codes=class_data.class_codes)
    return result


@router.get(
    "/institutions/classrooms/{classroom_id}/seating-arrangements",
    response_model=List[SeatingResponse],
    status_code=status.HTTP_200_OK
)
async def get_seating_endpoint(
    classroom_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("exam:full_management"))
):
    """
    Get seating arrangement for a classroom.
 
    """
    seating = await get_seating_by_classroom(
        tenant_id=current_user.tenant_id,
        db=db,
        classroom_id=classroom_id
    )
    return seating
