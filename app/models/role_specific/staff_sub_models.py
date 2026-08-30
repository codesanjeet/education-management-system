from sqlalchemy import Column, Integer, String, Date, ForeignKey, DateTime,Enum as SAEnum, Numeric ,Time
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from ..base import Base
from datetime import datetime,date
from enum import Enum

class StaffStatus(str, Enum):
    ACTIVE = "active"        # Staff is currently working
    INACTIVE = "inactive"    # Not working currently, but still on record
    FIRED = "fired"          # Employment terminated
    RESIGNED = "resigned"    # Staff resigned voluntarily
    RETIRED = "retired"      # Officially retired
    ON_LEAVE = "on_leave"    # Temporarily away but still employed
    SUSPENDED = "suspended"  # Temporarily removed due to disciplinary or other issues


def get_current_academic_year():
    """Return academic year string like '2025-26' based on current date."""
    now = datetime.now()
    year = now.year
    month = now.month
    # Academic year starts in April
    if month >= 4:
        start_year = year
        end_year = year + 1
    else:
        start_year = year - 1
        end_year = year
    return f"{start_year}-{str(end_year)[-2:]}"  # Example: "2025-26"


# Staff salary
class StaffSalaryDB(Base):
    __tablename__ = "staff_salaries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    total_salary = Column(Numeric(10, 2), nullable=False, default=0)  # Example: 60000.00
    total_paid = Column(Numeric(10, 2), nullable=False, default=0)  # Example: 30000.00 (Paid amount)
    total_due = Column(Numeric(10, 2), nullable=False, default=0)  # Example: 30000.00 (Remaining)

    salary_type = Column(String(50), nullable=False , default="Yearly")  # "Monthly" or "Yearly"
    academic_year = Column(String(25), nullable=False, default=get_current_academic_year)
    
    salary_breakdown = Column(JSONB, nullable=True, default=[])  
    # Example:
    # [{"month": "January", "amount": 50000, "paid": 50000, "due": 0, "date_paid": "2024-01-15"},
    #  {"month": "February", "amount": 50000, "paid": 30000, "due": 20000, "date_paid": "2024-02-20"}]
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)
    # staff_status = Column(SAEnum(StaffStatus), default="active")
    staff_status = Column(
    SAEnum(StaffStatus, values_callable=lambda x: [e.value for e in x]),
    nullable=False,default="active"
)
    
    user = relationship("UserDB", back_populates="staff_salary")

# Enum for Staff Attendance Status
class AttendanceStatus(Enum):
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"
    # UNMARK = "unmark"

# Staff Attendance Table
class StaffAttendanceDB(Base):
    __tablename__ = "staff_attendance"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    # status = Column(SAEnum(AttendanceStatus), nullable=False)
    status = Column(
    SAEnum(AttendanceStatus, values_callable=lambda x: [e.value for e in x]),
    nullable=False
)
    sign_in_time = Column(Time ,nullable=True)  # Useful for tracking working hours
    sign_out_time = Column(Time, nullable=True)
    late_duration = Column(Time, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)

    user = relationship("UserDB", back_populates="staff_attendance")




    