from sqlalchemy import Column, Integer, DateTime, ForeignKey,String
from sqlalchemy.orm import relationship
from datetime import datetime
from ..base import Base


class OtherStaffDB(Base):
    __tablename__ = "other_staffs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    qualification = Column(String(255), nullable=True)
    years_of_experience = Column(Integer, nullable=True)  
    assigned_work = Column(String(50), nullable=False, default=list) #mange finance ,student admission 
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)

    # Relationships
    user = relationship("UserDB", back_populates="other_staff")
