from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from ..base import Base
from datetime import datetime



class PrincipalDB(Base):
    __tablename__ = "principals"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subjects_taught = Column(JSONB, nullable=True, default=[])  
    department = Column(String(50), nullable=True)
    assigned_institution = Column(String(255), nullable=True)  # Optional: school branch, etc.
    # routine = Column(JSONB, default=[]) 
    # #[{"subject_code": 2, "subject_name": "Physics",is_class_teacher: False,"room": "101","start_time": "9","end_time": "10", day:[monday,tuesday,wednesday], is_class_teacher: False }] 
    qualification = Column(String(100), nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)
    # Relationships

    user = relationship("UserDB", back_populates="principal")
