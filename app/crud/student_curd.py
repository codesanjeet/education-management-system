from sqlalchemy import and_,func,case
from fastapi import BackgroundTasks
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.student_schema import StudentCreate, StudentResponse, StudentBasicResponse, StudentUpdate,StudentBasicRoleResponse
from app.models.role_specific.student_model import StudentDB, StudentFeesDB
from app.models.user_model import UserDB, UserSecurityDB, UserRoleEnum
from app.models.institution_model import InstitutionDB
from app.models.classes_model import ClassDB
from sqlalchemy.orm import selectinload
from typing import List
from ..core.exceptions import (
    UserAlreadyExistsError, 
    DatabaseError, 
    UserNotFoundException,
    ClassNotFoundError,
    ClassCapacityExceededError,
    DuplicateRollNumberError,
    InvalidUserRoleError,
    InstitutionNotFoundError
)
from .user_fun import generate_unique_username
from datetime import datetime
from secrets import token_urlsafe
import logging
from ..core.config import settings
from ..services.email import send_activation_email
from ..models.fee_model import InvoiceDB
logger = logging.getLogger(__name__)


async def create_student(
    db: AsyncSession,
    student_data: StudentCreate,
    class_code: str,
    tenant_id: str,
    activation_expires: datetime,
    activation_token: str
) -> dict:
    """Create a single student with flat schema."""
    
    # Check institution exists
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_result.scalar_one_or_none()
    
    if not inst_id:
        raise InstitutionNotFoundError(f"Institution not found for tenant: {tenant_id}")
    
    # Check if email already exists
    existing_user_result = await db.execute(
        select(UserDB).where(
            and_(
                UserDB.email == student_data.email.lower(),
                UserDB.tenant_id == tenant_id
            )
        )
    )
    if existing_user_result.scalars().first():
        raise UserAlreadyExistsError(f"Email '{student_data.email}' is already registered")
    
    # Check class exists and has capacity
    class_result = await db.execute(
        select(ClassDB).where(
            ClassDB.class_code == class_code,
            ClassDB.institution_id == inst_id
        )
    )
    class_obj = class_result.scalars().first()
    
    if not class_obj:
        raise ClassNotFoundError(f"Class '{class_code}' not found")
    
    if class_obj.current_student_count >= class_obj.max_student_limit:
        raise ClassCapacityExceededError(
            f"Class '{class_code}' is full "
            f"({class_obj.current_student_count}/{class_obj.max_student_limit} seats taken)"
        )
    
    # Check if roll number already taken in this class
    existing_roll_result = await db.execute(
        select(StudentDB).where(
            and_(
                StudentDB.class_code == class_code,
                StudentDB.roll_number == student_data.roll_number
            )
        )
    )
    if existing_roll_result.scalars().first():
        raise DuplicateRollNumberError(
            f"Roll number '{student_data.roll_number}' is already taken in class '{class_code}'"
        )

    # Create user and student records
    try:
        [username] = await generate_unique_username(
            db=db, 
            names=[(student_data.first_name, student_data.last_name)]
        )
        db_user = UserDB(
            user_name=username,
            institution_id=inst_id,
            tenant_id=tenant_id,
            role=UserRoleEnum.STUDENT.value,
            first_name=student_data.first_name,
            last_name=student_data.last_name,
            email=student_data.email,
            contact_num=student_data.contact_num,
            contact_num_country_code=student_data.contact_num_country_code,
            city=student_data.city,
            state=student_data.state,
            country=student_data.country,
            address=student_data.address,
            pincode=student_data.pincode,
        )

        db_student = StudentDB(
            roll_number=student_data.roll_number,
            class_code=class_code,
            guardian_contact_num=student_data.guardian_contact_num,
            guardian_contact_num_country_code=getattr(
                student_data, 'guardian_contact_num_country_code', '91'
            ),
        )

        db_user.student = db_student
        db_user.security = UserSecurityDB(
            activation_token_expires=activation_expires,
            activation_token=activation_token
        )
        db_student.fees = StudentFeesDB()

        db.add(db_user)
        class_obj.current_student_count += 1

        await db.commit()
        await db.refresh(db_student)
        await db.refresh(db_user)

        return {
            "message": "Student created successfully",
            "student_id": db_student.id,
            "first_name": db_user.first_name,
            "last_name": db_user.last_name,
            "user_id": db_user.id,
            "email": db_user.email,
            "user_name": db_user.user_name,
            "roll_number": db_student.roll_number
        }

    except (
        InstitutionNotFoundError,
        UserAlreadyExistsError,
        ClassNotFoundError,
        ClassCapacityExceededError,
        DuplicateRollNumberError,
        DatabaseError
    ):
        await db.rollback()
        raise

    except Exception as e:
        await db.rollback()
        # Only log truly unexpected errors
        logger.error(f"Unexpected error creating student for class '{class_code}': {e}", exc_info=True)
        raise DatabaseError("Unable to create student")

async def create_student_multi(
    db: AsyncSession,
    students: List[StudentCreate],
    class_code: str,
    tenant_id: str,
    activation_expires: datetime,
    background_tasks: BackgroundTasks = None  
) -> List[StudentDB]:
    """Create multiple students in a single transaction."""
   
    if not students:
        raise ValueError("Students list cannot be empty")
    
    MAX_BATCH_SIZE = 250
    if len(students) > MAX_BATCH_SIZE:
        raise ValueError(f"Cannot process more than {MAX_BATCH_SIZE} students at once")

    emails = [s.email.lower() for s in students]
    if len(set(emails)) != len(emails):
        raise UserAlreadyExistsError("Duplicate emails found in the submission")

    roll_numbers = [s.roll_number for s in students]
    if len(set(roll_numbers)) != len(roll_numbers):
        raise DuplicateRollNumberError("Duplicate roll numbers found in the submission")

    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst_id = inst_result.scalar_one_or_none()
    if not inst_id:
        raise InstitutionNotFoundError(f"Institution not found for tenant: {tenant_id}")

    class_result = await db.execute(
        select(ClassDB).where(ClassDB.class_code == class_code, ClassDB.institution_id == inst_id)
    )
    class_obj = class_result.scalars().first()
    if not class_obj:
        raise ClassNotFoundError(f"Class '{class_code}' not found")

    seats_available = class_obj.max_student_limit - class_obj.current_student_count
    if seats_available < len(students):
        raise ClassCapacityExceededError(
            f"Class '{class_code}' does not have enough capacity. "
            f"Available seats: {seats_available}, Requested: {len(students)}"
        )

    existing_users_result = await db.execute(
        select(UserDB.email).where(
            and_(UserDB.email.in_(emails), UserDB.tenant_id == tenant_id)
        )
    )
    existing_emails = [row[0] for row in existing_users_result.all()]
    if existing_emails:
        raise UserAlreadyExistsError(f"{len(existing_emails)} email(s) already registered")

    existing_rolls_result = await db.execute(
        select(StudentDB.roll_number).where(
            and_(StudentDB.class_code == class_code, StudentDB.roll_number.in_(roll_numbers))
        )
    )
    existing_rolls = [row[0] for row in existing_rolls_result.all()]
    if existing_rolls:
        raise DuplicateRollNumberError(
            f"{len(existing_rolls)} roll number(s) already assigned in class '{class_code}'"
        )

    created_students: List[StudentDB] = []

    try:
        names = [(s.first_name, s.last_name) for s in students]
        usernames_list = await generate_unique_username(db=db, names=names)
        usernames_map = {
            students[i].email.lower(): usernames_list[i]
            for i in range(len(students))
        }

        for student_data in students:
            username = usernames_map[student_data.email.lower()]
            activation_token = token_urlsafe(32)

            db_user = UserDB(
                user_name=username,
                institution_id=inst_id,
                tenant_id=tenant_id,
                role=UserRoleEnum.STUDENT.value,
                first_name=student_data.first_name,
                last_name=student_data.last_name,
                email=student_data.email,
                contact_num=student_data.contact_num,
                contact_num_country_code=student_data.contact_num_country_code,
                city=student_data.city,
                state=student_data.state,
                country=student_data.country,
                address=student_data.address,
                pincode=student_data.pincode,
            )

            db_student = StudentDB(
                roll_number=student_data.roll_number,
                class_code=class_code,
                guardian_contact_num=student_data.guardian_contact_num,
                guardian_contact_num_country_code=getattr(
                    student_data, 'guardian_contact_num_country_code', '91'
                ),
                father_name=getattr(student_data, 'father_name', None),
                mother_name=getattr(student_data, 'mother_name', None),
                guardian_name=getattr(student_data, 'guardian_name', None),
                guardian_relation=getattr(student_data, 'guardian_relation', None),
                guardian_email=getattr(student_data, 'guardian_email', None),
                guardian_address=getattr(student_data, 'guardian_address', None),
                emergency_contact=getattr(student_data, 'emergency_contact', None),
                medical_conditions=getattr(student_data, 'medical_conditions', None),
                special_needs=getattr(student_data, 'special_needs', None),
            )

            db_user.student = db_student
            db_user.security = UserSecurityDB(
                activation_token_expires=activation_expires,
                activation_token=activation_token
            )
            db_student.fees = StudentFeesDB()

            db.add(db_user)
            created_students.append(db_student)

        class_obj.current_student_count += len(created_students)
        await db.commit()

        student_ids = [s.id for s in created_students]
        result = await db.execute(
            select(StudentDB)
            .options(
                selectinload(StudentDB.user).selectinload(UserDB.security),
                selectinload(StudentDB.fees)
            )
            .where(StudentDB.id.in_(student_ids))
        )
        created_students_fresh = result.unique().scalars().all()

    except (
        InstitutionNotFoundError,
        UserAlreadyExistsError,
        ClassNotFoundError,
        ClassCapacityExceededError,
        DuplicateRollNumberError,
        DatabaseError,
        ValueError
    ):
        await db.rollback()
        raise

    except Exception as e:
        await db.rollback()
        logger.error(f"Unexpected error creating students for class '{class_code}': {e}", exc_info=True)
        raise DatabaseError("Unable to create students")

    # ── Commit done — queue emails in background ──────────────────────────────
    def _send_emails(students_data: list[dict]):
        for s in students_data:
            try:
                send_activation_email(
                    to=s["email"],
                    user_name=s["user_name"],
                    activation_link=s["activation_link"]
                )
            except Exception as e:
                logger.error(f"Activation email failed for '{s['email']}': {e}")

    # Build email payload before passing to background
    email_payloads = []
    for student in created_students_fresh:
        if student.user and student.user.security and student.user.security.activation_token:
            email_payloads.append({
                "email": student.user.email,
                "user_name": student.user.user_name,
                "activation_link": (
                    f"{settings.FRONTEND_URL}/activate"
                    f"?token={student.user.security.activation_token}"
                )
            })

    if background_tasks:
        background_tasks.add_task(_send_emails, email_payloads)
    else:
        _send_emails(email_payloads)  # fallback if no background_tasks passed

    return created_students_fresh


async def get_student_full(
    db: AsyncSession, 
    tenant_id: str,
    user_id: int
) -> StudentResponse:
    
    stmt = (
        select(UserDB)
        .options(selectinload(UserDB.student))
        .where(
            and_(
                UserDB.id == user_id,
                UserDB.tenant_id == tenant_id
            )
        )
    )
    
    result = await db.execute(stmt)
    user = result.scalars().first()
    
    if not user:
        raise UserNotFoundException("Student not found")
    
    if user.role != UserRoleEnum.STUDENT.value:
        raise InvalidUserRoleError("User is not a student")
    
    if not user.student:
        logger.error(f"Student data missing for user {user_id}")
        raise DatabaseError("Student data not found")
    
    student_response_data = {
        "roll_number": user.student.roll_number,
        "class_code": user.student.class_code,
        "father_name": user.student.father_name,
        "mother_name": user.student.mother_name,
        "guardian_name": user.student.guardian_name,
        "guardian_relation": user.student.guardian_relation,
        "guardian_email": user.student.guardian_email,
        "guardian_address": user.student.guardian_address,
        "guardian_contact_num": user.student.guardian_contact_num,
        "guardian_contact_num_country_code": user.student.guardian_contact_num_country_code,
        "guardian_alternative_contact_num": user.student.guardian_alternative_contact_num,
        "guardian_alternative_contact_num_country_code": user.student.guardian_alternative_contact_num_country_code,
        "emergency_contact": user.student.emergency_contact,
        "medical_conditions": user.student.medical_conditions,
        "special_needs": user.student.special_needs,
        "student_status": user.student.student_status,
        "issue_admit_card": user.student.issue_admit_card,
        "user_id": user.id,
        "profile_image": user.profile_image,
        "user_name": user.user_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": user.role,
        "joined_date": user.joined_date,
        "permissions": [],
        "is_block": user.is_block,
        "contact_num": user.contact_num,
        "contact_num_country_code": user.contact_num_country_code,
        "alternative_contact_num": user.alternative_contact_num,
        "alternative_contact_num_country_code": user.alternative_contact_num_country_code,
        "address": user.address,
        "city": user.city,
        "state": user.state,
        "pincode": user.pincode,
        "country": user.country,
        "gender": user.gender,
        "date_of_birth": user.date_of_birth,
        "blood_group": user.blood_group,
        "total_score": user.total_score,
        "score_breakdown": user.score_breakdown or [],
        "deleted_date": user.deleted_date,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    
    return StudentResponse(**student_response_data)


async def get_student_all(
    db: AsyncSession,
    tenant_id: str,
    class_code: str
) -> List[StudentBasicResponse]:
    
    query = (
        select(
            UserDB.id,
            UserDB.user_name,
            UserDB.first_name,
            UserDB.last_name,
            UserDB.email,
            UserDB.contact_num,
            UserDB.contact_num_country_code,
            UserDB.profile_image,
            UserDB.is_block,
            UserDB.deleted_date,
            StudentDB.roll_number,
            StudentDB.class_code,
            StudentDB.student_status
        )
        .join(StudentDB, StudentDB.user_id == UserDB.id)
        .where(
            UserDB.tenant_id == tenant_id,
            UserDB.role == UserRoleEnum.STUDENT.value,
            StudentDB.class_code == class_code
        )
    )

    result = await db.execute(query)
    rows = result.mappings().all()  

    if not rows:
        raise UserNotFoundException(f"No students found for class {class_code}")

    return [StudentBasicResponse.model_validate(row) for row in rows]

async def get_student_data_by_id(
    db: AsyncSession,
    user_id : int
) -> StudentBasicRoleResponse:
    
    query = (
        select(
           StudentDB
        )
        .where(
          StudentDB.user_id == user_id
        )
    )

    result = await db.execute(query)
    row = result.scalar_one_or_none()

    if not row:
        raise UserNotFoundException(f"No students found")

    return StudentBasicRoleResponse.model_validate(row) 
async def get_basic_student_data_by_id(db, user_id: int) -> StudentBasicResponse:
    query = (
        select(
            UserDB.id,
            UserDB.user_name,
            UserDB.first_name,
            UserDB.last_name,
            UserDB.email,
            UserDB.contact_num,
            UserDB.contact_num_country_code,
            UserDB.is_block,
            UserDB.deleted_date,
            UserDB.profile_image,
            StudentDB.roll_number,
            StudentDB.class_code,
            StudentDB.student_status
        )
        .join(StudentDB, StudentDB.user_id == UserDB.id)
        .where(UserDB.id == user_id)
    )

    result = await db.execute(query)
    row = result.mappings().first()

    if not row:
        raise UserNotFoundException("No student found")

    return StudentBasicResponse.model_validate(row) 

async def get_financial_data_by_id(db: AsyncSession, user_id: int):

    query = await db.execute(
        select(
            func.sum(
                case(
                    (
                        InvoiceDB.student_user_id == user_id,
                        InvoiceDB.balance_due
                    ),
                    else_=0
                )
            ).label("balance_due"),

            func.sum(
                case(
                    (
                        InvoiceDB.student_user_id == user_id,
                        InvoiceDB.paid_total
                    ),
                    else_=0
                )
            ).label("total_paid"),
        )
    )

    financial_data = query.one()

    return financial_data



async def update_student(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    update_data: StudentUpdate,
    mark_profile_complete: bool = False  
) -> StudentResponse:
    """Update student with flat schema."""
    
    user_result = await db.execute(
        select(UserDB)
        .options(selectinload(UserDB.student))
        .where(
            and_(
                UserDB.id == user_id,
                UserDB.tenant_id == tenant_id
            )
        )
    )
    user = user_result.scalars().first()
    
    if not user:
        raise UserNotFoundException("Student not found")
    
    if user.role != UserRoleEnum.STUDENT.value:
        raise InvalidUserRoleError("User is not a student")
    
    if not user.student:
        logger.error(f"Student data missing for user {user_id}")
        raise DatabaseError("Student data not found")
    
    student = user.student
    update_dict = update_data.model_dump(exclude_unset=True)
    
    if not update_dict:
        raise ValueError("No fields provided for update")
    
    # mark as complete profile
    user.is_profile_complete = True if mark_profile_complete else user.is_profile_complete

    user_fields = {
        'first_name', 'last_name', 'email', 'contact_num',
        'contact_num_country_code', 'alternative_contact_num',
        'alternative_contact_num_country_code',
        'address', 'city', 'state', 'pincode', 'country',
        'gender', 'date_of_birth', 'blood_group'
    }
    
    student_fields = {
        'roll_number', 'father_name', 'mother_name', 'guardian_name',
        'guardian_relation', 'guardian_email', 'guardian_address',
        'guardian_contact_num', 'guardian_contact_num_country_code',
        'guardian_alternative_contact_num', 'guardian_alternative_contact_num_country_code',
        'emergency_contact', 'medical_conditions', 'special_needs'
    }

    # Validate unique constraints
    if 'email' in update_dict and update_dict['email'] != user.email:
        existing_email = await db.execute(
            select(UserDB.id).where(
                and_(
                    UserDB.email == update_dict['email'].lower(),
                    UserDB.tenant_id == tenant_id,
                    UserDB.id != user_id
                )
            )
        )
        if existing_email.scalar_one_or_none():
            raise UserAlreadyExistsError(f"Email {update_dict['email']} is already registered")

    if 'roll_number' in update_dict and update_dict['roll_number'] != student.roll_number:
        existing_roll = await db.execute(
            select(StudentDB.id).where(
                and_(
                    StudentDB.roll_number == update_dict['roll_number'],
                    StudentDB.class_code == student.class_code,
                    StudentDB.id != student.id
                )
            )
        )
        if existing_roll.scalar_one_or_none():
            raise DuplicateRollNumberError(f"Roll number {update_dict['roll_number']} is already assigned")

    # Update fields
    user_updates = {k: v for k, v in update_dict.items() if k in user_fields}
    for key, value in user_updates.items():
        setattr(user, key, value)

    student_updates = {k: v for k, v in update_dict.items() if k in student_fields}
    for key, value in student_updates.items():
        setattr(student, key, value)

    try:
        await db.commit()
        await db.refresh(user)
        await db.refresh(student)
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating student {user_id}: {e}", exc_info=True)
        raise DatabaseError("Unable to update student")

    student_response_data = {
        "roll_number": student.roll_number,
        "class_code": student.class_code,
        "father_name": student.father_name,
        "mother_name": student.mother_name,
        "guardian_name": student.guardian_name,
        "guardian_relation": student.guardian_relation,
        "guardian_email": student.guardian_email,
        "guardian_address": student.guardian_address,
        "guardian_contact_num": student.guardian_contact_num,
        "guardian_contact_num_country_code": student.guardian_contact_num_country_code,
        "guardian_alternative_contact_num": student.guardian_alternative_contact_num,
        "guardian_alternative_contact_num_country_code": student.guardian_alternative_contact_num_country_code,
        "emergency_contact": student.emergency_contact,
        "medical_conditions": student.medical_conditions,
        "special_needs": student.special_needs,
        "student_status": student.student_status,
        "issue_admit_card": student.issue_admit_card,
        "user_id": user.id,
        "user_name": user.user_name,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": user.role,
        "joined_date": user.joined_date,
        "permissions": [],
        "is_block": user.is_block,
        "contact_num": user.contact_num,
        "contact_num_country_code": user.contact_num_country_code,
        "alternative_contact_num": user.alternative_contact_num,
        "alternative_contact_num_country_code": user.alternative_contact_num_country_code,
        "address": user.address,
        "city": user.city,
        "state": user.state,
        "pincode": user.pincode,
        "country": user.country,
        "gender": user.gender,
        "date_of_birth": user.date_of_birth,
        "blood_group": user.blood_group,
        "total_score": user.total_score,
        "score_breakdown": user.score_breakdown or [],
        "deleted_date": user.deleted_date,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    
    return StudentResponse(**student_response_data)


async def get_deleted_student(db: AsyncSession, tenant_id: str):
    q = select(UserDB).where(
        UserDB.deleted_date.isnot(None),
        UserDB.tenant_id == tenant_id,
        UserDB.role == "student"
    )
    result = await db.execute(q)
    users = result.unique().scalars().all()
    return users 