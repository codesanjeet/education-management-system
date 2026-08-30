from sqlalchemy import Column, Integer, String,Boolean, ForeignKey, DateTime,event,Date
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base  
from sqlalchemy.orm import relationship
# from .user_model import UserDB

class ClassDB(Base):
    __tablename__ = "classes"
    
 
    # Primary identification
    id = Column(Integer, primary_key=True, nullable=False, index=True)
    institution_id = Column(
    Integer,
    ForeignKey("institutions.id", ondelete="CASCADE"),
    nullable=False
)
    # Class identification and basic info
    class_code = Column(String(8), nullable=False, unique=True, index=True)  # e.g., "CSE101A"
    section = Column(String(5), nullable=False)  # A, B, C, etc.
    batch = Column(String(10), nullable=True)  # Academic year batch like "2024-25"
    department = Column(String(100), nullable=True, index=True)  # Computer Science, Mechanical, etc.
    program = Column(String(50), nullable=True)  # B.Tech, MBA, M.Tech, etc.
    class_or_year_or_name = Column(String(20), nullable=False)
    academic_year = Column(String(10), nullable=False)  # 2024-25
    
    # Capacity and limits
    max_student_limit = Column(Integer, nullable=False, default=60)
    current_student_count = Column(Integer, nullable=False, default=0)

    
    
    # Class ranking and performance data
    class_score = Column(Integer, nullable=True)
    class_start_at = Column(Integer, nullable=False)
    class_end_at = Column(Integer, nullable=False)
    lunch_start_at = Column(Integer, nullable=True)
    lunch_end_at = Column(Integer, nullable=True)


    morning_assembly_time = Column(Integer, nullable=True)

    
    
    # Classroom 
    primary_classroom = Column(String(20), nullable=True) 
    
    
    # Class performance and statistics
    class_statistics = Column(JSONB, nullable=True, default=dict)
    # Example: {
    #   "average_attendance": 87.5,
    #   "pass_percentage": 92.3,
    #   "discipline_issues": 2,
    #    fee_collection_percentage: 52
    #    participation_percentage : 90
    # }
    
    # Class activities and events
    class_activities = Column(JSONB, nullable=True, default=list)
    # Example: [
    #   {"activity": "Science Fair", "date": "2024-11-15", "participation": 25},
    #   {"activity": "Sports Day", "date": "2024-12-01", "participation": 45}
    # ]
    
    # Class representative and student leadership
    class_representatives = Column(JSONB, nullable=True, default=dict)
    # Example: {
    #   "studennt_role": {"student_id": 126, "name": "Sarah Wilson"}
    #   "class_representative": {"student_id": 123, "name": "John Doe"},
    #   "assistant_cr": {"student_id": 124, "name": "Jane Smith"},
    #   "sports_captain": {"student_id": 125, "name": "Mike Johnson"},
    #   "cultural_secretary": {"student_id": 126, "name": "Sarah Wilson"}
    # }
    
    # Administrative information
    class_status = Column(String(20), default="active")  # active, completed, suspended, archived
    is_active = Column(Boolean, default=True)
    

    exam_schedule = Column(JSONB, nullable=True, default=dict)
    # Example: {
    # exam_name
    # exam_date
    # 
    # }


    
    # Financial information (if applicable)
    fee_structure = Column(JSONB, nullable=True, default=dict)
    # Example: {
    #   "tuition_fee": 50000,
    #   "lab_fee": 5000,
    #   "library_fee": 2000,
    #   "examination_fee": 3000
    # etc
    # }

    # Additional notes and syllabus
    class_syllabus = Column(String(255), nullable=True)
    class_notes = Column(String(255), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # IS DELETED
    deleted_date = Column(Date,nullable=True)
    
    class_schedule = relationship("ClassScheduleDB", back_populates="main_class", uselist=True, passive_deletes=True,lazy="selectin")
    institution = relationship("InstitutionDB", back_populates="class_")
    study_material = relationship("StudyMaterialDB", back_populates="class_")

@event.listens_for(ClassDB, "before_insert")
@event.listens_for(ClassDB, "before_update")
def format_class_fields(mapper, connection, target):
    if target.class_or_year_or_name:
        target.class_or_year_or_name = target.class_or_year_or_name.upper()
    if target.class_code:
        target.class_code = target.class_code.upper()



class ClassScheduleDB(Base):
    __tablename__ = "class_schedule"

    id = Column(Integer, primary_key=True)
    class_id = Column(Integer, ForeignKey("classes.id", ondelete="CASCADE"))
    subject_code = Column(String(20), nullable=True)
    subject_name = Column(String(50), nullable=False)
    teacher_first_name= Column(String(50), nullable=False)
    teacher_last_name= Column(String(50), nullable=False)
    teacher_user_id = Column(Integer, nullable=False)
    class_room = Column(String(20), nullable=True)
    start_time = Column(Integer, nullable=False)
    end_time = Column(Integer, nullable=False)
    day = Column(String(10), nullable=False, default="monday")  # e.g., "Monday"   
    is_class_teacher= Column(Boolean, default=False)
    main_class = relationship("ClassDB",back_populates = "class_schedule" )


class StudyMaterialDB(Base):
    __tablename__ = "study_materials"
    
    id = Column(Integer, primary_key=True ,nullable=False, index=True)
    class_id = Column(Integer,ForeignKey("classes.id", ondelete="CASCADE") ,index=True , nullable=True)
    tenant_id = Column (String, nullable=False)
    class_name = Column(String, nullable=False)
    subject_name = Column(String, nullable=False)
    class_ = relationship("ClassDB", back_populates="study_material")
    title = Column(String, nullable=False)
    description = Column(String)
    downloadable = Column(Boolean , default=False, nullable=False)
    # Store the complete URL path
    file_url = Column(String, nullable=False)  
    file_type = Column(String, nullable=False) 
    
    uploaded_at = Column(DateTime, default=lambda: datetime.utcnow())
    # uploaded_by = Column(String, ForeignKey("users.id"))
    uploaded_by = Column(Integer,default=1)
    

