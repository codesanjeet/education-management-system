from fastapi import APIRouter, status, Depends, Query,HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..schemas.user_schema import CurrentUserResponse,UsersBasicResponse
from ..schemas.student_schema import StudentCreate, StudentResponse, StudentBasicResponse, StudentUpdate,StudentSelfUpdate,StudentDashboardResponse
from ..crud.student_curd import (
    create_student,
    get_student_full,
    get_student_all,
    update_student,
    create_student_multi,get_deleted_student,get_basic_student_data_by_id,get_financial_data_by_id
)
from .route_permissions import  STUDENT_READ_PERMISSIONS
from app.crud.attendance_crud import get_student_attendance_summary
from app.crud.class_crud import get_today_class_schedule
from ..crud.dashboard_crud import create_recent_activity_log
from typing import List
import logging
from ..crud.user_fun import mark_as_deleted_user
from ..deps import require_any_permission, require_permission, require_permission_or_owner,get_current_user
from ..core.config import settings
from ..services.email import send_activation_email
from secrets import token_urlsafe
from datetime import datetime, timedelta
from ..schemas.user_schema import CurrentUserResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/institutions/students", status_code=status.HTTP_201_CREATED)
async def create_student_endpoint(
    student_data: StudentCreate,
    class_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("student:create"))
):
    """Create a single student with activation email."""
    
    activation_expires = datetime.utcnow() + timedelta(days=21)
    
    activation_token = token_urlsafe(32)
    result = await create_student(
        db=db,
        tenant_id=current_user.tenant_id,
        student_data=student_data,
        activation_expires=activation_expires,
        class_code=class_code,
        activation_token = activation_token
    )
    
    
    activation_link = f"{settings.FRONTEND_URL}/activate?token={activation_token}"
    
    try:
        send_activation_email(
            to=result["email"],
            user_name=result["user_name"],
            activation_link=activation_link
        )
    except Exception as e:
        logger.error(f"Failed to send activation email: {e}")

    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="user_created",
        message=f"Student created: {result['first_name']} {result['last_name']} ({result['email']})"
    )
    
    return {
        "success": True,        
        "message": "Student created successfully",
        "roll_number": result["roll_number"]
    }




@router.post("/institutions/students/bulk", status_code=status.HTTP_201_CREATED)
async def create_students_bulk_endpoint(
    students: List[StudentCreate],
    class_code: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("student:create","bulk:entry"))
):
    """Bulk create students. Maximum 250 per request."""
    
    if not students:
        raise ValueError("Students list cannot be empty")
    
    if len(students) > 250:
        raise ValueError("Maximum 250 students per bulk request")

    activation_expires = datetime.utcnow() + timedelta(days=21)
    
    created_students = await create_student_multi(
        db=db,
        students=students,
        tenant_id=current_user.tenant_id,
        class_code=class_code,
        activation_expires=activation_expires
    )

    response_list = [
        {
            "roll_number": student.roll_number,
            "class_code": class_code,
            "email": student.user.email,
            "user_name": student.user.user_name,
            "first_name": student.user.first_name,
            "last_name": student.user.last_name,
        }
        for student in created_students
    ]

    logger.info(f"Bulk created {len(response_list)} students for tenant {current_user.tenant_id}")

    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="user_created_bulk",
        message=f"Student created in bulk: {len(created_students)} students created"
    )

    return {
        "success": True,
        "message": f"Successfully created {len(response_list)} students",
        "total_created": len(response_list),
        "students": response_list
    }

@router.get(
    "/institutions/students/classes/{class_code}",
    status_code=status.HTTP_200_OK,
    response_model=List[StudentBasicResponse]
)
async def get_students_by_class_endpoint(
    class_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_any_permission(*STUDENT_READ_PERMISSIONS))
) -> List[StudentBasicResponse]:
    """Get all students in a specific class."""
    return await get_student_all(db, current_user.tenant_id, class_code)



@router.get(
    "/institutions/students/me/dashboard",
    status_code=status.HTTP_200_OK,
    response_model=StudentDashboardResponse
)
async def get_student_dashboard_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
) -> dict:
    
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Not a student")
    """Get detailed information for a single student."""
    now = datetime.utcnow()
    month = now.month
    year = now.year
    basic_profile_data = await get_basic_student_data_by_id(user_id=current_user.id, db=db)
    todays_schedule =await get_today_class_schedule(user_id=current_user.id, tenant_id=current_user.tenant_id,db=db)
    attendance_summary = await get_student_attendance_summary(user_id=current_user.id,tenant_id=current_user.tenant_id ,month=month, year=year, db=db)
    finanacial_data = await get_financial_data_by_id(db=db, user_id=current_user.id)


    return {
        "basic_data" : basic_profile_data,
        "today_schedule": todays_schedule,
        "attendance_summary": attendance_summary,
        "balance_due": finanacial_data.balance_due,
        "total_paid": finanacial_data.total_paid
    }

@router.get(
    "/institutions/students/deleted",
    status_code=status.HTTP_200_OK,
    response_model=List[UsersBasicResponse]
)
async def get_deleted_student_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("recycle_bin:user"))
):

    result = await get_deleted_student(db=db, tenant_id=current_user.tenant_id)
    return result



@router.patch("/institutions/students/{user_id}")
async def update_student_endpoint(
    user_id: int,
    update_data: StudentUpdate, 
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("student:update"))
):
    if access["is_owner"] and not access["has_permission"]:
        safe = StudentSelfUpdate(**update_data.model_dump(exclude_unset=True))
        final = StudentUpdate(**safe.model_dump(exclude_unset=True))
    else:
        final = update_data 

    update_student_result = await update_student(db, access["current_user"].tenant_id, user_id, final) 

    if access["has_permission"]:
        await create_recent_activity_log(
            db=db,
            tenant_id=access["current_user"].tenant_id,
            user_id=access["current_user"].id,
            action_type="user_updated",
            message=f"Student updated: {update_student_result['first_name']} {update_student_result['last_name']}"
        )

    return update_student_result




@router.delete("/institutions/students/{user_id}", status_code=status.HTTP_200_OK)
async def soft_delete_student_endpoint(
    restore: bool,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_any_permission("recycle_bin:user","student:delete"))
):
    """Soft delete a student (mark as deleted)."""
    
    user = await mark_as_deleted_user(db, current_user.tenant_id, user_id, restore=restore)
    if not restore:
        await create_recent_activity_log(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action_type="user_deleted",
            message=f"Student deleted: {user.first_name} {user.last_name} ({user.email})"
        )
    else:        
        await create_recent_activity_log(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action_type="user_restored",
            message=f"Student restored: {user.first_name} {user.last_name} ({user.email})"
        )
    
    return {
        "success": True,
        "message": "Student marked as deleted successfully",
        "user_id": user_id
    }



@router.get(
    "/institutions/students/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=StudentResponse
)
async def get_student_endpoint(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("student:view"))
) -> StudentResponse:
    """Get detailed information for a single student."""
  
    return await get_student_full(db, access["current_user"].tenant_id, user_id)

