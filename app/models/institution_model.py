from sqlalchemy import Column, String, Integer,Boolean, Enum as SAEnum,event,Date,DateTime,ForeignKey,Float,BigInteger,Text,func
from sqlalchemy.dialects.postgresql import JSONB
from enum import Enum  # Python's enum
from .base import Base
from sqlalchemy.orm import relationship
from datetime import datetime



class InstitutionType(Enum):
    SCHOOL = "school"
    COLLEGE = "college"
    COACHING = "coaching"
    OTHERS = "others"



class ActionType(str, Enum):
    USER_RESTORED = "user_restored"
    USER_DELETED = "user_deleted"
    USER_UPDATED = "user_updated"
    USER_CREATED = "user_created"
    USER_CREATED_BULK = "user_created_bulk"

    ADMIN_CREATED = "admin_created"
    ADMIN_UPDATED = "admin_updated"
    ADMIN_DELETED = "admin_deleted"

    STUDY_MATERIAL_CREATED = "study_material_created"
    STUDY_MATERIAL_DELETED = "study_material_deleted"

    SETTING_UPDATED = "setting_updated"
    INSTITUTION_DELETED = "institution_deleted"
    PERMISSION_UPDATED = "permission_updated"

    CLASS_CREATED = "class_created"
    CLASS_UPDATED = "class_updated"
    CLASS_DELETED = "class_deleted"

    SCHEDULE_CREATED = "schedule_created"
    SCHEDULE_UPDATED = "schedule_updated"
    SCHEDULE_DELETED = "schedule_deleted"
    DISCIPLINARY_RECORD_CREATED = "disciplinary_record_created"

class InstitutionDB(Base):
    __tablename__ = "institutions"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    tenant_id = Column(String(8), unique=True, nullable=True)
    logo = Column(String(255), nullable=True)
    institute_name = Column(String(255), nullable=False) 
    institution_type=Column(
        SAEnum(InstitutionType, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    address = Column(String(255), nullable=False)

    city = Column(String(50), nullable=True)
    state = Column(String(50), nullable=True)
    pincode = Column(String(10), nullable=True)
    country = Column(String(50), nullable=True, default="India")
    session_timeout = Column(Integer, nullable=True , default=7)
    phone = Column(String(15), nullable=False)
    phone_country_code = Column(String(5), nullable=False ,default="91")
    email = Column(String(255), unique=True, nullable=False)
    primary_website = Column(String(100), nullable=True)
    year_established = Column(Integer, nullable=True)
    is_verified = Column(Boolean, nullable=False , default=False)
    is_rejected = Column(Boolean, nullable=False , default=False)
    is_block = Column(Boolean, nullable=False, default=False )
    # Financial
    billing_day = Column(Integer, default=25)   # generate on 25th
    due_day = Column(Integer, default=5)        # due on 5th next month

    created_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)
    # IS DELETED
    deleted_date = Column(Date,nullable=True)
    class_ = relationship(
        "ClassDB",
        back_populates="institution",
        passive_deletes=True,
        uselist=True
        
    )
    users = relationship("UserDB", back_populates="institution", uselist = True , passive_deletes= True)
    class_list = relationship("ClassroomDB",back_populates="institution", uselist=True, passive_deletes=True)
    notifications = relationship("NotificationsDB", back_populates="institution" , uselist=True ,passive_deletes=True)

@event.listens_for(InstitutionDB, "before_insert")
@event.listens_for(InstitutionDB, "before_update")
def lowercase_student_fields(mapper, connection, target):
    if target.tenant_id:
        target.tenant_id = target.tenant_id.upper()
    if target.email:
        target.email = target.email.lower()

class InstitutionInfoDB(Base):
    __tablename__ = "institutions_info"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"))
    ai_chat_url = Column(String(255), nullable=True)
    institution_page_url = Column(String(255), nullable=True)

class InstitutionUsageDB(Base):
    __tablename__ = "institution_usage"

    id = Column(Integer, primary_key=True)

    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        unique=True,
        index=True
    )

    ai_credits_balance = Column(BigInteger, default=0)
    email_balance = Column(Integer, default=1000)
    ai_voice_agents_balance_min = Column(Integer, default=0)
    storage_used_mb = Column(Float, default=0)


# class room data
class ClassroomDB(Base):
    __tablename__ = "classrooms"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"))
    layout_config = Column(JSONB, nullable=False) #[{column:1,row:20,seat_in_each_col:3},{column:2,row:31,seat_in_each_col:4}]
    room_number = Column(String(20), nullable=False)
    floor = Column(Integer)
    capacity = Column(Integer, default=2) 
    
    # Relationships
    institution = relationship("InstitutionDB", back_populates="class_list")


class ExamSeatingDB(Base):
    __tablename__ = "exam_seating"
    
    id = Column(Integer, primary_key=True)
    # exam_id = Column(Integer, ForeignKey("exams.id"),default=110)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # The actual "Address" of the seat
    row_index = Column(Integer)
    column_index = Column(Integer)
    seat_in_col = Column(Integer)
    # seat number
    seat_number = Column(Integer)


class ActivityLogDB(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(8), index=True, nullable=False)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE") ,nullable=False)
    user_id = Column(Integer, ForeignKey("users.id" ,ondelete="SET NULL"), nullable=True)
    action_type = Column(SAEnum(ActionType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    message = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow(), index=True)









# marketing page 
class ContactSubmissionDB(Base):
    __tablename__ = "contact_submissions"

    id         = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100), nullable=False)
    institute  = Column(String(150), nullable=False)
    email      = Column(String(255), nullable=False, index=True)
    phone      = Column(String(30), nullable=True)
    message    = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),  # DB sets this — always reliable
        nullable=False,
    )



