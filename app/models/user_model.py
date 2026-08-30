from sqlalchemy import Column, String,Integer, Enum as SAEnum, DateTime, Boolean, ForeignKey,Date,event,Text
from sqlalchemy.orm import relationship
from datetime import date
from datetime import datetime
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base
from enum import Enum  


# Define user role enum for SQLAlchemy model
class UserRoleEnum(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    OTHER_STAFF = "other_staff"
    PRINCIPAL = "principal"

    
class TwoFAMethod(str ,Enum):
    NONE = "none"
    EMAIL = "email"
    PHONE = "phone"
    APP = "app"

 
user_role_enum_type = SAEnum(
    UserRoleEnum,
    name="userroleenum",
    values_callable=lambda x: [e.value for e in x],
)

class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_name = Column(String(50), unique=True, nullable=False ,index=True)
    tenant_id = Column(String(8), nullable=False , index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(255), index=True, nullable=False)
    role = Column(
    user_role_enum_type,
    nullable=False
)
    joined_date = Column(Date,default=date.today, nullable=False)
    is_block = Column(Boolean, default=False)

    contact_num = Column(String(15), nullable=False)
    contact_num_country_code = Column(String(5), nullable=False, default="91")

    alternative_contact_num = Column(String, nullable=True)
    alternative_contact_num_country_code = Column(String(5), nullable=True ,default="91")

    profile_image = Column(String(255), nullable=True)

    address = Column(String(255), nullable=True)
    
    city = Column(String(50), nullable=False)
    state = Column(String(50), nullable=False)
    pincode = Column(String(10), nullable=True)
    country = Column(String(50), nullable=False, default="India")

    gender = Column(String(10), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    blood_group = Column(String(5), nullable=True)

    # gamification.
    total_score = Column(Integer, nullable=True, default=0)
    score_breakdown = Column(JSONB, nullable=True, default=list)
    # examplte [{score_get:20, reason:weekly test, date:2 aug, by:ramesh sir}]
    is_active = Column(Boolean, default=False, nullable=False)
    is_profile_complete = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)

    # IS DELETED
    deleted_date = Column(Date,nullable=True)

    # Relationships with related tables
    security = relationship("UserSecurityDB", back_populates="user", uselist=False, passive_deletes=True, lazy="selectin")
    permissions = relationship(
        "UserPermissionDB",
        back_populates="user",
        passive_deletes=True,
            lazy="selectin"
    )
    log = relationship("UserLogDB", back_populates="user", uselist=True, passive_deletes=True)
    student = relationship("StudentDB", back_populates="user", passive_deletes=True, uselist=False)
    teacher = relationship("TeacherDB", back_populates="user", passive_deletes=True, uselist=False)
    principal = relationship("PrincipalDB", back_populates="user", passive_deletes=True, uselist=False)
    other_staff = relationship("OtherStaffDB", back_populates="user", passive_deletes=True, uselist=False)
    admin = relationship("AdminDB", back_populates="user", passive_deletes=True, uselist=False)
    staff_salary = relationship("StaffSalaryDB", back_populates="user", passive_deletes=True, uselist=False)
    staff_attendance = relationship("StaffAttendanceDB", back_populates="user", passive_deletes=True, uselist=True)
    sessions = relationship("UserSessionDB", back_populates="user", passive_deletes=True, uselist=True)

    
    institution = relationship("InstitutionDB", back_populates="users", uselist=False , lazy="selectin")


    # security = relationship("UserSecurityDB", back_populates="user", uselist=False, passive_deletes=True, lazy="joined")
    # log = relationship("UserLogDB", back_populates="user", uselist=True, passive_deletes=True, lazy="joined")

    
    # student = relationship("StudentDB", back_populates="user", passive_deletes=True, uselist=False , lazy="joined")
    # teacher = relationship("TeacherDB", back_populates="user", passive_deletes=True, uselist=False , lazy="joined")
    # principal = relationship("PrincipalDB", back_populates="user", passive_deletes=True, uselist=False, lazy="joined")
    # other_staff = relationship("OtherStaffDB", back_populates="user", passive_deletes=True, uselist=False , lazy="joined")
    # admin = relationship("AdminDB", back_populates="user", passive_deletes=True, uselist=False , lazy="joined")
    # staff_salary = relationship("StaffSalaryDB", back_populates="user", passive_deletes=True, uselist=False)
    # staff_attendance = relationship("StaffAttendanceDB", back_populates="user", passive_deletes=True, uselist=True)

@event.listens_for(UserDB, "before_insert")
@event.listens_for(UserDB, "before_update")
def lowercase_username_email(mapper, connection, target):
    if target.user_name:
        target.user_name = target.user_name.lower()
    if target.email:
        target.email = target.email.lower()



class UserSecurityDB(Base):
    __tablename__ = "user_security"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    password_hash = Column(String(100), nullable=True)
    otp_secret = Column(String(255), nullable=True)  # for app (TOTP secret)
    two_fa_method = Column(
    SAEnum(TwoFAMethod, values_callable=lambda x: [e.value for e in x]),
    default=None
)
    
    # GOOGLE OAUTH
    google_id = Column(String(255), nullable=True, index=True)  # Google's unique ID
    google_linked_at = Column(DateTime, nullable=True)  # When Google was linked

    last_password_change = Column(DateTime, default=lambda: datetime.utcnow())
    failed_login_attempts = Column(Integer, default=0)
    last_login = Column(DateTime, nullable=True)
    password_reset_token = Column(String(255), nullable=True)
    password_reset_expires = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)

    # temporary
    activation_token = Column(String(255), nullable=True, index=True)
    activation_token_expires = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    
    user = relationship("UserDB", back_populates="security")

class UserLogDB(Base):
    __tablename__ = "user_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    login_time = Column(DateTime, default=lambda: datetime.utcnow())
    user_agent = Column(String(500), nullable=True)
    ip_address = Column(String(45), nullable=True)   # IPv4/IPv6
    success = Column(Boolean, default=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.utcnow(),
        nullable=False
    )
    user = relationship("UserDB" , back_populates="log")


    # class UserLogDB(Base):
    # user_id = Column(ForeignKey("users.id"))
    # action = Column(String)  # "ACTIVATED", "BLOCKED", "UNBLOCKED"
    # performed_by = Column(Integer)
    # created_at = Column(DateTime)


class UserSessionDB(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    jti = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    expires_at = Column(
        DateTime,
        nullable=False,
        index=True
    )

    revoked = Column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at = Column(
        DateTime,
        default=lambda: datetime.utcnow(),
        nullable=False
    )

    last_used_at = Column(
        DateTime,
        nullable=True
        
    )

    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    user = relationship("UserDB", back_populates="sessions")


# remark for ai analalysis

class RemarkType(str, Enum):
    ACHIEVEMENT = "achievement"
    ACADEMIC = "academic"
    BEHAVIOUR = "behaviour"
    WARNING = "warning"


class RemarkLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"



class RemarkDB(Base):
    __tablename__ = "remarks"

    id = Column(Integer, primary_key=True)

    given_by_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"), 
        nullable=True
    )
    given_by_role = Column(
    user_role_enum_type,
    nullable=False
    )

    target_id = Column(Integer, nullable=True)
    target_type = Column(String, nullable=True)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="SET NULL"), 
        nullable=True
    )

    type = Column(SAEnum(RemarkType, values_callable=lambda x: [e.value for e in x]), nullable=True)
    level = Column(SAEnum(RemarkLevel, values_callable=lambda x: [e.value for e in x]), nullable=True)

    remark = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    

