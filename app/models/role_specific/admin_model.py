from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from ..base import Base
from datetime import datetime
# from ..user_model import UserDB

class AdminDB(Base):
    __tablename__ = "admin"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id",ondelete="CASCADE"), nullable=False, unique=True)
    qualification = Column(String(100), nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)  
    
    # Relationship with the User table (central user details)
    user = relationship("UserDB", back_populates="admin")
