from pydantic import BaseModel, Field, validator,field_validator
from typing import List, Optional
from datetime import datetime, date,time
from enum import Enum
from typing_extensions import Annotated,Literal


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
class AttendanceType(str, Enum):
    SUMMARY = "summary"
    FULL = "full"
    DAY_WISE = "day_wise"




class AttendanceRecordCreate(BaseModel):
    roll_number: str = Field(
        ..., 
        min_length=1,
        max_length=50
    )
    status: AttendanceStatus = Field(
        ..., 
        description="Attendance status (present, absent, late)"
    )
    subject: Optional[str] = Field(
        None, 
        max_length=100, 
        description="Subject name (optional)"
    )
    
    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "roll_number": "2024001",
                "status": "present",
                "subject": "Mathematics",
            }
        }
    
    @validator('roll_number')
    def validate_roll_number(cls, v):
        """Validate and clean roll number"""
        if not v or not v.strip():
            raise ValueError("Roll number cannot be empty")
        return v.strip()
    
    @validator('subject')
    def validate_subject(cls, v):
        """Validate and clean subject"""
        if v:
            return v.strip()
        return v
    

class BulkAttendanceCreate(BaseModel):
    attendance_date: date = Field(
        default_factory=date.today, 
        description="Date of attendance"
    )
    records: List[AttendanceRecordCreate] = Field(
        ..., 
        min_items=1, 
        description="List of student attendance records"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "attendance_date": "2024-01-15",
                "records": [
                    {
                        "roll_number": "2024001", 
                        "status": "present",
                        "subject": "Mathematics"
                    },
                    {
                        "roll_number": "2024002", 
                        "status": "absent", 
                        "subject": "Mathematics",
                    },
                    {
                        "roll_number": "2024003", 
                        "status": "late",
                        "subject": "Mathematics", 
                    }
                ]
            }
        }
    
    @validator('attendance_date')
    def validate_attendance_date(cls, v):
        """Ensure attendance date is not in the future"""
        if v > date.today():
            raise ValueError("Attendance date cannot be in the future")
        return v
    
    @validator('records')
    def validate_unique_roll_numbers(cls, v):
        """Ensure no duplicate roll numbers in the batch"""
        roll_numbers = [record.roll_number for record in v]
        if len(roll_numbers) != len(set(roll_numbers)):
            raise ValueError("Duplicate roll numbers found in records")
        return v


class AttendanceStudentSuccessResponse(BaseModel):
    message: str = Field(..., description="Success message")
    students_processed: int = Field(..., ge=0, description="Number of students processed")
    present_count: int = Field(..., ge=0, description="Number of students present")
    absent_count: int = Field(..., ge=0, description="Number of students absent")
    late_count: int = Field(..., ge=0, description="Number of students late")
    class_code: str = Field(..., description="Class code")
    attendance_date: date = Field(..., description="Date of attendance")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Attendance successfully submitted",
                "students_processed": 30,
                "present_count": 25,
                "absent_count": 3,
                "late_count": 2,
                "class_code": "CS101",
                "attendance_date": "2024-01-15"
            }
        }


 
 

Month = Annotated[int, Field(ge=1, le=12)]
Year = Annotated[int, Field(ge=2000)]
# Each att element must follow this 
class StudentAttendanceMonthResponse(BaseModel):
    attendance_date: date
    status: AttendanceStatus
    subject: Optional[str]


    
    class Config:
        from_attributes = True
        use_enum_values = True


class StudentAttendanceSummaryResponse(BaseModel):
    subject: str
    year:Year
    month:Month
    total: int
    present: int
    updated_at : datetime


    @field_validator("year")
    @classmethod
    def validate_year(cls, v: int) -> int:
        current_year = datetime.utcnow().year
        if v < 2000:
            raise ValueError("Year must be >= 2000")
        if v > current_year:
            raise ValueError("Year cannot be in the future")
        return v
    
    class Config:
        from_attributes = True
        use_enum_values = True



class ClassAttendanceSummary(BaseModel):
    class_code: str
    total: int
    present: int
    year: Year
    month: Month
    updated_at: datetime

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: int) -> int:
        current_year = datetime.utcnow().year
        if v < 2000:
            raise ValueError("Year must be >= 2000")
        if v > current_year:
            raise ValueError("Year cannot be in the future")
        return v


    class Config:
        json_schema_extra = {
            "example": {
                "class_code": "CS101",
                "total": 30,
                "present": 25,
                "absent": 3,
                "date": "2024-01-15"
            }
        }
        from_attributes = True


class InstitutionAttendanceSummary(BaseModel):
    total: int
    present: int
    year: Year
    month: Month
    updated_at: datetime

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: int) -> int:
        current_year = datetime.utcnow().year
        if v < 2000:
            raise ValueError("Year must be >= 2000")
        if v > current_year:
            raise ValueError("Year cannot be in the future")
        return v


    class Config:
        json_schema_extra = {
            "example": {
                "total": 30,
                "present": 25,
                "absent": 3,
                "date": "2024-01-15"
            }
        }




WeekDay = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday"
]
class InstitutionAttendanceDaySummary(BaseModel):
    total: int
    present: int
    week_day:WeekDay
    created_on: date
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "total": 30,
                "present": 25,
                "absent": 3,
                "week_day": "Monday"
            }
        }
class ClassAttendanceDaySummary(BaseModel):
    class_code: str
    total: int
    present: int
    week_day:WeekDay
    created_on:date
    updated_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "class_code":"Cl123",
                "total": 30,
                "present": 25,
                "absent": 3,
                "week_day": "Monday"
            }
        }



class StudentForMarkAttendance(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    roll_number: str
    class_code: str
        
    class Config:
        from_attributes = True

class StudentForUpdateAttendance(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    roll_number: str
    class_code: str
    subject: str
    status: AttendanceStatus = Field(   ... )
        
    class Config:
        from_attributes = True
        use_enum_values = True

class IndividualAttendanceCreate(BaseModel):
    class_code: str
    status: AttendanceStatus
    subject: Optional[str] = Field(
        None, 
        max_length=100, 
        description="Subject name (optional)"
    )
    attendance_date: date = Field(
        default_factory=date.today, 
        description="Date of attendance"
    )




# Staff Attendance Schema
# for create
class StaffAttendanceCreate(BaseModel):
    status: AttendanceStatus = Field(
        ..., 
        description="Attendance status (present, absent, late)"
    )
    attendance_date: date = Field(
        default_factory=date.today, 
        description="Date of attendance"
    )
    sign_in_time: Optional[time] = None
    sign_out_time: Optional[time] = None
    late_duration: Optional[time] = None

    
    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "status": "present",
                "attendance_date": "2025-12-17",
                "sign_in_time": "09:10:00",
                "sign_in_time": "08:10:00",
                "late_duration":'120 min..'
            }
        }

# for update
class StaffAttendanceUpdate(BaseModel):

    status: AttendanceStatus = Field(
        ..., 
        description="Attendance status (present, absent, late)"
    )
    attendance_date: date = Field(
        default_factory=date.today, 
        description="Date of attendance"
    )
    late_duration: Optional[time] = None


    
    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "status": "present",
                "attendance_date": "2025-12-17",
                "late_duration":'120 min..'
            }
        }
# for get normal
class StaffAttendanceResponse(BaseModel):
    attendance_date: date = Field(
        ..., 
    )
    status: AttendanceStatus = Field(
        ..., 
        description="Attendance status (present, absent, late)"
    )
    sign_in_time: Optional[time]= None
    sign_out_time: Optional[time] = None
    late_duration: Optional[time] = None
    attendance_id: int

    class Config:
        use_enum_values = True
        from_attributes = True

# for get agg 
class StaffAttendanceAggResponse(BaseModel):
    present:int
    total:int
    late_count:int
    late_duration:Optional[int] = None
    updated_at:datetime

    class Config:
        use_enum_values = True

class StaffAttendanceDayAggResponse(BaseModel):
    present:int
    total:int
    user_id:int
    week_day:WeekDay
    created_on:date
    updated_at:datetime

    class Config:
        use_enum_values = True

class AttendanceScanRequest(BaseModel):
    session_token: str
    device_fingerprint: str
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    gps_accuracy: Optional[float] = None  # to detect cell tower spoofing


