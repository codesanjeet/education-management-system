from sqlalchemy import select, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.staff_schema import (
    TeacherCreate, PrincipalCreate, OtherStaffCreate, AdminCreate,
    StaffBasicResponse, StaffResponse, TeacherBasicResponse,
    PrincipalBasicResponse, AdminBasicResponse, OtherStaffBasicResponse,
    OtherStaffResponse, AdminResponse, TeacherResponse, PrincipalResponse,
    AdminUpdate, TeacherUpdate, OtherStaffUpdate, PrincipalUpdate
)
from app.schemas.user_schema import UserCreate, UsersBasicResponse, UsersResponse, UserUpdate,UserRoleEnum
from app.models.role_specific.teacher_model import TeacherDB
from app.models.role_specific.principal_model import PrincipalDB
from app.models.role_specific.admin_model import AdminDB
from app.models.role_specific.other_staff_model import OtherStaffDB
from app.models.user_model import UserDB, UserSecurityDB
from sqlalchemy.orm import selectinload
from app.models.permission_model import UserPermissionDB
from app.models.role_specific.staff_sub_models import StaffSalaryDB
from typing import Optional, List, Union
from ..core.exceptions import (
    UserAlreadyExistsError, DatabaseError, UserNotFoundException,
    InstitutionNotFoundError, InvalidStaffRoleError,InvalidImageError,ImageTooLargeError,FileUploadError
)
from app.schemas.permission_schema import PermissionDetail
from .user_fun import generate_unique_username,get_basic_user_by_id
from ..models.institution_model import InstitutionDB
from ..models.classes_model import ClassScheduleDB, ClassDB
from datetime import datetime
from secrets import token_urlsafe
from ..core.config import settings
from ..services.email import send_activation_email
import logging
logger = logging.getLogger(__name__)


# ==================== HELPER FUNCTIONS ====================

async def _validate_institution_exists(db: AsyncSession, tenant_id: str) -> int:
    """Validate institution exists and return its ID."""
    inst_query = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_query.scalar_one_or_none()
    
    if not institution_id:
        logger.warning(f"Institution not found for tenant: {tenant_id}")
        raise InstitutionNotFoundError("Institution not found")
    
    return institution_id


async def _check_email_exists(db: AsyncSession, email: str, tenant_id: str) -> bool:
    """Check if email already exists for this tenant."""
    existing = await db.execute(
        select(exists().where(
            and_(
                UserDB.email == email.lower(),
                UserDB.tenant_id == tenant_id
            )
        ))
    )
    return existing.scalar()


async def _create_staff_user(
    db: AsyncSession,
    user_data: UserCreate,
    institution_id: int,
    tenant_id: str,
    activation_token: str,
    activation_expires: datetime
) -> UserDB:
    """Create base user object for staff."""
    [username] = await generate_unique_username(
        db=db,
        names=[(user_data.first_name, user_data.last_name)]
    )
    
    db_user = UserDB(
        **user_data.model_dump(),
        tenant_id=tenant_id,
        user_name=username,
        institution_id=institution_id
    )
    
    db_user.security = UserSecurityDB(
        activation_token_expires=activation_expires,
        activation_token=activation_token
    )
    db_user.staff_salary = StaffSalaryDB()
    
    return db_user



# ==================== CREATE TEACHER ====================

async def create_teacher(
    db: AsyncSession,
    teacher_data: Union[TeacherCreate, List[TeacherCreate]],
    tenant_id: str,
    activation_expires: datetime,
    bulk: bool = False
):
    """Create teacher(s) - supports both single and bulk creation."""
    
    # Normalize input
    is_single = not isinstance(teacher_data, list)
    teachers_list = [teacher_data] if is_single else teacher_data
    
    if not teachers_list:
        raise ValueError("Teacher list cannot be empty")
    
    if not bulk and len(teachers_list) > 1:
        raise ValueError("Multiple teachers provided but bulk=False")
    
    # Validate institution
    institution_id = await _validate_institution_exists(db, tenant_id)
    
    # Check for duplicate emails in request
    emails = [t.user_data.email.lower() for t in teachers_list]
    if len(set(emails)) != len(emails):
        raise UserAlreadyExistsError("Duplicate emails found in submission")
    
    # Check for existing emails in database
    existing_check = await db.execute(
        select(UserDB.email).where(
            and_(
                UserDB.email.in_(emails),
                UserDB.tenant_id == tenant_id
            )
        )
    )
    existing_emails = [row[0] for row in existing_check.all()]
    
    if existing_emails:
        logger.warning(f"{len(existing_emails)} existing emails found")
        raise UserAlreadyExistsError(
            f"{len(existing_emails)} email(s) already registered"
        )
    
    # Create teachers
    created_teachers = []
    
    try:
        for item in teachers_list:
            activation_token = token_urlsafe(32)
            
            # Create user
            db_user = await _create_staff_user(
                db=db,
                user_data=item.user_data,
                institution_id=institution_id,
                tenant_id=tenant_id,
                activation_token=activation_token,
                activation_expires=activation_expires
            )
            
            # Create teacher profile
            db_teacher = TeacherDB(**item.teacher_data.model_dump())
            db_user.teacher = db_teacher
            
            db.add(db_user)
            created_teachers.append(db_user)
 

            try:
                activation_link = f"{settings.FRONTEND_URL}/activate?token={activation_token}"
                send_activation_email(
                        to=db_user.email,
                        user_name=db_user.user_name,
                        activation_link=activation_link
                    )
            except Exception as e:
                    logger.error(f"Failed to send activation email: {e}")
        
        await db.commit()
        
        # Refresh all
        for teacher in created_teachers:
            await db.refresh(teacher)
        
        return created_teachers if bulk or not is_single else created_teachers[0]
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating teacher(s): {e}", exc_info=True)
        raise DatabaseError("Unable to create teacher(s)")


# ==================== CREATE OTHER STAFF ====================

async def create_other_staff(
    db: AsyncSession,
    other_staff_data: Union[OtherStaffCreate, List[OtherStaffCreate]],
    tenant_id: str,
    activation_expires: datetime,
    bulk: bool = False
):
    """Create other staff - supports both single and bulk creation."""
    
    # Normalize input
    is_single = not isinstance(other_staff_data, list)
    staff_list = [other_staff_data] if is_single else other_staff_data
    
    if not staff_list:
        raise ValueError("Staff list cannot be empty")
    
    if not bulk and len(staff_list) > 1:
        raise ValueError("Multiple staff provided but bulk=False")
    
    # Validate institution
    institution_id = await _validate_institution_exists(db, tenant_id)
    
    # Check for duplicate emails
    emails = [s.user_data.email.lower() for s in staff_list]
    if len(set(emails)) != len(emails):
        raise UserAlreadyExistsError("Duplicate emails found in submission")
    
    # Check existing emails
    existing_check = await db.execute(
        select(UserDB.email).where(
            and_(
                UserDB.email.in_(emails),
                UserDB.tenant_id == tenant_id
            )
        )
    )
    existing_emails = [row[0] for row in existing_check.all()]
    
    if existing_emails:
        logger.warning(f"{len(existing_emails)} existing emails found")
        raise UserAlreadyExistsError(
            f"{len(existing_emails)} email(s) already registered"
        )
    
    # Create staff
    created_staff = []
    
    try:
        for item in staff_list:
            activation_token = token_urlsafe(32)
            
            db_user = await _create_staff_user(
                db=db,
                user_data=item.user_data,
                institution_id=institution_id,
                tenant_id=tenant_id,
                activation_token=activation_token,
                activation_expires=activation_expires
            )
            
            db_other_staff = OtherStaffDB(**item.other_staff_data.model_dump())
            db_user.other_staff = db_other_staff
            
            db.add(db_user)
            created_staff.append(db_user)
            

            try:
                activation_link = f"{settings.FRONTEND_URL}/activate?token={activation_token}"
                send_activation_email(
                        to=db_user.email,
                        user_name=db_user.user_name,
                        activation_link=activation_link
                    )
            except Exception as e:
                    logger.error(f"Failed to send activation email: {e}")
        
        await db.commit()
        
        for staff in created_staff:
            await db.refresh(staff)
        
        return created_staff if bulk or not is_single else created_staff[0]
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating staff: {e}", exc_info=True)
        raise DatabaseError("Unable to create staff")


# ==================== CREATE PRINCIPAL ====================

async def create_principal(
    db: AsyncSession,
    user_data: UserCreate,
    role_data: PrincipalCreate,
    activation_token: str,
    activation_expires: datetime,
    tenant_id: str
):
    """Create a principal."""
    
    # Validate institution
    institution_id = await _validate_institution_exists(db, tenant_id)
    
    # Check email exists
    if await _check_email_exists(db, user_data.email, tenant_id):
        raise UserAlreadyExistsError(f"Email {user_data.email} already registered")
    
    try:
        db_user = await _create_staff_user(
            db=db,
            user_data=user_data,
            institution_id=institution_id,
            tenant_id=tenant_id,
            activation_token=activation_token,
            activation_expires=activation_expires
        )
        
        db_principal = PrincipalDB(**role_data.model_dump())
        db_user.principal = db_principal
        
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        
        return db_user
        
    except Exception as e:
        print("Actual error:", e)
        raise e


# ==================== CREATE ADMIN ====================

async def create_admin(
    db: AsyncSession,
    user_data: UserCreate,
    role_data: AdminCreate,
    activation_token: str,
    activation_expires: datetime,
    tenant_id: str
):
    """Create an admin."""
    
    # Validate institution
    institution_id = await _validate_institution_exists(db, tenant_id)
    
    # Check email exists
    if await _check_email_exists(db, user_data.email, tenant_id):
        raise UserAlreadyExistsError(f"Email {user_data.email} already registered")
    
    try:
        db_user = await _create_staff_user(
            db=db,
            user_data=user_data,
            institution_id=institution_id,
            tenant_id=tenant_id,
            activation_token=activation_token,
            activation_expires=activation_expires
        )
        
        db_admin = AdminDB(**role_data.model_dump())
        db_user.admin = db_admin
        
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        
        return db_user
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating admin: {e}", exc_info=True)
        raise DatabaseError("Unable to create admin")


# ==================== GET STAFF BY USER_ID ====================

async def get_staff_by_id(
    db: AsyncSession,
    tenant_id: str,
    user_id: int
) -> StaffBasicResponse:
    """Get basic staff information by user_id."""
    
    query = select(UserDB).options(
        selectinload(UserDB.admin),
        selectinload(UserDB.principal),
        selectinload(UserDB.teacher),
        selectinload(UserDB.other_staff),
    ).where(
        and_(
            UserDB.id == user_id,
            UserDB.tenant_id == tenant_id
        )
    )
    
    result = await db.execute(query)
    user = result.scalars().first()
    
    if not user:
        raise UserNotFoundException(f"Staff member not found")
    
    # Get role data
    role_data = None
    if user.admin:
        role_data = AdminBasicResponse.model_validate(user.admin, from_attributes=True)
    elif user.principal:
        role_data = PrincipalBasicResponse.model_validate(user.principal, from_attributes=True)
    elif user.teacher:
        role_data = TeacherBasicResponse.model_validate(user.teacher, from_attributes=True)
    elif user.other_staff:
        role_data = OtherStaffBasicResponse.model_validate(user.other_staff, from_attributes=True)
    return StaffBasicResponse(
        user_data=UsersBasicResponse.model_validate(user, from_attributes=True),
        role_data=role_data
    )


async def get_staff_full_by_id(
    db: AsyncSession,
    tenant_id: str,
    user_id: int
) -> StaffResponse:

    query = select(UserDB).options(
        selectinload(UserDB.admin),
        selectinload(UserDB.principal),
        selectinload(UserDB.teacher),
        selectinload(UserDB.other_staff),
        selectinload(UserDB.permissions).selectinload(UserPermissionDB.permission), 
    ).where(
        and_(
            UserDB.id == user_id,
            UserDB.tenant_id == tenant_id
        )
    )

    result = await db.execute(query)
    user = result.scalars().first()

    if not user:
        raise UserNotFoundException("Staff member not found")

    #Transform permissions properly
    permissions_data = [
        PermissionDetail(
            id=up.permission.id,
            name=up.permission.name,
            description=up.permission.description,
            granted_at=up.granted_at,
            granted_by=up.granted_by,
        )
        for up in user.permissions
    ]

    # Attach transformed permissions
    user_dict = user.__dict__.copy()
    user_dict["permissions"] = permissions_data

    # Get role data
    role_data = None
    if user.admin:
        role_data = AdminResponse.model_validate(user.admin, from_attributes=True)
    elif user.principal:
        role_data = PrincipalResponse.model_validate(user.principal, from_attributes=True)
    elif user.teacher:
        role_data = TeacherResponse.model_validate(user.teacher, from_attributes=True)
    elif user.other_staff:
        role_data = OtherStaffResponse.model_validate(user.other_staff, from_attributes=True)

    return StaffResponse(
        user_data=UsersResponse.model_validate(user_dict),
        role_data=role_data
    )


# ==================== GET ALL STAFF ====================

async def get_staff_all(
    db: AsyncSession,
    tenant_id: str,
) -> List[StaffBasicResponse]:
    """Get all staff members."""
    
    # Check institution exists
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    result = await db.execute(
        select(UserDB).options(
            selectinload(UserDB.admin),
            selectinload(UserDB.principal),
            selectinload(UserDB.teacher),
            selectinload(UserDB.other_staff),
        ).where(
            and_(
                UserDB.tenant_id == tenant_id,
                UserDB.role != "student"
            )
        )
    )
    users = result.unique().scalars().all()
    
    if not users:
        raise UserNotFoundException("No staff members found")
    
    all_staff = []
    
    for user in users:
        role_data = None
        if user.admin:
            role_data = AdminBasicResponse.model_validate(user.admin, from_attributes=True)
        elif user.principal:
            role_data = PrincipalBasicResponse.model_validate(user.principal, from_attributes=True)
        elif user.teacher:
            role_data = TeacherBasicResponse.model_validate(user.teacher, from_attributes=True)
        elif user.other_staff:
            role_data = OtherStaffBasicResponse.model_validate(user.other_staff, from_attributes=True)
        
        all_staff.append(
            StaffBasicResponse(
                user_data=UsersBasicResponse.model_validate(user, from_attributes=True),
                role_data=role_data
            )
        )
    
    return all_staff


# ==================== UPDATE STAFF BY USER_ID ====================

async def update_staff_by_id(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    updated_user_data: UserUpdate,
    updated_role_data: Union[TeacherUpdate, PrincipalUpdate, AdminUpdate, OtherStaffUpdate],
    mark_profile_complete: bool = False
) -> dict:
    """Update staff information by user_id."""
    
    query = select(UserDB).options(
        selectinload(UserDB.admin),
        selectinload(UserDB.principal),
        selectinload(UserDB.teacher),
        selectinload(UserDB.other_staff),
        selectinload(UserDB.permissions).selectinload(UserPermissionDB.permission)
    ).where(
        and_(
            UserDB.id == user_id,
            UserDB.tenant_id == tenant_id
        )
    )
    
    result = await db.execute(query)
    user = result.scalars().first()
    
    if not user:
        raise UserNotFoundException("Staff member not found")
    
    if user.role == 'student':
        raise InvalidStaffRoleError("User is not a staff member")
    
    # Get the actual role object
    role_obj = None
    if user.admin:
        role_obj = user.admin
    elif user.principal:
        role_obj = user.principal
    elif user.teacher:
        role_obj = user.teacher
    elif user.other_staff:
        role_obj = user.other_staff
    
    if not role_obj:
        raise DatabaseError("Staff role data not found")
    
        #Transform permissions properly
    permissions_data = [
        PermissionDetail(
            id=up.permission.id,
            name=up.permission.name,
            description=up.permission.description,
            granted_at=up.granted_at,
            granted_by=up.granted_by,
        )
        for up in user.permissions
    ]

    # mark as profile complete
    user.is_profile_complete = True if mark_profile_complete else user.is_profile_complete


    user_dict = user.__dict__.copy()
    user_dict["permissions"] = permissions_data
    
    # Update user fields
    user_update_dict = updated_user_data.model_dump(exclude_unset=True)
    for key, value in user_update_dict.items():
        setattr(user, key, value)
    
    # Update role fields
    role_update_dict = updated_role_data.model_dump(exclude_unset=True)
    for key, value in role_update_dict.items():
        setattr(role_obj, key, value)
    
    try:
        await db.commit()
        await db.refresh(user)
        await db.refresh(role_obj)
        
        return {
            "user_data": UsersResponse.model_validate(user_dict),
            "role_data": role_obj
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating staff: {e}", exc_info=True)
        raise DatabaseError("Unable to update staff")
    


async def get_deleted_staff(db: AsyncSession, tenant_id: str):
    q = select(UserDB).where(
        UserDB.deleted_date.isnot(None),
        UserDB.tenant_id == tenant_id,
        UserDB.role != "student" or "parent"
    )
    result = await db.execute(q)
    users = result.unique().scalars().all()
    return users 



# ==================== GET AVAILABLE STAFF ====================

async def get_available_staff(
    db: AsyncSession,
    tenant_id: str,
    start_time: int,
    end_time: int,
    days: List[str],
    subject: Optional[str] = None,
) -> List[StaffBasicResponse]:
    """Get staff available for given time slots."""
    
    # Check institution exists
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")
    
    # Capitalize days
    capitalized_days = [day.capitalize() for day in days]
    
    # Build conditions for busy check
    conditions = [
        InstitutionDB.tenant_id == tenant_id,
        ClassScheduleDB.day.in_(capitalized_days),
        ClassScheduleDB.start_time < end_time,
        ClassScheduleDB.end_time > start_time,
    ]
    
    if subject:
        conditions.append(ClassScheduleDB.subject_name == subject)
    
    # Get busy teacher IDs (using teacher_user_id which is UserDB.id)
    busy_query = await db.execute(
        select(ClassScheduleDB.teacher_user_id)
        .join(ClassDB, ClassScheduleDB.class_id == ClassDB.id)
        .join(InstitutionDB, ClassDB.institution_id == InstitutionDB.id)
        .where(and_(*conditions))
        .distinct()
    )
    busy_teacher_ids = {row[0] for row in busy_query.all()}
    
    # Get all eligible staff
    staff_query = await db.execute(
        select(UserDB)
        .options(
            selectinload(UserDB.admin),
            selectinload(UserDB.principal),
            selectinload(UserDB.teacher),
            selectinload(UserDB.other_staff),
        )
        .where(
            UserDB.tenant_id == tenant_id,
            # UserDB.role.not_in(["student", "admin", "other_staff"]),
            UserDB.role.not_in(["student"]),
        )
    )
    users = staff_query.unique().scalars().all()
    
    if not users:
        raise UserNotFoundException(f"No staff found")
    
    available_staff = []
    
    for user in users:
        # Skip busy teachers (checking UserDB.id against busy_teacher_ids)
        if user.id in busy_teacher_ids:
            continue
        
        role_data = None
        if user.admin:
            role_data = AdminBasicResponse.model_validate(user.admin, from_attributes=True)
        elif user.principal:
            role_data = PrincipalBasicResponse.model_validate(user.principal, from_attributes=True)
        elif user.teacher:
            role_data = TeacherBasicResponse.model_validate(user.teacher, from_attributes=True)
        elif user.other_staff:
            role_data = OtherStaffBasicResponse.model_validate(user.other_staff, from_attributes=True)
        
        available_staff.append(
            StaffBasicResponse(
                user_data=UsersBasicResponse.model_validate(user, from_attributes=True),
                role_data=role_data
            )
        )
    
    return available_staff

