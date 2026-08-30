from sqlalchemy import Column, Integer, String, DateTime,ForeignKey, Time,Date,Float,Boolean
from datetime import datetime
from .base import Base

# for both staff and student 
class AttendanceAuditDB(Base):
    __tablename__ = "attendance_audit"

    id = Column(Integer, primary_key=True, index=True)
    student_attendance_id = Column(Integer, ForeignKey("student_attendance.id", ondelete="CASCADE"), nullable=True)
    staff_attendance_id = Column(Integer, ForeignKey("staff_attendance.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(Integer, nullable=False)
    is_student = Column(Boolean, nullable=False, default=True)
    # session_token = Column(String(64), nullable=False)   # which QR was used
    device_fingerprint = Column(String(255), nullable=True)
    gps_lat = Column(Float, nullable=True)
    gps_lng = Column(Float, nullable=True)
    marked_at = Column(DateTime, default=lambda: datetime.utcnow())

# Student Attendance Aggregate
class StudentAttendanceAggDB(Base):
    __tablename__ = "students_attendance_agg"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_name = Column(String(25), nullable=False, index=True)
    year = Column(Integer, nullable=False ,index=True)
    subject = Column(String(255), nullable=False, default="all")
    month = Column(Integer, nullable=False ,index=True)
    present = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)



# Class Attendance Aggregate
class ClassAttendanceAggDB(Base):
    __tablename__ = "classes_attendance_agg"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    class_code = Column(String(15), nullable=False, index=True)
    year = Column(Integer, nullable=False ,index=True)
    month = Column(Integer, nullable=False ,index=True)
    present = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)



# Days-wise Class Attendance Aggregate
class DaysClassAttendanceAggDB(Base):
    __tablename__ = "days_classes_attendance_agg"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    class_code = Column(String(15), nullable=False, index=True)
    week_day = Column(String(10), nullable=False, index=True)  # Example: "Monday", "Tuesday"
    present = Column(Integer, nullable=False, default=0)
    created_on = Column(Date, nullable=False, default=lambda: datetime.utcnow())
    total = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)


#Days-wise Institution Attendance Aggregate
class DaysInstitutionAttendanceAggDB(Base):
    __tablename__ = "days_institution_attendance_agg"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    week_day = Column(String(10), nullable=False)  # Example: "Monday", "Tuesday"
    present = Column(Integer, nullable=False, default=0)
    created_on = Column(Date, nullable=False, default=lambda: datetime.utcnow())
    total = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)



# Institution Attendance Aggregate
class InstitutionAttendanceAggDB(Base):
    __tablename__ = "institution_attendance_agg"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    year = Column(Integer, nullable=False ,index=True)
    month = Column(Integer, nullable=False ,index=True)
    present = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)


# Staff
class StaffAttendanceAggDB(Base):
    __tablename__ = "staffs_attendance_agg"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_name = Column(String(25), nullable=False, index=True)
    year = Column(Integer, nullable=False ,index=True)
    month = Column(Integer, nullable=False ,index=True)
    present = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)
    late_count = Column(Integer, nullable=True)
    late_duration = Column(Time, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)


# Days-wise staff Attendance Aggregate
class DaysStaffAttendanceAggDB(Base):
    __tablename__ = "days_staffs_attendance_agg"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    user_name = Column(String(25), nullable=False, index=True)
    week_day = Column(String(10), nullable=False)  # Example: "Monday", "Tuesday"
    present = Column(Integer, nullable=False, default=0)
    created_on = Column(Date, nullable=False, default=lambda: datetime.utcnow())
    total = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)


# QR  Attendance 
import enum
from sqlalchemy import Column, Enum as SAEnum

class QRRoleType(str, enum.Enum):
    STUDENT = "student"
    STAFF = "staff"

qr_role_enum = SAEnum(
    QRRoleType,
    name="qrroletype",       
    create_type=True,
    values_callable=lambda x: [e.value for e in x]         
)

class QRAttendanceSessionDB(Base):
    __tablename__ = "qr_attendance_sessions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(8), nullable=False, index=True)
    created_by = Column(Integer, nullable=False)
    session_token = Column(String(64), unique=True, index=True, nullable=False)
    role = Column(qr_role_enum, nullable=False)  
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    expires_at = Column(DateTime, nullable=False)

