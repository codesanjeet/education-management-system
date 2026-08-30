# from app.models.user_model import UserDB
from sqlalchemy import Column, Integer, String,Numeric, Date,Enum as SAEnum,event,  DateTime, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from  ..base import Base
from datetime import datetime
from datetime import date

from enum import Enum

class StudentStatus(str, Enum):
    COMPLETED = "completed"
    DROPPED = "dropped"
    SUSPENDED = "suspended"
    REMOVED = "removed"
    ACTIVE = "active"



class StudentDB(Base):
    __tablename__ = "students"
    
    # Primary identification
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Student identification
    roll_number = Column(String(20), nullable=False, index=True)  # Made unique
    class_code = Column(String(20), nullable=False, index=True)  # e.g., "CSE101A"
        
    # Guardian information
    father_name = Column(String(100), nullable=True)
    mother_name = Column(String(100), nullable=True)
    guardian_name = Column(String(100), nullable=True)
    guardian_relation = Column(String(20), nullable=True)  # Father, Mother, Uncle, etc.
    guardian_email = Column(String(100), nullable=True)
    guardian_address = Column(Text, nullable=True)
    guardian_contact_num = Column(String(15), nullable=False)
    guardian_contact_num_country_code = Column(String(5), nullable=False ,default="91")

    guardian_alternative_contact_num = Column(String(15), nullable=True)
    guardian_alternative_contact_num_country_code = Column(String(5), nullable=True ,default="91")

    
    # Additional metadata
    emergency_contact = Column(String(15), nullable=True)
    medical_conditions = Column(Text, nullable=True)
    special_needs = Column(Text, nullable=True)

 
    # Status and metadata
    # student_status = Column(SAEnum(StudentStatus), default="active")  # active, graduated, dropped, suspended
    student_status = Column(
    SAEnum(StudentStatus, values_callable=lambda x: [e.value for e in x]),
    nullable=False,default="active"
)  # active, graduated, dropped, suspended
    issue_admit_card = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)

    
    # Relationships
    attendance = relationship("StudentAttendanceDB",uselist=True, back_populates="student", passive_deletes=True)
    fees = relationship("StudentFeesDB", uselist=False, back_populates="student", passive_deletes=True )
    grades = relationship("StudentGradeDB", uselist=True, back_populates="student", passive_deletes=True )
    disciplinary_records = relationship("DisciplinaryRecordDB", uselist=True, back_populates="student", passive_deletes=True )
    user = relationship("UserDB", back_populates="student", lazy="joined")
    # Table constraints
    __table_args__ = (
        UniqueConstraint('roll_number', 'class_code', name='unique_roll_per_class'),
    )
@event.listens_for(StudentDB, "before_insert")
@event.listens_for(StudentDB, "before_update")
def lowercase_student_fields(mapper, connection, target):
    if target.guardian_email:
        target.guardian_email = target.guardian_email.lower()

class AttendanceStatus(Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    # UNMARK = "unmark"



class StudentAttendanceDB(Base):
    __tablename__ = "student_attendance"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_code = Column(String(20), nullable=False, index=True) 
    subject = Column(String(255) , nullable=True,default='all')
    date = Column(Date, nullable=False, default=date.today)
    # status = Column(SAEnum(AttendanceStatus), nullable=False)
    status = Column(
    SAEnum(AttendanceStatus, values_callable=lambda x: [e.value for e in x]),
    nullable=False
)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)
    # Relationship with Student
    student = relationship("StudentDB", back_populates="attendance")  



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
  

class StudentFeesDB(Base):
    __tablename__ = "fee_cards"
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    total_fee = Column(Numeric(10, 2), nullable=False, default=0)  # Example: 50000.00
    due_date = Column(Date, nullable=True)
    total_paid = Column(Numeric(10, 2), nullable=False, default=0)  # Example: 25000.00 (Paid amount)
    total_due = Column(Numeric(10, 2), nullable=False, default=0)  # Example: 25000.00 (Remaining)
    late_fine = Column(Numeric(10, 2), nullable=True ) 

    fee_type = Column(String(20), nullable=False, default="Monthly")  # "Monthly" or "Yearly"
    academic_year = Column(String(25), nullable=False, default=get_current_academic_year)
    
    fee_breakdown = Column(JSONB, nullable=True, default=[])  
    # Example:
    # [{"month": "January", "amount": 5000, "paid": 5000, "due": 0, "date_paid": "2024-01-15"},
    #  {"month": "February", "amount": 5000, "paid": 3000, "due": 2000, "date_paid": "2024-02-20"}]

    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)
    updated_by = Column(String(50), nullable=True)

    # Relationship
    student = relationship("StudentDB", back_populates="fees")



class StudentGradeDB(Base):
    __tablename__ = "student_grades"
    
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    subject_code = Column(String(20), nullable=False)
    subject_name = Column(String(100), nullable=False)
    marks_obtained = Column(Integer, nullable=False)
    total_marks = Column(Integer, nullable=False)
    grade = Column(String(5), nullable=True)
    academic_year = Column(String(25), nullable=False)
    exam_date = Column(Date, nullable=False )
    publish_date = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)

    
    student = relationship("StudentDB", back_populates="grades")
class DisciplinaryRecordDB(Base):
    __tablename__ = "disciplinary_records"
    
    id = Column(Integer, primary_key=True)

    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)

    incident_date = Column(Date, nullable=False)
    incident_level = Column(String(50), nullable=False)
    description = Column(Text, nullable=False)
    action_taken = Column(String(100), nullable=True)
    reported_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
# for make editable or not
    is_locked = Column(Boolean, default=False)

    student = relationship("StudentDB", back_populates="disciplinary_records")
