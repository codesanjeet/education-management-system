
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any,Union
from enum import Enum
from .user_schema import UsersBasicResponse,UsersResponse,UserCreate


class StaffStatus(str, Enum):
    ACTIVE = "active"        # Staff is currently working
    INACTIVE = "inactive"    # Not working currently, but still on record
    FIRED = "fired"          # Employment terminated
    RESIGNED = "resigned"    # Staff resigned voluntarily
    RETIRED = "retired"      # Officially retired
    ON_LEAVE = "on_leave"    # Temporarily away but still employed
    SUSPENDED = "suspended"  # Temporarily removed due to disciplinary or other issues


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



class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
pass

class TeacherCre(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50)
    subjects_taught: List = Field(...)


class PrincipalCre(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50)
    subjects_taught: Optional[List] = Field(None)     
    assigned_institution: Optional[str] = Field(None)


class OtherStaffCre(BaseModel):
    assigned_work: str = Field(...)


class AdminCre(BaseModel):
    pass

class TeacherCreate(BaseModel):
    teacher_data:TeacherCre
    user_data:UserCreate
    class Config:
        from_attributes = True

class PrincipalCreate(BaseModel):
    principal_data:PrincipalCre
    user_data:UserCreate
    class Config:
        from_attributes = True


class AdminCreate(BaseModel):
    admin_data:AdminCre
    user_data:UserCreate
    class Config:
        from_attributes = True


class OtherStaffCreate(BaseModel):
    other_staff_data:OtherStaffCre
    user_data:UserCreate


    
class TeacherBasicResponse(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50)
    subjects_taught: List = Field(...)
    class Config:
        from_attributes = True


class PrincipalBasicResponse(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50)
    subjects_taught: Optional[List] = Field(None)     
    class Config:
        from_attributes = True

class OtherStaffBasicResponse(BaseModel):
    assigned_work: str = Field(...)
    class Config:
        from_attributes = True

class AdminBasicResponse(BaseModel):
    pass
    class Config:
        from_attributes = True    
# Union of all roles
StaffRoleBasicResponse = Optional[Union[TeacherBasicResponse, PrincipalBasicResponse, AdminBasicResponse, OtherStaffBasicResponse]]


class StaffBasicResponse(BaseModel):
    user_data: UsersBasicResponse
    role_data: StaffRoleBasicResponse = None

    class Config:
        from_attributes = True






# full staff response

class TeacherResponse(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50)
    subjects_taught: List = Field(...)
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)
    class Config:
        from_attributes = True


class PrincipalResponse(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50) 
    subjects_taught: Optional[List] = Field(None) 
    assigned_institution: Optional[str] = Field(None ,max_length=255)
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)
    class Config:
        from_attributes = True    


class OtherStaffResponse(BaseModel):
    assigned_work: str = Field(...)
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)
    class Config:
        from_attributes = True

class AdminResponse(BaseModel):
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)
    class Config:
        from_attributes = True

StaffRoleResponse =Optional[Union[TeacherResponse,PrincipalResponse,AdminResponse,OtherStaffResponse]]

class StaffResponse(BaseModel):
    user_data: UsersResponse
    role_data: StaffRoleResponse = None
    class Config:
        from_attributes = True
# TEACHER AVAL
class TeacherAvailabilityRequest(BaseModel):
    start_time: int = Field(..., description="Start time in minutes (e.g., 540 for 9:00 AM)")
    end_time: int = Field(..., description="End time in minutes (e.g., 600 for 10:00 AM)")
    days: List[str] = Field(..., min_items=1, description="List of days (e.g., ['monday', 'tuesday'])")
    subject: Optional[str] = Field(None, description="Optional subject filter")


# UPDATE STAFF
class TeacherUpdate(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50)
    subjects_taught: Optional[List] = Field(None)
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)



class PrincipalUpdate(BaseModel):
    department: Optional[str] = Field(None, min_length=2, max_length=50) 
    subjects_taught: Optional[List] = Field(None) 
    assigned_institution: Optional[str] = Field(None ,max_length=255)
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)


class OtherStaffUpdate(BaseModel):
    assigned_work: Optional[str] = Field(...)
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)

class AdminUpdate(BaseModel):
    qualification: Optional[str] = Field(None, max_length=100)
    years_of_experience: Optional[int] = Field(None, ge=0)

# Response model for teacher routine/schedule
class TeacherRoutineResponse(BaseModel):
    teacher_id: int
    teacher_name: str
    department: Optional[str] = None
    routine: List[Dict[str, Any]] = Field(default_factory=list)
    
    class Config:
        from_attributes = True



