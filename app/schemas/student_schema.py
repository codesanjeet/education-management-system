import re
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator,computed_field
from typing import Optional,List,Dict,Any
from enum import Enum
from datetime import date,datetime


class UserRoleEnum(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    OTHER_STAFF = "other_staff"
    PRINCIPAL = "principal"


class TwoFAMethod(str, Enum):
    NONE = "none"
    EMAIL = "email"
    PHONE = "phone"
    APP = "app"


class GenderEnum(str, Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class BloodGroupEnum(str, Enum):
    A_POSITIVE = "A+"
    A_NEGATIVE = "A-"
    B_POSITIVE = "B+"
    B_NEGATIVE = "B-"
    AB_POSITIVE = "AB+"
    AB_NEGATIVE = "AB-"
    O_POSITIVE = "O+"
    O_NEGATIVE = "O-"


class StudentStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    DROPPED = "dropped"
    SUSPENDED = "suspended"
    REMOVED = "removed"


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"





class StudentCreate(BaseModel):

    # Student Academic Fields
    roll_number: str = Field(..., min_length=1, max_length=20)
    guardian_contact_num: str = Field(..., min_length=10, max_length=15)

    # User Fields
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    role: UserRoleEnum = Field(..., description="User role")

    # User Contact Info
    contact_num: str = Field(..., min_length=10, max_length=15)
    contact_num_country_code: str = Field("91", min_length=1, max_length=5)

    # User Personal Info
    address: Optional[str] = Field(None, max_length=500)
    city: str = Field(..., min_length=2, max_length=50)
    state: str = Field(..., min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=4, max_length=10)
    country: str = Field("India", min_length=2, max_length=50)

    @field_validator("contact_num", "guardian_contact_num")
    @classmethod
    def validate_contact_number(cls, v: str, info) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) != 10:
            field = info.field_name.replace("_", " ").title()
            raise ValueError(f"{field} must be exactly 10 digits")
        return digits

    @field_validator("contact_num_country_code")
    @classmethod
    def validate_country_code(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if not digits:
            raise ValueError("Country code must contain digits only")
        return digits

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str, info) -> str:
        if not re.match(r"^[a-zA-Z\s\-']+$", v):
            field = info.field_name.replace("_", " ").title()
            raise ValueError(f"{field} must contain letters only")
        return v.strip()

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^\d{4,10}$", v):
            raise ValueError("Pincode must contain digits only (4-10 digits)")
        return v

    @field_validator("roll_number")
    @classmethod
    def validate_roll_number(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9\-_]+$", v):
            raise ValueError("Roll number must contain letters and numbers only")
        return v.strip()

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.lower().strip()




class StudentBasicRoleResponse(BaseModel):
    roll_number: str
    class_code: str
    student_status: StudentStatus
    
    class Config:
        from_attributes = True







class StudentResponse(BaseModel):
    """Student-specific data only"""
    # role ////////
    # Student identification
    roll_number: str = Field(..., min_length=1, max_length=20)
    class_code: str = Field(..., min_length=1, max_length=20)
    
    # Guardian information
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_relation: Optional[str] = None
    guardian_email: Optional[str] = None
    guardian_address: Optional[str] = None
    guardian_contact_num: str = Field(..., min_length=10, max_length=15)
    guardian_contact_num_country_code: str = Field(default="91")
    guardian_alternative_contact_num: Optional[str] = None
    guardian_alternative_contact_num_country_code: Optional[str] = Field(default="91")
    
    # Additional information
    emergency_contact: Optional[str] = None
    medical_conditions: Optional[str] = None
    special_needs: Optional[str] = None
    student_status: str = Field(default="active")
    issue_admit_card: bool = Field(default=False)



    # User related data ///////////
    user_id : int
    user_name: str = Field(..., min_length=2, max_length=50)
    first_name: str = Field(..., min_length=2, max_length=50)
    last_name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    role: UserRoleEnum = Field(..., description="User role")
    joined_date: date
    permissions: List[str] = Field(default_factory=list)
    is_block: bool = Field(default=False)

    # Contact Information
    contact_num: str = Field(..., min_length=10, max_length=15)
    contact_num_country_code: str = Field("91", min_length=1, max_length=5)
    alternative_contact_num: Optional[str] = Field(None, max_length=15)
    alternative_contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)

    # Profile & Address
    address: Optional[str] = Field(None, max_length=255)
    city: str = Field(..., min_length=2, max_length=50)
    state: str = Field(..., min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=4, max_length=10)
    country: str = Field("India", min_length=2, max_length=50)

    # Personal Information
    gender: Optional[str] = Field(None, max_length=10)
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = Field(None, max_length=5)

    # Gamification
    total_score: Optional[int] = Field(0, ge=0)
    score_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    # Example: [{"score_get": 20, "reason": "weekly test", "date": "2 aug", "by": "ramesh sir"}]
    deleted_date: Optional[date] = Field(None)
    # Timestamps
    created_at: datetime
    updated_at: datetime



    profile_image_raw: str | None = Field(
        alias="profile_image",
        exclude=True
    )
    model_config = {"from_attributes": True}
    @computed_field
    @property
    def profile_image(self) -> dict | None:
        if not self.profile_image_raw:
            return None

        return {
            "thumb": f"/api/institutions/users/{self.user_id}/profile-image?type=thumb",
            "main": f"/api/institutions/users/{self.user_id}/profile-image?type=main"
        }





class StudentUpdate(BaseModel):
    # Student identification
    roll_number: Optional[str] = Field(None, min_length=1, max_length=20)
 
    # Guardian information
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_relation: Optional[str] = None
    guardian_email: Optional[str] = None
    guardian_address: Optional[str] = None
    guardian_contact_num: Optional[str] = Field(None, min_length=5, max_length=15)
    guardian_contact_num_country_code: str = Field(default="91")
    guardian_alternative_contact_num: Optional[str] = None
    guardian_alternative_contact_num_country_code: Optional[str] = Field(default="91")
    
    # Additional information
    emergency_contact: Optional[str] = None
    medical_conditions: Optional[str] = None
    special_needs: Optional[str] = None

    # user data
    user_name: Optional[str] = Field(None, min_length=2, max_length=50)
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = None


    # Contact Information
    contact_num: Optional[str] = Field(None, min_length=10, max_length=15)
    contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)
    alternative_contact_num: Optional[str] = Field(None, max_length=15)
    alternative_contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)

    # Profile & Address
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, min_length=2, max_length=50)
    state: Optional[str] = Field(None, min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=4, max_length=10)
    country: Optional[str] = Field("India", min_length=2, max_length=50)

    # Personal Information
    gender: Optional[str] = Field(None, max_length=10)
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = Field(None, max_length=5)


# for self update

class StudentSelfUpdate(BaseModel):
    # Student identity
    user_name: Optional[str] = Field(None, min_length=2, max_length=50)
    first_name: Optional[str] = Field(None, min_length=2, max_length=50)
    last_name: Optional[str] = Field(None, min_length=2, max_length=50)
    email: Optional[EmailStr] = None

    # Contact Information
    contact_num: Optional[str] = Field(None, min_length=10, max_length=15)
    contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)
    alternative_contact_num: Optional[str] = Field(None, max_length=15)
    alternative_contact_num_country_code: Optional[str] = Field("91", min_length=1, max_length=5)

    # Profile & Address
    address: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, min_length=2, max_length=50)
    state: Optional[str] = Field(None, min_length=2, max_length=50)
    pincode: Optional[str] = Field(None, min_length=4, max_length=10)
    country: Optional[str] = Field("India", min_length=2, max_length=50)

    # Personal Information
    gender: Optional[str] = Field(None, max_length=10)
    date_of_birth: Optional[date] = None
    blood_group: Optional[str] = Field(None, max_length=5)

    # Guardian information (non-contact fields only)
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_relation: Optional[str] = None
    guardian_email: Optional[str] = None
    guardian_address: Optional[str] = None

    # Additional information
    emergency_contact: Optional[str] = None
    medical_conditions: Optional[str] = None
    special_needs: Optional[str] = None
    


class StudentBasicResponse(BaseModel):
    # User table fields
    id: int
    user_name: str
    first_name: str
    last_name: str
    email: EmailStr
    contact_num: str
    contact_num_country_code: str
    
    is_block: bool
    deleted_date: Optional[date]

    # Student table fields
    roll_number: str
    class_code: str
    student_status: str


    profile_image_raw: str | None = Field(
        alias="profile_image",
        exclude=True
    )
    model_config = {"from_attributes": True}
    @computed_field
    @property
    def profile_image(self) -> dict | None:
        if not self.profile_image_raw:
            return None

        return {
            "thumb": f"/api/institutions/users/{self.id}/profile-image?type=thumb",
            "main": f"/api/institutions/users/{self.id}/profile-image?type=main"
        }
    
class StudentDashboardResponse(BaseModel):
    basic_data: Any
    today_schedule: Any
    attendance_summary: Any
