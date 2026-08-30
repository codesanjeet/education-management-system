from sqlalchemy.future import select
from sqlalchemy import extract, exists, and_, desc,delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime,timedelta
from typing import List,Optional
import logging

from ..schemas.user_schema import UserRoleEnum
from ..core.exceptions import (
    DatabaseError,
    UserNotFoundException,
    InstitutionNotFoundError,
)
import re
from ..models.institution_model import InstitutionDB
from ..models.classes_model import ClassDB
from ..models.role_specific.staff_sub_models import StaffAttendanceDB
from ..models.role_specific.student_model import StudentDB, StudentAttendanceDB
from ..models.attendance_model import (
    StudentAttendanceAggDB,
    ClassAttendanceAggDB,
    DaysClassAttendanceAggDB,
    InstitutionAttendanceAggDB,
    DaysInstitutionAttendanceAggDB,
    StaffAttendanceAggDB,
    DaysStaffAttendanceAggDB,
    QRAttendanceSessionDB,
    AttendanceAuditDB
)
from ..schemas.attendance_schema import (
    BulkAttendanceCreate,
    AttendanceStudentSuccessResponse,
    AttendanceStatus,
    StudentForMarkAttendance,
    StudentForUpdateAttendance,
    ClassAttendanceSummary,
    ClassAttendanceDaySummary,
    InstitutionAttendanceSummary,
    InstitutionAttendanceDaySummary,
    StudentAttendanceMonthResponse,
    StudentAttendanceSummaryResponse,
    StaffAttendanceCreate,
    StaffAttendanceUpdate,
    IndividualAttendanceCreate,
    StaffAttendanceDayAggResponse,
    StaffAttendanceResponse
)
from ..models.user_model import UserDB
import uuid
logger = logging.getLogger(__name__)


# ==================== HELPER FUNCTIONS ====================

async def _validate_institution_exists(db: AsyncSession, tenant_id: str) -> None:
    """Validate institution exists."""
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")


async def get_previous_student_agg_totals(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    subject: str,
    current_year: int,
    current_month: int
) -> tuple[int, int]:
    """Get cumulative totals from previous months for a student."""
    normalized_subject = subject.capitalize()
    query = await db.execute(
        select(StudentAttendanceAggDB)
        .where(
            and_(
                StudentAttendanceAggDB.tenant_id == tenant_id,
                StudentAttendanceAggDB.user_id == user_id,
                StudentAttendanceAggDB.subject == normalized_subject
            )
        )
        .order_by(
            desc(StudentAttendanceAggDB.year),
            desc(StudentAttendanceAggDB.month)
        )
        .limit(1)
    )
    previous_agg = query.scalars().first()
    
    if previous_agg:
        if (previous_agg.year < current_year or 
            (previous_agg.year == current_year and previous_agg.month < current_month)):
            return previous_agg.present, previous_agg.total
    
    return 0, 0


async def get_previous_class_agg_totals(   
    db: AsyncSession,
    tenant_id: str,
    class_code: str,
    current_year: int,
    current_month: int
) -> tuple[int, int]:
    """Get cumulative totals from previous months for a class."""
    query = await db.execute(
        select(ClassAttendanceAggDB)
        .where(
            and_(
                ClassAttendanceAggDB.tenant_id == tenant_id,
                ClassAttendanceAggDB.class_code == class_code
            )
        )
        .order_by(
            desc(ClassAttendanceAggDB.year),
            desc(ClassAttendanceAggDB.month)
        )
        .limit(1)
    )
    previous_agg = query.scalars().first()
    
    if previous_agg:
        if (previous_agg.year < current_year or 
            (previous_agg.year == current_year and previous_agg.month < current_month)):
            return previous_agg.present, previous_agg.total
    
    return 0, 0


async def get_previous_institution_agg_totals(
    db: AsyncSession,
    tenant_id: str,
    current_year: int,
    current_month: int
) -> tuple[int, int]:
    """Get cumulative totals from previous months for an institution."""
    query = await db.execute(
        select(InstitutionAttendanceAggDB)
        .where(InstitutionAttendanceAggDB.tenant_id == tenant_id)
        .order_by(
            desc(InstitutionAttendanceAggDB.year),
            desc(InstitutionAttendanceAggDB.month)
        )
        .limit(1)
    )
    previous_agg = query.scalars().first()
    
    if previous_agg:
        if (previous_agg.year < current_year or 
            (previous_agg.year == current_year and previous_agg.month < current_month)):
            return previous_agg.present, previous_agg.total
    
    return 0, 0


async def get_previous_staff_agg_totals(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    current_year: int,
    current_month: int
) -> dict:
    """Get cumulative totals from previous months for staff."""
    query = await db.execute(
        select(StaffAttendanceAggDB)
        .where(
            StaffAttendanceAggDB.tenant_id == tenant_id,
            StaffAttendanceAggDB.user_id == user_id
        )
        .order_by(
            desc(StaffAttendanceAggDB.year),
            desc(StaffAttendanceAggDB.month)
        )
        .limit(1)
    )

    previous_agg = query.scalars().first()

    if previous_agg and (
        previous_agg.year < current_year or
        (previous_agg.year == current_year and previous_agg.month < current_month)
    ):
        return {
            "present": previous_agg.present,
            "total": previous_agg.total
        }

    return {"present": 0, "total": 0}


# ==================== STUDENT ATTENDANCE ====================
async def create_individual_student_attendance(
    db: AsyncSession,
    tenant_id: str,
    user_id: str,
    attendance_data: IndividualAttendanceCreate
) -> AttendanceStudentSuccessResponse:
    """Create attendance record for a single student with aggregation updates."""

    try:
        attendance_date = attendance_data.attendance_date or datetime.now().date()
        normalized_subject = attendance_data.subject.capitalize() if attendance_data.subject else "all"

        current_year = attendance_date.year
        current_month = attendance_date.month
        current_weekday = attendance_date.weekday()
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_str = weekday_names[current_weekday]

        # Fetch student + class_code + username in ONE query
        student_result = await db.execute(
            select(
                StudentDB.id.label("student_id"),
                StudentDB.roll_number,
                StudentDB.class_code,
                UserDB.user_name
            )
            .join(UserDB, UserDB.id == StudentDB.user_id)
            .where(
                StudentDB.user_id == user_id,
                StudentDB.class_code == attendance_data.class_code
            )
        )
        student = student_result.mappings().first()

        if not student:
            raise ValueError(f"Student with user_id {user_id} not found in class {attendance_data.class_code}")

        class_code = student["class_code"]

        # Validate class belongs to institution/tenant
        class_check = await db.execute(
            select(exists().where(
                InstitutionDB.tenant_id == tenant_id,
                ClassDB.class_code == class_code,
                ClassDB.institution_id == InstitutionDB.id
            ))
        )
        if not class_check.scalar():
            raise ValueError(f"Class {class_code} not found for tenant {tenant_id}")

        # Check if attendance already marked for this student on this date + subject
        already_marked = await db.execute(
            select(exists().where(
                StudentAttendanceDB.student_id == student["student_id"],
                StudentAttendanceDB.date == attendance_date,
                StudentAttendanceDB.subject == normalized_subject
            ))
        )
        if already_marked.scalar():
            raise ValueError(
                f"Attendance already marked for student {user_id} "
                f"on {attendance_date} for subject '{normalized_subject}'"
            )

        status = attendance_data.status
        is_present = status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]

        # ── 1. Insert attendance record ──────────────────────────────────────
        attendance_record = StudentAttendanceDB(
            student_id=student["student_id"],
            subject=normalized_subject,
            class_code=class_code,
            date=attendance_date,
            status=status
        )
        db.add(attendance_record)
        # to make attendance id  aval
        await db.flush()
        attendance_id = attendance_record.id

        # ── 2. Student monthly aggregation ───────────────────────────────────
        student_agg_result = await db.execute(
            select(StudentAttendanceAggDB).where(
                and_(
                    StudentAttendanceAggDB.tenant_id == tenant_id,
                    StudentAttendanceAggDB.user_id == user_id,
                    StudentAttendanceAggDB.year == current_year,
                    StudentAttendanceAggDB.month == current_month,
                    StudentAttendanceAggDB.subject == normalized_subject
                )
            )
        )
        student_agg = student_agg_result.scalars().first()

        if student_agg:
            student_agg.total += 1
            if is_present:
                student_agg.present += 1
        else:
            prev_present, prev_total = await get_previous_student_agg_totals(
                db, tenant_id, user_id,
                normalized_subject, current_year, current_month
            )
            student_agg = StudentAttendanceAggDB(
                tenant_id=tenant_id,
                user_id=user_id,
                user_name=student["user_name"],
                year=current_year,
                month=current_month,
                subject=normalized_subject,
                present=prev_present + (1 if is_present else 0),
                total=prev_total + 1,
            )
            db.add(student_agg)

        # ── 3. Class monthly aggregation ─────────────────────────────────────
        class_agg_result = await db.execute(
            select(ClassAttendanceAggDB).where(
                and_(
                    ClassAttendanceAggDB.tenant_id == tenant_id,
                    ClassAttendanceAggDB.class_code == class_code,
                    ClassAttendanceAggDB.year == current_year,
                    ClassAttendanceAggDB.month == current_month
                )
            )
        )
        class_agg = class_agg_result.scalars().first()

        if class_agg:
            class_agg.total += 1
            if is_present:
                class_agg.present += 1
        else:
            prev_present, prev_total = await get_previous_class_agg_totals(
                db, tenant_id, class_code, current_year, current_month
            )
            class_agg = ClassAttendanceAggDB(
                tenant_id=tenant_id,
                class_code=class_code,
                year=current_year,
                month=current_month,
                present=prev_present + (1 if is_present else 0),
                total=prev_total + 1,
            )
            db.add(class_agg)

        # ── 4. Class daily (weekday) aggregation ─────────────────────────────
        class_day_agg_result = await db.execute(
            select(DaysClassAttendanceAggDB).where(
                and_(
                    DaysClassAttendanceAggDB.tenant_id == tenant_id,
                    DaysClassAttendanceAggDB.class_code == class_code,
                    DaysClassAttendanceAggDB.week_day == weekday_str
                )
            )
        )
        class_day_agg = class_day_agg_result.scalars().first()

        if class_day_agg:
            if weekday_str == "Monday":
                class_day_agg.total = 0
                class_day_agg.present = 0
            class_day_agg.total += 1
            if is_present:
                class_day_agg.present += 1
        else:
            class_day_agg = DaysClassAttendanceAggDB(
                tenant_id=tenant_id,
                class_code=class_code,
                week_day=weekday_str,
                present=1 if is_present else 0,
                total=1,
            )
            db.add(class_day_agg)

        # ── 5. Institution monthly aggregation ───────────────────────────────
        inst_agg_result = await db.execute(
            select(InstitutionAttendanceAggDB).where(
                and_(
                    InstitutionAttendanceAggDB.tenant_id == tenant_id,
                    InstitutionAttendanceAggDB.year == current_year,
                    InstitutionAttendanceAggDB.month == current_month
                )
            )
        )
        inst_agg = inst_agg_result.scalars().first()

        if inst_agg:
            inst_agg.total += 1
            if is_present:
                inst_agg.present += 1
        else:
            prev_present, prev_total = await get_previous_institution_agg_totals(
                db, tenant_id, current_year, current_month
            )
            inst_agg = InstitutionAttendanceAggDB(
                tenant_id=tenant_id,
                year=current_year,
                month=current_month,
                present=prev_present + (1 if is_present else 0),
                total=prev_total + 1,
            )
            db.add(inst_agg)

        # ── 6. Institution daily (weekday) aggregation ───────────────────────
        inst_day_agg_result = await db.execute(
            select(DaysInstitutionAttendanceAggDB).where(
                and_(
                    DaysInstitutionAttendanceAggDB.tenant_id == tenant_id,
                    DaysInstitutionAttendanceAggDB.week_day == weekday_str
                )
            )
        )
        inst_day_agg = inst_day_agg_result.scalars().first()

        if inst_day_agg:
            if weekday_str == "Monday":
                inst_day_agg.total = 0
                inst_day_agg.present = 0
            inst_day_agg.total += 1
            if is_present:
                inst_day_agg.present += 1
        else:
            inst_day_agg = DaysInstitutionAttendanceAggDB(
                tenant_id=tenant_id,
                week_day=weekday_str,
                present=1 if is_present else 0,
                total=1,
            )
            db.add(inst_day_agg)

        await db.commit()

        return AttendanceStudentSuccessResponse(
            message="Attendance successfully submitted",
            students_processed=1,
            present_count=1 if status == AttendanceStatus.PRESENT else 0,
            absent_count=1 if status == AttendanceStatus.ABSENT else 0,
            late_count=1 if status == AttendanceStatus.LATE else 0,
            class_code=class_code,
            attendance_date=attendance_date,
            attendance_id = attendance_id
        )

    except ValueError:
        await db.rollback()
        raise

    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating individual student attendance: {e}", exc_info=True)
        raise DatabaseError("Unable to create attendance record")






async def create_student_attendance(
    db: AsyncSession, 
    tenant_id: str,
    class_code: str,
    attendance_data: BulkAttendanceCreate
) -> AttendanceStudentSuccessResponse:
    """Create student attendance records with aggregation updates."""
    
    try:
        normalized_subject = attendance_data.records[0].subject.capitalize() if attendance_data.records[0].subject else "all"
        class_code = class_code
        records = attendance_data.records
        attendance_date = attendance_data.attendance_date or datetime.now().date()

        # Check if attendance already marked
        already_marked_check = await db.execute(
            select(exists().where(
                StudentAttendanceDB.date == attendance_date,
                StudentAttendanceDB.class_code == class_code,
                StudentAttendanceAggDB.subject == normalized_subject
            ))
        )
        
        if already_marked_check.scalar():
            raise ValueError(f"Attendance already marked for class {class_code} on {attendance_date}")

        # Date information
        current_year = attendance_date.year
        current_month = attendance_date.month
        current_weekday = attendance_date.weekday()
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_str = weekday_names[current_weekday]
        
        # Validate class and institution
        class_check = await db.execute(
            select(exists().where(
                InstitutionDB.tenant_id == tenant_id,
                ClassDB.class_code == class_code,
                ClassDB.institution_id == InstitutionDB.id
            ))
        )
        if not class_check.scalar():
            raise ValueError(f"Class {class_code} not found")
        
        # Initialize counters
        total_students_processed = 0
        present_count = 0
        absent_count = 0
        late_count = 0

        #Fetch all students in the class (ONE QUERY)
        students_result = await db.execute(
            select(
                StudentDB.id.label("student_id"),
                StudentDB.roll_number,
                StudentDB.user_id,
                UserDB.user_name
            )
            .join(UserDB, UserDB.id == StudentDB.user_id)
            .where(StudentDB.class_code == class_code)
        )

        students = students_result.mappings().all()

        if not students:
            raise ValueError("No students found for this class")


        # Validate attendance count
        if len(records) != len(students):
            raise ValueError("Attendance must include all students in the class")


        # Create lookup dictionary 
        student_map = {s["roll_number"]: s for s in students}


        submitted_rolls = {r.roll_number for r in records}
        actual_rolls = {s["roll_number"] for s in students}

        if submitted_rolls != actual_rolls:
                raise ValueError("Attendance list does not match class roster")
        
        # Step 4: Process attendance safely
        for record in records:
            student = student_map[record.roll_number]

            if not student:
                raise ValueError(f"Invalid roll number: {record.roll_number}")
            
   
            is_present = record.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
            
            # Create attendance record
    
            attendance_record = StudentAttendanceDB(
                student_id=student["student_id"],
                subject=normalized_subject or "all",
                class_code=class_code,
                date=attendance_date, 
                status=record.status
            )
            db.add(attendance_record)
            
            # Update student monthly aggregation
            student_agg_query = await db.execute(
                select(StudentAttendanceAggDB).where(
                    and_(
                        StudentAttendanceAggDB.tenant_id == tenant_id,
                        StudentAttendanceAggDB.user_id == student["user_id"],
                        StudentAttendanceAggDB.year == current_year,
                        StudentAttendanceAggDB.month == current_month,
                        StudentAttendanceAggDB.subject == (normalized_subject or "all")
                    )
                )
            )
            student_agg = student_agg_query.scalars().first()
            
            if student_agg:
                student_agg.total += 1
                if is_present:
                    student_agg.present += 1
            else:
                prev_present, prev_total = await get_previous_student_agg_totals(
                    db, tenant_id, student["user_id"], 
                    normalized_subject or "all", current_year, current_month
                )
                
                student_agg = StudentAttendanceAggDB(
                    tenant_id=tenant_id,
                    user_id=student["user_id"],
                    user_name=student["user_name"],
                    year=current_year,
                    month=current_month,
                    subject=normalized_subject or "all",
                    present=prev_present + (1 if is_present else 0),
                    total=prev_total + 1,
                )
                db.add(student_agg)
            
            total_students_processed += 1
            if record.status == AttendanceStatus.PRESENT:
                present_count += 1
            elif record.status == AttendanceStatus.ABSENT:
                absent_count += 1
            elif record.status == AttendanceStatus.LATE:
                late_count += 1
        
        if total_students_processed == 0:
            raise ValueError("No valid student records were processed")
        
        total_present_for_agg = present_count + late_count
        
        # Update class monthly aggregation
        class_agg_query = await db.execute(
            select(ClassAttendanceAggDB).where(
                and_(
                    ClassAttendanceAggDB.tenant_id == tenant_id,
                    ClassAttendanceAggDB.class_code == class_code,
                    ClassAttendanceAggDB.year == current_year,
                    ClassAttendanceAggDB.month == current_month
                )
            )
        )
        class_agg = class_agg_query.scalars().first()
        
        if class_agg:
            class_agg.total += total_students_processed
            class_agg.present += total_present_for_agg
        else:
            prev_present, prev_total = await get_previous_class_agg_totals(
                db, tenant_id, class_code, current_year, current_month
            )
            
            class_agg = ClassAttendanceAggDB(
                tenant_id=tenant_id,
                class_code=class_code,
                year=current_year,
                month=current_month,
                present=prev_present + total_present_for_agg,
                total=prev_total + total_students_processed,
            )
            db.add(class_agg)
        
        # Update class daily aggregation
        class_day_agg_query = await db.execute(
            select(DaysClassAttendanceAggDB).where(
                and_(
                    DaysClassAttendanceAggDB.tenant_id == tenant_id,
                    DaysClassAttendanceAggDB.class_code == class_code,
                    DaysClassAttendanceAggDB.week_day == weekday_str
                )
            )
        )
        class_day_agg = class_day_agg_query.scalars().first()
        
        if class_day_agg:
            if class_day_agg.week_day == "Monday":
                class_day_agg.total = 0
                class_day_agg.present = 0
            class_day_agg.total += total_students_processed
            class_day_agg.present += total_present_for_agg
        else:
            class_day_agg = DaysClassAttendanceAggDB(
                tenant_id=tenant_id,
                class_code=class_code,
                week_day=weekday_str,
                present=total_present_for_agg,
                total=total_students_processed,
            )
            db.add(class_day_agg)
        
        # Update institution monthly aggregation
        inst_agg_query = await db.execute(
            select(InstitutionAttendanceAggDB).where(
                and_(
                    InstitutionAttendanceAggDB.tenant_id == tenant_id,
                    InstitutionAttendanceAggDB.year == current_year,
                    InstitutionAttendanceAggDB.month == current_month
                )
            )
        )
        inst_agg = inst_agg_query.scalars().first()
        
        if inst_agg:
            inst_agg.total += total_students_processed
            inst_agg.present += total_present_for_agg
        else:
            prev_present, prev_total = await get_previous_institution_agg_totals(
                db, tenant_id, current_year, current_month
            )
            
            inst_agg = InstitutionAttendanceAggDB(
                tenant_id=tenant_id,
                year=current_year,
                month=current_month,
                present=prev_present + total_present_for_agg,
                total=prev_total + total_students_processed,
            )
            db.add(inst_agg)
        
        # Update institution daily aggregation
        inst_day_agg_query = await db.execute(
            select(DaysInstitutionAttendanceAggDB).where(
                and_(
                    DaysInstitutionAttendanceAggDB.tenant_id == tenant_id,
                    DaysInstitutionAttendanceAggDB.week_day == weekday_str
                )
            )
        )
        inst_day_agg = inst_day_agg_query.scalars().first()
        
        if inst_day_agg:
            if inst_day_agg.week_day == "Monday":
                inst_day_agg.total = 0
                inst_day_agg.present = 0
            inst_day_agg.total += total_students_processed
            inst_day_agg.present += total_present_for_agg
        else:
            inst_day_agg = DaysInstitutionAttendanceAggDB(
                tenant_id=tenant_id,
                week_day=weekday_str,
                present=total_present_for_agg,
                total=total_students_processed
            )
            db.add(inst_day_agg)
        
        await db.commit()
        
        return AttendanceStudentSuccessResponse(
            message="Attendance successfully submitted",
            students_processed=total_students_processed,
            present_count=present_count,
            absent_count=absent_count,
            late_count=late_count,
            class_code=class_code,
            attendance_date=attendance_date
        )
        
    except ValueError:
        await db.rollback()
        raise
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating student attendance: {e}", exc_info=True)
        raise DatabaseError("Unable to create attendance records")


async def get_full_month_student_attendance(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    month: int,
    year: int
) -> List[StudentAttendanceMonthResponse]:
    """Get full month student attendance records."""
    
    await _validate_institution_exists(db, tenant_id)

    user_query = await db.execute(
        select(UserDB).where(
            UserDB.id == user_id,
            UserDB.tenant_id == tenant_id,
        )
    )
    user = user_query.scalars().first()
    if not user:
        raise UserNotFoundException(f"User not found")

    student_query = await db.execute(
        select(StudentDB).where(StudentDB.user_id == user.id)
    )
    student = student_query.scalars().first()
    if not student:
        raise ValueError("No student record linked with this user")

    att_query = await db.execute(
        select(
            StudentAttendanceDB.subject,
            StudentAttendanceDB.date,
            StudentAttendanceDB.status
        )
        .where(
            StudentAttendanceDB.student_id == student.id,
            extract("year", StudentAttendanceDB.date) == year,
            extract("month", StudentAttendanceDB.date) == month,
        )
        .order_by(StudentAttendanceDB.date.asc())
    )

    attendance_rows = att_query.mappings().all()
    if not attendance_rows:
        return []

    return [
        StudentAttendanceMonthResponse(
            subject=row["subject"],
            attendance_date=row["date"],
            status=row["status"]
        )
        for row in attendance_rows
    ]


async def get_student_attendance_summary(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    month: int,
    year: int
) -> list[StudentAttendanceSummaryResponse]:
    """Get student attendance summary for a month."""
    
    if not 1 <= month <= 12:
        raise ValueError("Month must be between 1 and 12")

    await _validate_institution_exists(db, tenant_id)

    user_id_query = await db.execute(
        select(UserDB.id).where(
            UserDB.id == user_id,
            UserDB.tenant_id == tenant_id
        )
    )
    user_id = user_id_query.scalars().first()

    if not user_id:
        raise UserNotFoundException("User not found")

    result = await db.execute(
        select(
            StudentAttendanceAggDB.present,
            StudentAttendanceAggDB.total,
            StudentAttendanceAggDB.updated_at,
            StudentAttendanceAggDB.subject,
        )
        .where(
            and_(
                StudentAttendanceAggDB.tenant_id == tenant_id,
                StudentAttendanceAggDB.user_id == user_id,
                StudentAttendanceAggDB.year == year,
                StudentAttendanceAggDB.month == month
            )
        )
    )

    rows= result.mappings().all()


    
    if not rows:
        return []

    return [StudentAttendanceSummaryResponse(
        subject= summary["subject"],
        total=summary["total"],
        present=summary["present"],
        month=month,
        year=year,
        updated_at=summary["updated_at"]
    ) for summary in rows] 


async def get_class_attendance_agg(
    db: AsyncSession,
    tenant_id: str,
    class_code: str,
    year: int,
    month: int
) -> ClassAttendanceSummary:
    """Get class attendance aggregation for a month."""
    
    await _validate_institution_exists(db, tenant_id)

    query = await db.execute(
        select(ClassAttendanceAggDB).where(
            and_(
                ClassAttendanceAggDB.tenant_id == tenant_id,
                ClassAttendanceAggDB.class_code == class_code,
                ClassAttendanceAggDB.year == year,
                ClassAttendanceAggDB.month == month,
            )
        )
    )
    rec = query.scalars().first()
    if not rec:
        return None
    return ClassAttendanceSummary.model_validate(rec, from_attributes=True)


async def get_institution_attendance_agg(
    db: AsyncSession,
    tenant_id: str,
    year: int,
    month: int
) -> InstitutionAttendanceSummary:
    """Get institution attendance aggregation for a month."""
    
    await _validate_institution_exists(db, tenant_id)

    query = await db.execute(
        select(
            InstitutionAttendanceAggDB.month,
            InstitutionAttendanceAggDB.year,
            InstitutionAttendanceAggDB.present,
            InstitutionAttendanceAggDB.total,
            InstitutionAttendanceAggDB.updated_at
        ).where(
            and_(
                InstitutionAttendanceAggDB.tenant_id == tenant_id,
                InstitutionAttendanceAggDB.year == year,
                InstitutionAttendanceAggDB.month == month,
            )
        )
    )
    rec = query.mappings().first()
    if not rec:
        return None
    
    return InstitutionAttendanceSummary(
        total=rec["total"],
        present=rec["present"],
        year=year,
        month=month,
        updated_at=rec["updated_at"]
    )


async def get_days_class_attendance_agg(
    db: AsyncSession,
    tenant_id: str,
    class_code: str
) -> List[ClassAttendanceDaySummary]:
    """Get class attendance aggregation by day of week."""
    
    await _validate_institution_exists(db, tenant_id)

    query = await db.execute(
        select(DaysClassAttendanceAggDB).where(
            and_(
                DaysClassAttendanceAggDB.tenant_id == tenant_id,
                DaysClassAttendanceAggDB.class_code == class_code,
            )
        ).order_by(DaysClassAttendanceAggDB.week_day)
    )
    rows = query.scalars().all()
    
    return [
        ClassAttendanceDaySummary(
            class_code=class_code,
            total=r.total,
            present=r.present,
            week_day=r.week_day,
            updated_at=r.updated_at,
            created_on=r.created_on
        )
        for r in rows
    ]


async def get_days_institution_attendance_agg(
    db: AsyncSession,
    tenant_id: str
) -> List[InstitutionAttendanceDaySummary]:
    """Get institution attendance aggregation by day of week."""
    
    await _validate_institution_exists(db, tenant_id)

    query = await db.execute(
        select(DaysInstitutionAttendanceAggDB)
        .where(DaysInstitutionAttendanceAggDB.tenant_id == tenant_id)
        .order_by(DaysInstitutionAttendanceAggDB.week_day)
    )

    rows = query.scalars().all()

    return [
        InstitutionAttendanceDaySummary(
            total=r.total,
            present=r.present,
            week_day=r.week_day,
            updated_at=r.updated_at,
            created_on=r.created_on
        )
        for r in rows
    ]


async def get_students_for_attendance(
    db: AsyncSession, 
    class_code: str,
    tenant_id: str
) -> List[StudentForMarkAttendance]:
    """Get students for marking attendance."""
    
    query = select(
        UserDB.id.label('user_id'),
        UserDB.user_name,
        UserDB.first_name,
        UserDB.last_name,
        StudentDB.roll_number
    ).join(
        StudentDB, UserDB.id == StudentDB.user_id
    ).where(
        StudentDB.class_code == class_code,
        UserDB.tenant_id == tenant_id,
    ).order_by(
        StudentDB.roll_number
    )
    
    result = await db.execute(query)
    rows = result.all()
    
    return [
        StudentForMarkAttendance(
            class_code=class_code,  
            **dict(row._mapping)
        )
        for row in rows
    ]


async def get_students_for_attendance_update(
    db: AsyncSession,
    attendance_date: datetime.date,
    subject: str,
    class_code: str,
    tenant_id: str,
) -> List[StudentForUpdateAttendance]:
    """Get students with existing attendance for update."""
    normalized_subject = subject.capitalize()
    
    query = (
        select(
            UserDB.id.label('user_id'),
            UserDB.user_name,
            UserDB.first_name,
            UserDB.last_name,
            StudentDB.roll_number,
            StudentAttendanceDB.status
        )
        .join(StudentDB, UserDB.id == StudentDB.user_id)
        .join(
            StudentAttendanceDB,
            StudentDB.id == StudentAttendanceDB.student_id
        )
        .where(
            StudentDB.class_code == class_code,
            UserDB.tenant_id == tenant_id,
            StudentAttendanceDB.date == attendance_date,
            StudentAttendanceDB.subject == normalized_subject
        )
        .order_by(StudentDB.roll_number)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        StudentForUpdateAttendance(
            class_code=class_code,
            subject=normalized_subject,
            **row._mapping
        )
        for row in rows
    ]


async def update_students_attendance(
    db: AsyncSession,
    tenant_id: str,
    class_code: str,
    attendance_date: datetime.date,
    subject: str,
    attendance_data: List[StudentForUpdateAttendance]
) -> AttendanceStudentSuccessResponse:
    """Update student attendance records with aggregation adjustments."""
    normalized_subject = subject.capitalize()
    try:
        if isinstance(attendance_date, str):
            attendance_date = datetime.strptime(attendance_date, "%Y-%m-%d").date()
        
        current_year = attendance_date.year
        current_month = attendance_date.month
        current_weekday = attendance_date.weekday()
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_str = weekday_names[current_weekday]
        
        # Verify class exists
        class_check = await db.execute(
            select(exists().where(
                InstitutionDB.tenant_id == tenant_id,
                ClassDB.class_code == class_code,
                ClassDB.institution_id == InstitutionDB.id
            ))
        )
        if not class_check.scalar():
            raise ValueError(f"Class {class_code} not found")
        
        roll_numbers_to_update = [record.roll_number for record in attendance_data]
        
        if not roll_numbers_to_update:
            raise ValueError("No attendance records provided for update")
        
        # Get existing attendance records
        attendance_query = await db.execute(
            select(StudentAttendanceDB)
            .options(selectinload(StudentAttendanceDB.student).selectinload(StudentDB.user))
            .where(
                and_(
                    StudentAttendanceDB.class_code == class_code,
                    StudentAttendanceDB.date == attendance_date,
                    StudentAttendanceDB.subject == normalized_subject,
                    StudentAttendanceDB.student.has(StudentDB.roll_number.in_(roll_numbers_to_update))
                )
            )
        )
        existing_records = {rec.student.roll_number: rec for rec in attendance_query.scalars().all()}
        
        if not existing_records:
            raise ValueError(f"No attendance records found for the specified students")
        
        # Identify records needing update
        records_to_update = []
        
        for update_data in attendance_data:
            if update_data.roll_number not in existing_records:
                continue
            
            attendance_record = existing_records[update_data.roll_number]
            old_status = attendance_record.status
            new_status = update_data.status
            
            if old_status == new_status:
                continue
            
            records_to_update.append({
                'update_data': update_data,
                'attendance_record': attendance_record,
                'old_status': old_status,
                'new_status': new_status
            })
        
        if not records_to_update:
            return AttendanceStudentSuccessResponse(
                message="No changes detected",
                students_processed=0,
                present_count=0,
                absent_count=0,
                late_count=0,
                class_code=class_code,
                attendance_date=attendance_date
            )
        
        status_changes = {}
        total_students_updated = 0
        
        for record_info in records_to_update:
            attendance_record = record_info['attendance_record']
            old_status = record_info['old_status']
            new_status = record_info['new_status']
            
            old_is_present = old_status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
            new_is_present = new_status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
            
            user_id = attendance_record.student.user_id
            user_name = attendance_record.student.user.user_name
            status_changes[user_id] = {
                'user_name': user_name,
                'old_status': old_status,
                'new_status': new_status,
                'old_present': old_is_present,
                'new_present': new_is_present,
                'subject': normalized_subject
            }
            
            attendance_record.status = new_status
            total_students_updated += 1
        
        present_count = sum(1 for r in records_to_update if r['new_status'] == AttendanceStatus.PRESENT)
        absent_count = sum(1 for r in records_to_update if r['new_status'] == AttendanceStatus.ABSENT)
        late_count = sum(1 for r in records_to_update if r['new_status'] == AttendanceStatus.LATE)
        
        net_present_change_for_class = 0
        
        for user_id, change in status_changes.items():
            student_agg_query = await db.execute(
                select(StudentAttendanceAggDB).where(
                    and_(
                        StudentAttendanceAggDB.tenant_id == tenant_id,
                        StudentAttendanceAggDB.user_id == user_id,
                        StudentAttendanceAggDB.year == current_year,
                        StudentAttendanceAggDB.month == current_month,
                        StudentAttendanceAggDB.subject == change['subject']
                    )
                )
            )
            student_agg = student_agg_query.scalars().first()
            
            if not student_agg:
                continue
            
            if change['old_present'] and not change['new_present']:
                student_agg.present -= 1
                net_present_change_for_class -= 1
            elif not change['old_present'] and change['new_present']:
                student_agg.present += 1
                net_present_change_for_class += 1
        
        # Update aggregations
        class_agg_query = await db.execute(
            select(ClassAttendanceAggDB).where(
                and_(
                    ClassAttendanceAggDB.tenant_id == tenant_id,
                    ClassAttendanceAggDB.class_code == class_code,
                    ClassAttendanceAggDB.year == current_year,
                    ClassAttendanceAggDB.month == current_month
                )
            )
        )
        class_agg = class_agg_query.scalars().first()
        if class_agg:
            class_agg.present += net_present_change_for_class

        class_day_agg_query = await db.execute(
            select(DaysClassAttendanceAggDB).where(
                and_(
                    DaysClassAttendanceAggDB.tenant_id == tenant_id,
                    DaysClassAttendanceAggDB.class_code == class_code,
                    DaysClassAttendanceAggDB.week_day == weekday_str
                )
            )
        )
        class_day_agg = class_day_agg_query.scalars().first()
        if class_day_agg:
            class_day_agg.present += net_present_change_for_class
        
        inst_agg_query = await db.execute(
            select(InstitutionAttendanceAggDB).where(
                and_(
                    InstitutionAttendanceAggDB.tenant_id == tenant_id,
                    InstitutionAttendanceAggDB.year == current_year,
                    InstitutionAttendanceAggDB.month == current_month
                )
            )
        )
        inst_agg = inst_agg_query.scalars().first()
        if inst_agg:
            inst_agg.present += net_present_change_for_class
        
        inst_day_agg_query = await db.execute(
            select(DaysInstitutionAttendanceAggDB).where(
                and_(
                    DaysInstitutionAttendanceAggDB.tenant_id == tenant_id,
                    DaysInstitutionAttendanceAggDB.week_day == weekday_str
                )
            )
        )
        inst_day_agg = inst_day_agg_query.scalars().first()
        if inst_day_agg:
            inst_day_agg.present += net_present_change_for_class
        
        await db.commit()
        
        return AttendanceStudentSuccessResponse(
            message="Attendance successfully updated",
            students_processed=total_students_updated,
            present_count=present_count,
            absent_count=absent_count,
            late_count=late_count,
            class_code=class_code,
            attendance_date=attendance_date
        )
        
    except ValueError:
        await db.rollback()
        raise
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating attendance: {e}", exc_info=True)
        raise DatabaseError("Unable to update attendance records")


# ==================== STAFF ATTENDANCE ====================

async def create_staff_attendance(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    attendance_data: StaffAttendanceCreate,
    auto_commit: bool = True
) -> dict:
    """Create staff attendance record with aggregation updates."""
    
    try:
        attendance_date = attendance_data.attendance_date or datetime.now().date()

        user_query = await db.execute(
            select(UserDB.user_name).where(
                UserDB.id == user_id,
                UserDB.tenant_id == tenant_id
            )
        )
        user_name = user_query.scalars().first()
        
        if not user_name:
            raise UserNotFoundException(f"User not found")

        # Check if already marked
        already_marked_check = await db.execute(
            select(exists().where(
                StaffAttendanceDB.date == attendance_date,
                StaffAttendanceDB.user_id == user_id
            ))
        )

        if already_marked_check.scalar():
            raise DatabaseError(f"Attendance already marked for {user_name} on {attendance_date}")

        current_year = attendance_date.year
        current_month = attendance_date.month
        current_weekday = attendance_date.weekday()
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_str = weekday_names[current_weekday]

        attendance_record = StaffAttendanceDB(
            user_id=user_id,
            date=attendance_date,
            status=attendance_data.status,
            sign_in_time=attendance_data.sign_in_time,
            sign_out_time=attendance_data.sign_out_time,
            late_duration=attendance_data.late_duration
        )
        db.add(attendance_record)

        is_present = attendance_data.status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]

        # Update monthly aggregation
        staff_agg_query = await db.execute(
            select(StaffAttendanceAggDB).where(
                StaffAttendanceAggDB.user_id ==user_id,
                StaffAttendanceAggDB.month == current_month,
                StaffAttendanceAggDB.year == current_year,
                StaffAttendanceAggDB.tenant_id == tenant_id
            )
        )
        staff_agg = staff_agg_query.scalars().first()
        
        if staff_agg:
            staff_agg.total += 1
            if is_present:
                staff_agg.present += 1
        else:
            staff_agg = StaffAttendanceAggDB(
                tenant_id=tenant_id,
                user_id=user_id,
                user_name=user_name,
                month=current_month,
                year=current_year,
                total=1,
                present=1 if is_present else 0,
                late_count=1 if attendance_data.status == AttendanceStatus.LATE else 0
            )
            db.add(staff_agg)

        # Update day-wise aggregation
        day_staff_agg_query = await db.execute(
            select(DaysStaffAttendanceAggDB).where(
                DaysStaffAttendanceAggDB.tenant_id == tenant_id,
                DaysStaffAttendanceAggDB.week_day == weekday_str,
                DaysStaffAttendanceAggDB.user_id == user_id
            )
        )
        day_staff_agg = day_staff_agg_query.scalars().first()
        
        if day_staff_agg:
            if day_staff_agg.week_day == "Monday":
                day_staff_agg.total = 0
                day_staff_agg.present = 0
            day_staff_agg.total += 1
            if is_present:
                day_staff_agg.present += 1
        else:
            day_staff_agg = DaysStaffAttendanceAggDB(
                tenant_id=tenant_id,
                user_id=user_id,
                user_name=user_name,
                week_day=weekday_str,
                total=1,
                present=1 if is_present else 0,
            )
            db.add(day_staff_agg)
        if auto_commit:
            await db.commit()
            await db.refresh(attendance_record)

        return {
            "message": f"Attendance successfully submitted for {attendance_date}",
            "attendance_id": attendance_record.id,
            "date": str(attendance_date),
            "status": attendance_data.status.value if hasattr(attendance_data.status, 'value') else attendance_data.status
        }

    except (ValueError, UserNotFoundException):
        await db.rollback()
        raise
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating staff attendance: {e}", exc_info=True)
        raise DatabaseError("Unable to create attendance record")


async def update_staff_attendance(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    attendance_data: StaffAttendanceUpdate
) -> dict:
    """Update staff attendance record with aggregation adjustments."""
    
    try:
        attendance_date = attendance_data.attendance_date or datetime.now().date()

        user_query = await db.execute(
            select(UserDB.user_name).where(
                UserDB.id == user_id,
                UserDB.tenant_id == tenant_id
            )
        )
        user_name = user_query.scalars().first()
        
        if not user_name:
            raise UserNotFoundException(f"User {attendance_data.user_name} not found")

        existing_attendance_query = await db.execute(
            select(StaffAttendanceDB).where(
                StaffAttendanceDB.date == attendance_date,
                StaffAttendanceDB.user_id == user_id
            )
        )
        existing_attendance = existing_attendance_query.scalars().first()
        
        if not existing_attendance:
            raise ValueError(f"Attendance not found for {user_name} on {attendance_date}")

        old_status = existing_attendance.status
        new_status = attendance_data.status

        current_year = attendance_date.year
        current_month = attendance_date.month
        current_weekday = attendance_date.weekday()
        weekday_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_str = weekday_names[current_weekday]

        old_is_present = old_status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
        new_is_present = new_status in [AttendanceStatus.PRESENT, AttendanceStatus.LATE]
        old_is_late = old_status == AttendanceStatus.LATE
        new_is_late = new_status == AttendanceStatus.LATE

        existing_attendance.status = new_status
        existing_attendance.late_duration = attendance_data.late_duration
        
        if hasattr(attendance_data, 'sign_in_time') and attendance_data.sign_in_time:
            existing_attendance.sign_in_time = attendance_data.sign_in_time
        if hasattr(attendance_data, 'sign_out_time') and attendance_data.sign_out_time:
            existing_attendance.sign_out_time = attendance_data.sign_out_time

        # Update monthly aggregation
        staff_agg_query = await db.execute(
            select(StaffAttendanceAggDB).where(
                StaffAttendanceAggDB.user_id == user_id,
                StaffAttendanceAggDB.month == current_month,
                StaffAttendanceAggDB.year == current_year,
                StaffAttendanceAggDB.tenant_id == tenant_id
            )
        )
        staff_agg = staff_agg_query.scalars().first()
        
        if staff_agg:
            if old_is_present and not new_is_present:
                staff_agg.present = max(0, staff_agg.present - 1)
            elif not old_is_present and new_is_present:
                staff_agg.present = staff_agg.present + 1
            
            if old_is_late and not new_is_late:
                staff_agg.late_count = max(0, (staff_agg.late_count or 0) - 1)
            elif not old_is_late and new_is_late:
                staff_agg.late_count = (staff_agg.late_count or 0) + 1

        # Update day-wise aggregation
        day_staff_agg_query = await db.execute(
            select(DaysStaffAttendanceAggDB).where(
                DaysStaffAttendanceAggDB.tenant_id == tenant_id,
                DaysStaffAttendanceAggDB.week_day == weekday_str,
                DaysStaffAttendanceAggDB.user_id == user_id
            )
        )
        day_staff_agg = day_staff_agg_query.scalars().first()

        if day_staff_agg:
            if old_is_present and not new_is_present:
                day_staff_agg.present = max(0, day_staff_agg.present - 1)
            elif not old_is_present and new_is_present:
                day_staff_agg.present = day_staff_agg.present + 1

        await db.commit()
        await db.refresh(existing_attendance)

        return {
            "message": f"Attendance successfully updated for {attendance_date}",
            "attendance_id": existing_attendance.id,
            "date": str(attendance_date),
            "old_status": old_status.value if hasattr(old_status, 'value') else old_status,
            "new_status": new_status.value if hasattr(new_status, 'value') else new_status,
            "late_duration": str(attendance_data.late_duration) if attendance_data.late_duration else None
        }

    except (ValueError, UserNotFoundException):
        await db.rollback()
        raise
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating staff attendance: {e}", exc_info=True)
        raise DatabaseError("Unable to update attendance record")


async def get_full_month_staff_attendance(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    month: int,
    year: int
) -> List[StaffAttendanceResponse]:
    """Get full month staff attendance records."""
    
    if not (1 <= month <= 12):
        raise ValueError(f"Invalid month {month}")
    
    if year < 1900 or year > 2100:
        raise ValueError(f"Invalid year {year}")

    await _validate_institution_exists(db, tenant_id)

    user_query = await db.execute(
        select(UserDB).where(
            UserDB.id == user_id,
            UserDB.tenant_id == tenant_id
        )
    )
    user = user_query.scalars().first()
    
    if not user:
        raise UserNotFoundException(f"User not found")

    attendance_query = await db.execute(
        select(StaffAttendanceDB)
        .where(
            StaffAttendanceDB.user_id == user.id,
            extract("year", StaffAttendanceDB.date) == year,
            extract("month", StaffAttendanceDB.date) == month
        )
        .order_by(StaffAttendanceDB.date.asc())
    )
    
    attendance_records = attendance_query.scalars().all()

    return [
        StaffAttendanceResponse(
            attendance_date=record.date,
            status=record.status.value if hasattr(record.status, "value") else record.status,
            sign_in_time=record.sign_in_time,
            sign_out_time=record.sign_out_time,
            late_duration=record.late_duration
        )
        for record in attendance_records
    ]


async def get_staff_attendance_summary(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    month: int,
    year: int
) -> dict:
    """Get staff attendance summary for a month."""
    
    if not (1 <= month <= 12):
        raise ValueError(f"Invalid month {month}")
    
    if year < 1900 or year > 2100:
        raise ValueError(f"Invalid year {year}")

    await _validate_institution_exists(db, tenant_id)

    user_id_query = await db.execute(
        select(UserDB.id).where(
            UserDB.id == user_id,
            UserDB.tenant_id == tenant_id
        )
    )
    user_id = user_id_query.scalars().first()
    
    if not user_id:
        raise UserNotFoundException(f"User not found")

    staff_attendance_agg_query = await db.execute(
        select(StaffAttendanceAggDB).where(
            and_(
                StaffAttendanceAggDB.tenant_id == tenant_id,
                StaffAttendanceAggDB.user_id == user_id,
                StaffAttendanceAggDB.year == year,
                StaffAttendanceAggDB.month == month
            )
        )
    )
    staff_attendance_agg_data = staff_attendance_agg_query.scalars().first()

    if not staff_attendance_agg_data:
        return {
            "user_id": user_id,
            "month": month,
            "year": year,
            "summary": {
                "total": 0,
                "present": 0,
                "absent": 0,
                "late_count": 0,
                "late_duration": None,
                "attendance_percentage": 0.0
            },
            "message": "No attendance records found"
        }

    total = staff_attendance_agg_data.total or 0
    present = staff_attendance_agg_data.present or 0
    absent = total - present
    late_count = staff_attendance_agg_data.late_count or 0
    late_duration = staff_attendance_agg_data.late_duration
    
    attendance_percentage = (present / total * 100) if total > 0 else 0.0

    month_names = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    month_name = month_names[month - 1]

    return {
        "user_id": user_id,
        "month": month,
        "year": year,
        "month_name": month_name,
        "summary": {
            "total": total,
            "present": present,
            "absent": absent,
            "late_count": late_count,
            "late_duration": str(late_duration) if late_duration else None,
            "attendance_percentage": round(attendance_percentage, 2),
            "on_time": present - late_count
        }
    }


async def get_staff_attendance_day_wise_summary(
    db: AsyncSession,
    tenant_id: str,
    user_id: int
) -> List[StaffAttendanceDayAggResponse]:
    """Get day-wise staff attendance summary."""
    
    await _validate_institution_exists(db, tenant_id)

    day_order = {
        "Monday": 1, "Tuesday": 2, "Wednesday": 3, "Thursday": 4,
        "Friday": 5, "Saturday": 6, "Sunday": 7
    }

    query = await db.execute(
        select(DaysStaffAttendanceAggDB).where(
            DaysStaffAttendanceAggDB.tenant_id == tenant_id,
            DaysStaffAttendanceAggDB.user_id == user_id
        )
    )
    rows = query.scalars().all()

    sorted_rows = sorted(rows, key=lambda x: day_order.get(x.week_day, 8))

    return [
        StaffAttendanceDayAggResponse.model_validate(r, from_attributes=True)
        for r in sorted_rows
    ]


async def get_staff_all_attendance_for_date(
    db: AsyncSession,
    tenant_id: str,
    date: datetime.date
) -> List[dict]:
    """Get all staff attendance for a specific date."""
    
    try:
        result = await db.execute(
            select(StaffAttendanceDB, UserDB.user_name)
            .join(UserDB, UserDB.id == StaffAttendanceDB.user_id)
            .where(
                UserDB.tenant_id == tenant_id,
                UserDB.role != UserRoleEnum.STUDENT,
                StaffAttendanceDB.date == date
            )
        )

        rows = result.all()

        response = []
        for attendance, user_name in rows:
            response.append({
                "user_name": user_name,
                "attendance_date": attendance.date,
                "status": attendance.status.value if hasattr(attendance.status, "value") else attendance.status,
                "sign_in_time": attendance.sign_in_time,
                "sign_out_time": attendance.sign_out_time,
                "late_duration": attendance.late_duration,
            })

        return response

    except Exception as e:
        logger.error(f"Error retrieving staff attendance for date: {e}", exc_info=True)
        raise DatabaseError("Unable to retrieve staff attendance data")
    




# QR ATTENDANCE
async def create_attendance_qr_session(user_id, tenant_id, role, db: AsyncSession):

    if role in ["principal", "other_staff", "teacher", "admin"]:
        accepted_role = "staff"
    else:
        accepted_role = role

    existing = await db.execute(
        select(QRAttendanceSessionDB).where(
            QRAttendanceSessionDB.tenant_id == tenant_id,
            QRAttendanceSessionDB.role == accepted_role
        )
    )
    existing_session = existing.scalar_one_or_none()

    try:
        if existing_session:
            await db.delete(existing_session)

        new_session = QRAttendanceSessionDB(
            tenant_id=tenant_id,
            created_by=user_id,
            session_token=str(uuid.uuid4()),
            role=accepted_role, 
            expires_at=datetime.utcnow() + timedelta(seconds=60),
        )

        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)
        return new_session

    except Exception as e:
        await db.rollback()
        raise DatabaseError("Unable to generate QR right now", e)
    
async def validate_attendance_token(
    db: AsyncSession,
    tenant_id: str,
    role: str,
    token: str
):
    # Fetch session (no expiry logic here)
    existing_session_q = await db.execute(
        select(QRAttendanceSessionDB).where(
            QRAttendanceSessionDB.tenant_id == tenant_id,
            QRAttendanceSessionDB.session_token == token,
            QRAttendanceSessionDB.role == role
        )
    )

    session = existing_session_q.scalar_one_or_none()

    # Check if exists
    if not session:
        raise DatabaseError("Invalid QR code")

    # Expiry check with grace time
    GRACE_SECONDS = 5
    current_time = datetime.utcnow()

    if current_time > session.expires_at + timedelta(seconds=GRACE_SECONDS):
        raise DatabaseError("QR code expired, ask teacher/admin to refresh")

    return session
    
    
    


async def create_attendance_audit(
        user_id: int,
        device_fingerprint:str,
        gps_lat:float,
        gps_lng:float,
        is_student: bool,
        db:AsyncSession,
        staff_attendance_id: Optional[int] = None,
        student_attendance_id: Optional[int] = None,
        auto_commit: bool = True

):
    if not staff_attendance_id and not student_attendance_id:
        return None

    try:
        audit = AttendanceAuditDB(
            staff_attendance_id=staff_attendance_id, 
            student_attendance_id=student_attendance_id, 
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            gps_lat=gps_lat,
            gps_lng=gps_lng,
            is_student = is_student
        )
        db.add(audit)
        if auto_commit:
            await db.commit()
            await db.refresh(audit)
    except Exception as e:
        await db.rollback()
        logger.error(f"Scan attendance failed: {e}", exc_info=True)  
        raise DatabaseError("Unable to generate QR right now")