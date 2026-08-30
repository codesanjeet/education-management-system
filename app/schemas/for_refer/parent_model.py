# from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
# from sqlalchemy.dialects.postgresql import JSONB
# from sqlalchemy.orm import relationship
# from datetime import datetime
# from ..base import Base

# class ParentsDB(Base):
#     __tablename__ = "parents"
    
#     id = Column(Integer, primary_key=True, index=True)
#     user_id = Column(Integer, ForeignKey("users.id",ondelete="CASCADE"), nullable=False, unique=True)
#     parents_id = Column(String, nullable=False, unique=True)
#     occupation = Column(String, nullable=True)
#     children = Column(JSONB, nullable=False, default=[])
#     name = Column(String(100), nullable=True)
#     relation = Column(String(20), nullable=True)  # Father, Mother, Uncle, etc.
#     email = Column(String(100), nullable=True)
#     address = Column(String, nullable=True)
    
#     city = Column(String(50), nullable=True)
#     state = Column(String(50), nullable=True)
#     pincode = Column(String(10), nullable=True)
#     country = Column(String(50), nullable=False, default="India")


#     contact_num = Column(String, nullable=False)#
#     contact_num_country_code = Column(String(5), nullable=False ,default="91")#

#     alternative_contact_num = Column(String, nullable=True)
#     alternative_contact_num_country_code = Column(String(5), nullable=True ,default="91")
    
#     created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
#     updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
#     # Relationship with the User table (central user details)
#     user = relationship("UserDB", back_populates="parents")


