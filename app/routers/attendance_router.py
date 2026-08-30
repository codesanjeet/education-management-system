from fastapi import APIRouter, Depends, status, Query,requests,HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import date

from ..core.database import get_db
from ..schemas.attendance_schema import (
    BulkAttendanceCreate,
    AttendanceType,
    AttendanceStudentSuccessResponse,
    StudentForUpdateAttendance,
    StaffAttendanceCreate,
    StaffAttendanceUpdate,
    AttendanceScanRequest,
    IndividualAttendanceCreate,
)
from ..crud.attendance_crud import (
    create_student_attendance,
    get_full_month_student_attendance,
    get_student_attendance_summary,
    get_class_attendance_agg,
    get_days_institution_attendance_agg,
    get_institution_attendance_agg,
    get_days_class_attendance_agg,
    get_students_for_attendance,
    get_students_for_attendance_update,
    update_students_attendance,
    create_staff_attendance,
    update_staff_attendance,
    get_full_month_staff_attendance,
    get_staff_attendance_summary,
    get_staff_attendance_day_wise_summary,
    get_staff_all_attendance_for_date,
    create_attendance_qr_session,
    create_attendance_audit,
    validate_attendance_token,
    create_individual_student_attendance
)
from ..crud.student_curd import get_student_data_by_id
from ..deps import require_permission,require_permission_or_owner,get_current_user
from ..schemas.user_schema import CurrentUserResponse
from ..models.attendance_model import QRRoleType
router = APIRouter()


# ==================== STUDENT ATTENDANCE ====================

@router.post(
    "/institutions/classes/{class_code}/attendance",
    response_model=AttendanceStudentSuccessResponse,
    status_code=status.HTTP_201_CREATED
)
async def mark_class_attendance(
    class_code: str,
    attendance_data: BulkAttendanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:student_attendance_management"))
):
    """
 Mark attendance for students in a class.
    """
    
    response = await create_student_attendance(
        db=db,
        tenant_id=current_user.tenant_id,
        attendance_data=attendance_data,
        class_code = class_code
    )
    
    return response


@router.patch(
    "/institutions/classes/{class_code}/attendance",
    status_code=status.HTTP_200_OK
)
async def update_class_attendance(
    class_code: str,
    attendance_data: List[StudentForUpdateAttendance],
    attendance_date: date = Query(...),
    subject: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:student_attendance_management"))
):
    """
    Update existing attendance records.
    """
    result = await update_students_attendance(
        db=db,
        tenant_id=current_user.tenant_id,
        class_code=class_code,
        attendance_date=attendance_date,
        subject=subject,
        attendance_data=attendance_data
    )
    return result


@router.get(
    "/institutions/classes/{class_code}/students",
    status_code=status.HTTP_200_OK
)
async def get_class_students(
    class_code: str,
    attendance_date: date = Query(None),
    subject: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:student_attendance_management"))
):
    """
    Get students for attendance marking or updating.

    
    **Two modes:**
    1. **For marking new attendance** - Only provide class_code
       - Returns: List of students without attendance data
       
    2. **For updating existing attendance** - Provide attendance_date and subject
       - Returns: List of students WITH their existing attendance data
    

    """
    if attendance_date and subject:
        result = await get_students_for_attendance_update(
            tenant_id=current_user.tenant_id,
            attendance_date=attendance_date,
            class_code=class_code,
            subject=subject,
            db=db
        )
    else:
        result = await get_students_for_attendance(
            db=db,
            tenant_id=current_user.tenant_id,
            class_code=class_code
        )
    
    return result


@router.get(
    "/institutions/students/{user_id}/attendance",
    status_code=status.HTTP_200_OK
)
async def get_student_attendance(
    user_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    type: AttendanceType = Query(AttendanceType.FULL),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_permission_or_owner("attendance:student_attendance_management"))
):
    """
    Get student attendance data.

    **Two modes based on 'type' parameter:**
    
    1. **type=full** (default) - Detailed day-by-day attendance records
       - Returns: List of all attendance entries for the month
       - Required params: month, year
 
    2. **type=summary** - Aggregated statistics
       - Returns: Total counts (present/absent/late) and attendance percentage
       - Required params: month, year
  
    """
    if type == AttendanceType.SUMMARY:
        result = await get_student_attendance_summary(
            db=db,
            tenant_id=current_user["current_user"].tenant_id,
            user_id=user_id,
            month=month,
            year=year
        )
        return {"message": "Attendance summary retrieved", "data": result}
    
    else:
        result = await get_full_month_student_attendance(
            db=db,
            tenant_id=current_user["current_user"].tenant_id,
            user_id=user_id,
            month=month,
            year=year
        )
        return {"message": "Full month attendance retrieved", "data": result}


@router.get(
    "/institutions/classes/{class_code}/attendance/summary",
    status_code=status.HTTP_200_OK
)
async def get_class_summary(
    class_code: str,
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None, ge=2000),
    type: AttendanceType = Query(AttendanceType.SUMMARY),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:student_attendance_management"))
):
    """
    Get class attendance summary.
    
    **Two modes based on 'type' parameter:**
    
    1. **type=summary** (default) - Monthly aggregated statistics
       - Returns: Total counts (present/absent/late) for the specified month
       - Required params: month, year

    
    2. **type=day_wise** - Weekday-based statistics (Monday-Sunday)
       - Returns: All-time attendance patterns grouped by day of week
       - Params: month and year are NOT required (ignored if provided)
    """
    if type == AttendanceType.DAY_WISE:
        result = await get_days_class_attendance_agg(
            db=db,
            tenant_id=current_user.tenant_id,
            class_code=class_code
        )
        return {"message": "Day-wise summary retrieved", "data": result}
    
    else:
        result = await get_class_attendance_agg(
            db=db,
            tenant_id=current_user.tenant_id,
            class_code=class_code,
            month=month,
            year=year
        )
        return {"message": "Monthly summary retrieved", "data": result}


@router.get(
    "/institutions/attendance/summary",
    status_code=status.HTTP_200_OK
)
async def get_institution_summary(
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None, ge=2000),
    type: AttendanceType = Query(AttendanceType.SUMMARY),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:student_attendance_management"))
):
    """
    Get institution-wide attendance summary.
    
    **Two modes based on 'type' parameter:**
    
    1. **type=summary** (default) - Monthly aggregated statistics
       - Returns: Total counts (present/absent/late) for the entire institution
       - Required params: month, year
    
    2. **type=day_wise** - Weekday-based statistics (Monday-Sunday)
       - Returns: All-time attendance patterns grouped by day of week across institution
       - Params: month and year are NOT required (ignored if provided)
    """
    if type == AttendanceType.DAY_WISE:
        result = await get_days_institution_attendance_agg(
            db=db,
            tenant_id=current_user.tenant_id
        )
        return {"message": "Day-wise summary retrieved", "data": result}
    
    else:
        if month is None or year is None:
            raise ValueError("month and year required for summary type")
            
        result = await get_institution_attendance_agg(
            db=db,
            tenant_id=current_user.tenant_id,
            month=month,
            year=year
        )
        return {"message": "Monthly summary retrieved", "data": result}


# ==================== STAFF ATTENDANCE ====================

@router.get(
    "/institutions/staff/attendance",
    status_code=status.HTTP_200_OK
)
async def get_all_staff_attendance(
    date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:staff_attendance_management"))
):
    """
    Get all staff attendance for a specific date.
    
    """
    return await get_staff_all_attendance_for_date(
        date=date,
        tenant_id=current_user.tenant_id,
        db=db
    )


@router.post(
    "/institutions/staff/{user_id}/attendance",
    status_code=status.HTTP_201_CREATED
)
async def mark_staff_attendance(
    attendance_data: StaffAttendanceCreate,
    user_id:int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:staff_attendance_management"))
):
    """
    Mark staff attendance.
    
    """
    response = await create_staff_attendance(
        db=db,
        tenant_id=current_user.tenant_id,
        attendance_data=attendance_data,
        user_id = user_id
    )
    
    return {"message": "Attendance created", "data": response}


@router.patch(
    "/institutions/staff/{user_id}/attendance",
    status_code=status.HTTP_200_OK
)
async def update_staff_attendance_route(
    attendance_data: StaffAttendanceUpdate,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:staff_attendance_management"))
):
    """
    Update staff attendance.
    
    """
    response = await update_staff_attendance(
        db=db,
        tenant_id=current_user.tenant_id,
        attendance_data=attendance_data,
        user_id = user_id
    )

    return {"message": "Attendance updated", "data": response}


@router.get(
    "/institutions/staff/{user_id}/attendance",
    status_code=status.HTTP_200_OK
)
async def get_staff_attendance(
    user_id: int,
    month: int = Query(None, ge=1, le=12),
    year: int = Query(None, ge=1900, le=2100),
    type: AttendanceType = Query(AttendanceType.FULL),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission_or_owner("attendance:staff_attendance_management"))
):
    """
    Get staff attendance data.

    **Three modes based on 'type' parameter:**
    
    1. **type=full** (default) - Detailed day-by-day attendance records
       - Returns: List[StaffAttendanceResponse]
       - Required params: month, year
  
    
    2. **type=summary** - Monthly aggregated statistics
       - Returns: StaffAttendanceAggResponse with totals and percentages
       - Required params: month, year
  
    
    3. **type=day_wise** - Weekday-based statistics (Monday-Sunday)
       - Returns: List[StaffAttendanceDayAggResponse] - All-time patterns by weekday
       - Params: month and year are NOT required (ignored if provided)
  
    """
    if type in [AttendanceType.FULL, AttendanceType.SUMMARY]:
        if month is None or year is None:
            raise ValueError("month and year required")
    
    if type == AttendanceType.SUMMARY:
        result = await get_staff_attendance_summary(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=user_id,
            month=month,
            year=year
        )
        return {"message": "Summary retrieved", "data": result}
    
    elif type == AttendanceType.DAY_WISE:
        result = await get_staff_attendance_day_wise_summary(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=user_id
        )
        return {"message": "Day-wise summary retrieved", "data": result}
    
    else:
        result = await get_full_month_staff_attendance(
            db=db,
            tenant_id=current_user.tenant_id,
            user_id=user_id,
            month=month,
            year=year
        )
        return {"message": "Full month attendance retrieved", "data": result}

# QR


@router.post("/institutions/students/attendance/qr/generate")
async def generate_qr(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:student_attendance_management"))
):

    session = await create_attendance_qr_session(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        role=QRRoleType.STUDENT.value,
        db=db
    )

    return { "token": session.session_token, "expires_in": 60 }


@router.post("/institutions/staff/attendance/qr/generate")
async def generate_qr_staff(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("attendance:staff_attendance_management"))
):

    session = await create_attendance_qr_session(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        role=QRRoleType.STAFF.value,
        db=db
    )

    return { "token": session.session_token, "expires_in": 60 }





@router.post("/institutions/attendance/scan")
async def scan_attendance_qr(
    device_data: AttendanceScanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user)
):
    if current_user.role in ["admin","teacher","other_staff","principal"]:
        attendance_role = "staff"
    else:
        attendance_role = "student"
    
    # . Validate session token exists and not expired
    session =await validate_attendance_token(db=db, tenant_id=current_user.tenant_id,role=attendance_role, token=device_data.session_token )

    # GPS accuracy check — reject if cell tower only
    # if device_data.gps_accuracy and device_data.gps_accuracy > 100:
    #     raise HTTPException(status_code=400, detail="Location accuracy too low, move to open area")

    try:
        if session.role == "staff":
            staff_attendance = await create_staff_attendance(
                tenant_id= current_user.tenant_id,
                user_id= current_user.id,
                db= db,
                auto_commit=False,
                attendance_data=StaffAttendanceCreate(
                    status="present",
                )
            )

            await create_attendance_audit(
                    staff_attendance_id=staff_attendance["attendance_id"],
                    user_id=current_user.id,
                    # session_token=device_data.session_token,
                    device_fingerprint=device_data.device_fingerprint,
                    gps_lat=device_data.gps_lat,
                    gps_lng=device_data.gps_lng,
                    is_student=False,
                    auto_commit=False,
                    db=db
                )
            await db.commit()
        else:

            student = await get_student_data_by_id(
                user_id=current_user.id,
                db=db
            )
            student_attendance = await create_individual_student_attendance(
                db=db,
                tenant_id= current_user.tenant_id,
                user_id= current_user.id,
                attendance_data=IndividualAttendanceCreate(
                    class_code=student.class_code,
                    status= "present",
                    subject= "all",
                )
            )
                        # Create audit record
            await create_attendance_audit(
                    student_attendance_id=student_attendance.attendance_id,
                    user_id=current_user.id,
                    # session_token=device_data.session_token,
                    device_fingerprint=device_data.device_fingerprint,
                    gps_lat=device_data.gps_lat,
                    gps_lng=device_data.gps_lng,
                    is_student=True,
                    auto_commit=False,
                    db=db
                )

        return {"message": "Attendance marked successfully"}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Failed to mark attendance")