from fastapi import APIRouter, status, Depends, Query,HTTPException,UploadFile,File
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from ..schemas.student_schema import StudentSelfUpdate
from ..core.database import get_db
from ..schemas.staff_schema import (
    TeacherCreate, PrincipalCreate, AdminCreate, OtherStaffCreate,
    StaffBasicResponse, StaffResponse, AdminUpdate, PrincipalUpdate,
    TeacherUpdate, OtherStaffUpdate, TeacherAvailabilityRequest
)
from .route_permissions import STAFF_READ_PERMISSIONS
from ..crud.student_curd import update_student
from ..schemas.user_schema import  UserUpdate,CurrentUserResponse,UsersBasicResponse,CurrentUserResponse
from ..crud.staff_crud import (
    create_teacher, create_other_staff, create_principal, create_admin,
    get_staff_all, get_staff_by_id, get_staff_full_by_id, update_staff_by_id, get_available_staff,get_deleted_staff
)
from ..services.profile_image import(upload_profile_image,get_profile_signed_url)
from ..crud.user_fun import mark_as_deleted_user
from ..crud.dashboard_crud import create_recent_activity_log
from typing import List,Optional
import logging
from ..deps import  require_permission, require_permission_or_owner, require_any_permission,get_current_user
from secrets import token_urlsafe
from ..services.email import send_activation_email
from datetime import datetime, timedelta
from ..core.config import settings
from ..models.user_model import UserRoleEnum
from ..crud.permission_crud import assign_permissions_to_user
from ..schemas.permission_accod_to_role import  DEFAULT_PERMISSIONS_PRINCIPAL as principal_perm,DEFAULT_PERMISSIONS_TEACHER as teacher_perm ,DEFAULT_PERMISSIONS_ADMIN as admin_perm
router = APIRouter()
logger = logging.getLogger(__name__)

ACTIVATION_EXPIRE_HOURS = 504


# ==================== TEACHER ROUTES ====================

@router.post(
    "/institutions/staff/teachers",
    status_code=status.HTTP_201_CREATED
)
async def create_teacher_endpoint(
    teacher_data: TeacherCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("staff:create"))
):
    """
    Create a single teacher.
    """

    activation_expires = datetime.utcnow() + timedelta(hours=ACTIVATION_EXPIRE_HOURS)

    user = await create_teacher(
        db=db,
        tenant_id=current_user.tenant_id,
        teacher_data=teacher_data,
        activation_expires=activation_expires,
        bulk=False
    )
    Permission_key = [p[0] for p in teacher_perm]
    await assign_permissions_to_user(
            db = db,
            user_id=user.id,
            permissions= Permission_key,
            granted_by=current_user.id

        )
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="user_created",
        message=f"Teacher created: {user.first_name} {user.last_name} ({user.email})"
    )
    
    # Email is sent inside the create_teacher function, due to single function handling both single and bulk creation, and for that we need to run the loop
    return {
        "message": "Teacher created successfully",
        "email": user.email
    }


@router.post(
    "/institutions/staff/teachers/bulk",
    status_code=status.HTTP_201_CREATED
)
async def create_teachers_bulk_endpoint(
    teacher_data: List[TeacherCreate],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("staff:create","bulk:entry"))
):
    """
    Bulk create teachers.
    """
    activation_expires = datetime.utcnow() + timedelta(hours=ACTIVATION_EXPIRE_HOURS)
    if len(teacher_data) > 200:
        raise ValueError("Maximum 200 teachers per bulk request")
    teachers = await create_teacher(
        db=db,
        tenant_id=current_user.tenant_id,
        teacher_data=teacher_data,
        activation_expires=activation_expires,
        bulk=True
    )
    Permission_key = [p[0] for p in teacher_perm]
    for teacher in teachers:
        await assign_permissions_to_user(
                db = db,
                user_id=teacher.id,
                permissions= Permission_key,
                granted_by=current_user.id

            )
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="user_created_bulk",
        message=f"Teacher created in bulk: {len(teachers)} teachers created"
    )
    
    return {
        "message": "Teachers created successfully",
        "count": len(teachers),
    }



@router.patch(
    "/institutions/staff/teachers/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=StaffResponse
)
async def update_teacher_endpoint(

    user_id: int,
    updated_role_data: TeacherUpdate,
    updated_user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("staff:update"))
):
    """
    Update teacher information by user_id.

    """

    if access["is_owner"] and not access["has_permission"]:
        updated_role_data.department = None  
        updated_role_data.subjects_taught = None

    result = await update_staff_by_id(
        db=db,
        tenant_id=access["current_user"].tenant_id,
        user_id=user_id,
        updated_role_data=updated_role_data,
        updated_user_data=updated_user_data
    )
    if access["has_permission"]:
        await create_recent_activity_log(
            db=db,
            tenant_id=access["current_user"].tenant_id,
            user_id=access["current_user"].id,
            action_type="user_updated",
            message=f"Teacher updated: {result['user_data']['first_name']} {result['user_data']['last_name']} ({result['user_data']['email']})"
        )
    
    return StaffResponse(**result)


# ==================== OTHER STAFF ROUTES ====================

@router.post(
    "/institutions/staff/other",
    status_code=status.HTTP_201_CREATED
)
async def create_other_staff_endpoint(
    other_staff_data: OtherStaffCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("staff:create"))
):
    """
    Create a single other staff member.
    
    """
    activation_expires = datetime.utcnow() + timedelta(hours=ACTIVATION_EXPIRE_HOURS)

    user = await create_other_staff(
        db=db,
        tenant_id=current_user.tenant_id,
        other_staff_data=other_staff_data,
        activation_expires=activation_expires,
        bulk=False
    )
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="user_created",
        message=f"Other staff member created: {user.first_name} {user.last_name} ({user.email})"
    )
    # Email is sent inside the create_other_staff function, due to single function handling both single and bulk creation, and for that we need to run the loop
    return {
        "message": "Staff member created successfully",
        "email": user.email
    }


@router.post(
    "/institutions/staff/other/bulk",
    status_code=status.HTTP_201_CREATED
)
async def create_other_staff_bulk_endpoint(
    other_staff_data: List[OtherStaffCreate],
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("staff:create","bulk:entry"))
):
    """
    Bulk create other staff members.
     
    """
    activation_expires = datetime.utcnow() + timedelta(hours=ACTIVATION_EXPIRE_HOURS)
    if len(other_staff_data) > 250:
        raise ValueError("Maximum 250 other staff members per bulk request")  
    staff = await create_other_staff(
        db=db,
        tenant_id=current_user.tenant_id,
        other_staff_data=other_staff_data,
        activation_expires=activation_expires,
        bulk=True
    )
    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="user_created_bulk",
        message=f"Other staff members created in bulk: {len(staff)} staff members created"
    )
    
    return {
        "message": "Staff members created successfully",
        "count": len(staff),
    }



@router.patch(
    "/institutions/staff/others/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=StaffResponse
)
async def update_other_staff_endpoint(
    user_id: int,
    updated_role_data: OtherStaffUpdate,
    updated_user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("staff:update"))
):
    """
    Update other staff information by user_id.
    """

    if access["is_owner"] and not access["has_permission"]:
        updated_role_data.assigned_work = None  

    result = await update_staff_by_id(
        db=db,
        tenant_id=access["current_user"].tenant_id,
        user_id=user_id,
        updated_role_data=updated_role_data,
        updated_user_data=updated_user_data
    )
    if access["has_permission"]:
        await create_recent_activity_log(
            db=db,
            tenant_id=access["current_user"].tenant_id,
            user_id=access["current_user"].id,
            action_type="user_updated",
            message=f"{result['role_data']['assigned_work']} updated: {result['user_data']['first_name']} {result['user_data']['last_name']} ({result['user_data']['email']})"
        )
    
    return StaffResponse(**result)



# ==================== PRINCIPAL ROUTES ====================

@router.post(
    "/institutions/staff/principals",
    status_code=status.HTTP_201_CREATED
)
async def create_principal_endpoint(
    principal_data: PrincipalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("staff:create"))
):
    """
    Create a principal.
    
    """
    activation_expires = datetime.utcnow() + timedelta(hours=ACTIVATION_EXPIRE_HOURS)
    activation_token = token_urlsafe(32)
    
    user = await create_principal(
        db=db,
        tenant_id=current_user.tenant_id,
        role_data=principal_data.principal_data,
        user_data=principal_data.user_data,
        activation_token=activation_token,
        activation_expires=activation_expires
    )
    Permission_key = [p[0] for p in principal_perm]
    await assign_permissions_to_user(
            db = db,
            user_id=user.id,
            permissions= Permission_key,
            granted_by=current_user.id

        )
    
    activation_link = f"{settings.FRONTEND_URL}/activate?token={activation_token}"
    
    try:
        send_activation_email(
            to=user.email,
            user_name=user.user_name,
            activation_link=activation_link
        )
    except Exception as e:
        logger.error(f"Failed to send activation email: {e}")

    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="user_created",
        message=f"Principal created: {user.first_name} {user.last_name} ({user.email})"
    )
    
    return {
        "message": "Principal created successfully",
        "email": user.email
    }



@router.patch(
    "/institutions/staff/principals/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=StaffResponse
)
async def update_principal_endpoint(
    user_id: int,
    updated_role_data: PrincipalUpdate,
    updated_user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("staff:update"))
):
    current_user = access["current_user"]
    is_owner = access["is_owner"]
    has_perm = access["has_permission"]

    # must be admin with permission, OR the owner themselves
    if not is_owner and not (has_perm and current_user.role == UserRoleEnum.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins with staff:update permission can update a principal"
        )

    # owner without admin permission — restrict sensitive fields
    if is_owner and not (has_perm and current_user.role == "admin"):
        updated_role_data.assigned_institution = None
        updated_role_data.department = None

    result = await update_staff_by_id(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        updated_role_data=updated_role_data,
        updated_user_data=updated_user_data
    )
    if has_perm:
        await create_recent_activity_log(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action_type="user_updated",
            message=f"Principal updated: {result['user_data']['first_name']} {result['user_data']['last_name']} ({result['user_data']['email']})"
        )

    return StaffResponse(**result)



# ==================== ADMIN ROUTES ====================

@router.post(
    "/institutions/admins",
    status_code=status.HTTP_201_CREATED
)
async def create_admin_endpoint(
    admin_data: AdminCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("staff:create"))
):
    """
    Create an admin.
  
    """
    if current_user.role != UserRoleEnum.ADMIN.value:
            raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins with staff:create permission can create an admin"
        )
    activation_expires = datetime.utcnow() + timedelta(hours=ACTIVATION_EXPIRE_HOURS)
    activation_token = token_urlsafe(32)
    
    user = await create_admin(
        db=db,
        user_data=admin_data.user_data,
        tenant_id=current_user.tenant_id,
        role_data=admin_data.admin_data,
        activation_expires=activation_expires,
        activation_token=activation_token
    )
    Permission_key = [p[0] for p in admin_perm]
    await assign_permissions_to_user(
            db = db,
            user_id=user.id,
            permissions= Permission_key,
            granted_by=current_user.id

        )

    
    activation_link = f"{settings.FRONTEND_URL}/activate?token={activation_token}"
    
    try:
        send_activation_email(
            to=user.email,
            user_name=user.user_name,
            activation_link=activation_link
        )
    except Exception as e:
        logger.error(f"Failed to send activation email: {e}")

    await create_recent_activity_log(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="admin_created",
        message=f"Admin created: {user.first_name} {user.last_name} ({user.email})"
    )
    
    return {
        "message": "Admin created successfully",
        "email": user.email
    }


@router.patch(
    "/institutions/admins/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=StaffResponse
)
async def update_admin_endpoint(
    user_id: int,
    updated_role_data: AdminUpdate,
    updated_user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("staff:update"))
):
    """
    Update admin information by user_id.
    """

    current_user = access["current_user"]
    is_owner = access["is_owner"]
    has_perm = access["has_permission"]

    if not is_owner and not (has_perm and current_user.role == UserRoleEnum.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins with staff:update permission can update a admin"
        )
    result = await update_staff_by_id(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=user_id,
        updated_role_data=updated_role_data,
        updated_user_data=updated_user_data
    )
    if has_perm:
        await create_recent_activity_log(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action_type="admin_updated",
            message=f"Admin updated: {result['user_data']['first_name']} {result['user_data']['last_name']} ({result['user_data']['email']})"
        )
    
    return StaffResponse(**result)




# ==================== GENERAL STAFF ROUTES ====================

@router.get(
    "/institutions/staff",
    status_code=status.HTTP_200_OK,
    response_model=List[StaffBasicResponse]
)
async def get_all_staff_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_any_permission(*STAFF_READ_PERMISSIONS))
):
    """
    Get all staff members.
    """
    staff = await get_staff_all(db=db, tenant_id=current_user.tenant_id)
    return staff

# getting the deleted user 

@router.get(
    "/institutions/staff/deleted",
    status_code=status.HTTP_200_OK,
    response_model=List[UsersBasicResponse]

)
async def get_deleted_staff_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_any_permission("recycle_bin:user"))
):

    result = await get_deleted_staff(db=db, tenant_id=current_user.tenant_id)
    return result


@router.get(
    "/institutions/staff/{user_id}",
    status_code=status.HTTP_200_OK,
    response_model=StaffResponse
)
async def get_staff_endpoint(
    user_id: int,
    full_data: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("staff:view"))
):
    """
    Get staff member details by user_id.

    **Query Param**: ?full_data=true
    """
    if access["is_owner"] or access["has_permission"]: 
        if full_data:
            staff = await get_staff_full_by_id(db=db, tenant_id=access["current_user"].tenant_id, user_id=user_id)
        else:
            staff = await get_staff_by_id(db=db, tenant_id=access["current_user"].tenant_id, user_id=user_id)
        
        return staff



@router.post(
    "/institutions/staff/available",
    status_code=status.HTTP_200_OK,
    response_model=List[StaffBasicResponse]
)
async def get_available_staff_endpoint(
    required_data: TeacherAvailabilityRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("class:management"))
):
    """
    Check staff availability for time slots.

    """
    staff = await get_available_staff(
        db=db,
        tenant_id=current_user.tenant_id,
        start_time=required_data.start_time,
        end_time=required_data.end_time,
        days=required_data.days,
        subject=required_data.subject
    )
    return staff


@router.delete(
    "/institutions/staff/{user_id}",
    status_code=status.HTTP_200_OK
)
async def delete_staff_endpoint(
    user_id: int,
    restore: bool,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("recycle_bin:user","staff:delete"))
):
    """
    Soft delete an staff by user_id.
    """
    user = await mark_as_deleted_user(db, current_user.tenant_id, user_id, restore)
    if not restore:
        await create_recent_activity_log(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action_type="staff_deleted",
            message=f"Staff deleted: {user.first_name} {user.last_name} ({user.email})"
        )
    else:
        await create_recent_activity_log(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action_type="staff_restored",
            message=f"Staff restored: {user.first_name} {user.last_name} ({user.email})"
        )
    
    return {
        "message": "Staff marked as deleted successfully",
        "user_id": user_id
    }



@router.put("/institutions/users/complete-profile")
async def complete_profile(
    staff_user_data: UserUpdate,
    student_data: Optional[StudentSelfUpdate] = None,
    staff_role_data: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
):
    if current_user.is_profile_complete:
        return {"message": "Profile already completed","status": "no_action"}

    if current_user.role == "student":
        if not student_data:
            raise HTTPException(400, "Student data required")

        user = await update_student(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            update_data=student_data,
            mark_profile_complete=True
        )
    else:
        if not staff_role_data:
            raise HTTPException(400, "Staff data required")

        # Dynamic validation based on role
        try:
            if current_user.role == "teacher":
                validated_data = TeacherUpdate(**staff_role_data)

            elif current_user.role == "principal":
                validated_data = PrincipalUpdate(**staff_role_data)

            elif current_user.role == "admin":
                validated_data = AdminUpdate(**staff_role_data)

            else:
                validated_data = OtherStaffUpdate(**staff_role_data)

        except ValidationError as e:
            raise HTTPException(
                status_code=422,
                detail=e.errors()
            )
        user = await update_staff_by_id(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            updated_role_data=validated_data,
            updated_user_data= staff_user_data,
            mark_profile_complete=True
        )

    return {"message": "Profile completed successfully"}


# profile image
@router.post("/institutions/users/profile-image")
async def upload_profile_image_endpoint(
    file: UploadFile= File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
):

        result = await upload_profile_image(
            file=file,
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            db=db,
        )
        return {
            "message": "Profile image uploaded successfully",
            **result
        }


@router.get("/institutions/users/{user_id}/profile-image")
async def get_profile_image_endpoint(
    user_id: int,
    image_type: str = Query("thumb", alias="type", enum=["thumb", "main"]),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    """
    Return a 302 redirect to a 1-hour R2 presigned URL for the requested
    image derivative.
 
    Using a redirect (rather than proxying bytes through FastAPI) means:
      • Zero bandwidth through your server — R2 serves the bytes directly.
      • The client caches the redirect target for up to the TTL.
      • Your server stays stateless and fast.
 
    The caller must be authenticated — profile images are private.
    """
    url = await get_profile_signed_url(
            db=db,
            tenant_id=str(current_user.tenant_id),
            user_id=user_id,
            image_type=image_type,
        )

    # 302 → client follows to R2; add Cache-Control so the browser doesn't
    # re-hit this endpoint on every render (safe up to the presign TTL).
    return RedirectResponse(
        url=url,
        status_code=302,
        headers={"Cache-Control": "private, max-age=3300"},
        # 3300 s ≈ 55 min — slightly under the 60-min presign TTL so the
        # client re-fetches before the URL actually expires.
    )
