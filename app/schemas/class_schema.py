from pydantic import BaseModel, Field
from typing import Optional,List,Dict
from datetime import date
import datetime
from enum import Enum

# Enum for ClassStatus
class ClassStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"



class ClassStatistics(BaseModel):
    average_attendance: Optional[float] = Field(None, description="Average attendance percentage")
    discipline_percentage: Optional[int] = Field(None, description="Number of discipline issues")
    fee_collection_percentage: Optional[float] = Field(None, description="Fee collection percentage")

class ClassActivity(BaseModel):
    activity: str = Field(..., description="Activity name")
    date: str = Field(..., description="Activity date")
    participation: int = Field(..., description="Number of + participants")

class ClassRepresentative(BaseModel):
    student_user_id: int = Field(..., description="Student user id")
    student_first_name: Optional[str] = Field(...,max_length=50)
    student_last_name: Optional[str] = Field(...,max_length=50)
    role: str = Field(..., description="Student Role")

class ClassCreate(BaseModel):
    
    # User Fields
    section: str = Field(..., min_length=1, max_length=5, description="Class section")
    batch: Optional[str] = Field(None, min_length=1, max_length=10, description="Academic batch")
    department: Optional[str] = Field(None, min_length=2, max_length=100, description="Department name")
    program: Optional[str] = Field(None, min_length=2, max_length=50, description="Program name")
    class_or_year_or_name: str = Field(..., min_length=1, max_length=50, description="Class year or name")
    academic_year: str = Field(..., min_length=2, max_length=10, description="Academic year")
    max_student_limit: int = Field(..., description="Maximum student limit")
    class_start_at: int = Field(..., description="Class start time")
    class_end_at: int = Field(..., description="Class end time")
    lunch_start_at: Optional[int] = Field(None, description="lunch start at")
    lunch_end_at: Optional[int] = Field(None, description="lunch end at")
    morning_assembly_time: Optional[int] = Field(None, description="Morning assembly time")
    primary_classroom: str = Field(..., description="Primary classroom")


class ClassBasicResponse(BaseModel):
    
    # User Fields
    class_code: str = Field(..., min_length=1, max_length=20, description="Class code")
    section: str = Field(..., min_length=1, max_length=5, description="Class section")
    batch: Optional[str] = Field(None, min_length=1, max_length=10)
    department: Optional[str] = Field(None, min_length=2, max_length=100)
    program: Optional[str] = Field(None, min_length=2, max_length=50)
    class_or_year_or_name: str = Field(..., min_length=1, max_length=50, description="Class year or name")
    max_student_limit: int = Field(..., description="Maximum student limit")
    current_student_count: int = Field(..., description="Current student count")
    class_status: ClassStatus = Field(..., description="Class status")
    is_active: bool = Field(..., description="Is class active")
    deleted_date: Optional[date] = Field(None, description="Date on which the record was soft-deleted")

    class Config:
        from_attributes = True



class ClassDataResponse(BaseModel):
    
    class_code: str = Field(..., min_length=1, max_length=20, description="Class code")
    section: str = Field(..., min_length=1, max_length=5, description="Class section")
    batch: Optional[str] = Field(None, min_length=1, max_length=10, description="Academic batch")
    department: Optional[str] = Field(None, min_length=2, max_length=100, description="Department name")
    program: Optional[str] = Field(None, min_length=2, max_length=50, description="Program name")
    class_or_year_or_name: str = Field(..., min_length=1, max_length=50, description="Class year or name")
    academic_year: str = Field(..., min_length=2, max_length=10, description="Academic year")
    class_score: Optional[int] = Field(None, description="Class score")
    max_student_limit: int = Field(..., description="Maximum student limit")
    current_student_count: int = Field(..., description="Current student count")
    class_start_at: int = Field(..., description="Class start time")
    class_end_at: int = Field(..., description="Class end time")
    lunch_start_at: int = Field(..., description="lunch start at")
    lunch_end_at: int = Field(..., description="lunch end at")

    morning_assembly_time: Optional[int] = Field(..., description="Morning assembly time")
    primary_classroom: str = Field(..., description="Primary classroom")
    class_statistics: ClassStatistics = Field(..., description="Class statistics")
    class_activities: List[ClassActivity] = Field(..., description="Class activities")
    class_representatives: Dict[str, ClassRepresentative] = Field(..., description="Class representatives")
    fee_structure: Dict[str, float] = Field(..., description="Fee structure")
    created_at: datetime.datetime = Field(..., description="Created at timestamp")
    updated_at: datetime.datetime = Field(..., description="Updated at timestamp")
    class_status: ClassStatus = Field(..., description="Class status")
    is_active: bool = Field(..., description="Is class active")
    deleted_date: Optional[date] = Field(None, description="Date on which the record was soft-deleted")
    # exam schedule

    
    class Config:
        from_attributes = True

class ClassScheduleCreate(BaseModel):
    subject_code: Optional[str] = Field(None, max_length=20)
    subject_name: str = Field(..., max_length=50)
    teacher_user_id: int = Field(...)
    class_room: Optional[str] = Field(None, max_length=20)
    start_time: int = Field(..., description="Start time in MM or minutes format")
    end_time: int = Field(..., description="End time in MM or minutes format")
    day: str = Field(default="Monday", description="day")
    is_class_teacher: bool = Field(default=False)


class ClassScheduleResponse(BaseModel):
    id: int = Field(...)
    subject_code: Optional[str] = Field(..., max_length=20)
    subject_name: str = Field(..., max_length=50)
    teacher_user_id: int = Field(...)
    teacher_first_name: str = Field(...,max_length=50)
    teacher_last_name: str = Field(...,max_length=50)
    class_room: Optional[str] = Field(None, max_length=20)
    start_time: int = Field(..., description="Start time in MM or minutes format")
    end_time: int = Field(..., description="End time in MM or minutes format")
    day: str = Field(default="Monday", description="day")
    is_class_teacher: bool = Field(default=False)
    class Config:
        from_attributes = True



class ClassScheduleUpdate(BaseModel):
    subject_code: Optional[str] = Field(None, max_length=20)
    subject_name: Optional[str] = Field(None, max_length=50)
    teacher_user_id: Optional[int] = Field(None)
    class_room: Optional[str] = Field(None, max_length=20)
    start_time: Optional[int] = Field(None, description="Start time in HHMM or minutes format")
    end_time: Optional[int] = Field(None, description="End time in HHMM or minutes format")
    day: Optional[str] = Field(None, description="day")
    is_class_teacher: Optional[bool] = Field(None)
    class Config:
        from_attributes = True
   

class ClassUpdate(BaseModel):
    section: Optional[str] = Field(None, min_length=1, max_length=5, description="Class section")
    batch: Optional[str] = Field(None, min_length=1, max_length=10, description="Academic batch")
    department: Optional[str] = Field(None, min_length=2, max_length=100, description="Department name")
    program: Optional[str] = Field(None, min_length=2, max_length=50, description="Program name")
    class_or_year_or_name: Optional[str] = Field(None, min_length=1, max_length=50, description="Class year or name")
    academic_year: Optional[str] = Field(None, min_length=2, max_length=10, description="Academic year")
    max_student_limit: Optional[int] = Field(None, description="Maximum student limit")
    class_start_at: Optional[int] = Field(None, description="Class start time")
    class_end_at: Optional[int] = Field(None, description="Class end time")
    lunch_start_at: Optional[int] = Field(None, description="Lunch start time")
    lunch_end_at: Optional[int] = Field(None, description="Lunch end time")
    morning_assembly_time: Optional[int] = Field(None, description="Morning assembly time")
    primary_classroom: Optional[str] = Field(None, description="Primary classroom")
    class_representatives: Optional[Dict[str, "ClassRepresentative"]] = Field(
        None, description="Class representatives"
    )
    class_status: Optional["ClassStatus"] = Field(None, description="Class status")
    class Config:
        from_attributes = True
   

class ClassResponse(BaseModel):
    class_data: ClassDataResponse
    class_schedule: List[ClassScheduleResponse] 

    class Config:
        from_attributes = True


class CreateClassWithSchedule(BaseModel):
    class_data: ClassCreate
    class_schedule_data: List[ClassScheduleCreate] 
   


    


    
