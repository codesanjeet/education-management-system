from sqlalchemy import Column, Integer, String, ForeignKey,ARRAY, DateTime
from sqlalchemy.orm import relationship
from ..base import Base
from datetime import datetime


class TeacherDB(Base):
    __tablename__ = "teachers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id",ondelete="CASCADE"), nullable=False, unique=True)
    department = Column(String(50), nullable=True)
    subjects_taught = Column(ARRAY(String), nullable=False, default=[])
   #  routine = Column(JSONB, nullable=True, default=[]) 
   #  #[{"subject_code": 2, "subject_name": "Physics",is_class_teacher: False,"room": "101","start_time": "9","end_time": "10", day:[monday,tuesday,wednesday], class_code:clas252, is_class_teacher: False }] 
    qualification = Column(String(100), nullable=True)
    years_of_experience = Column(Integer, nullable=True) 
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)
 # Relationship definitions

    user = relationship("UserDB", back_populates="teacher")

  
