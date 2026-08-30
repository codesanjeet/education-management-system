from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime,date
from enum import Enum


class RemarkType(str, Enum):
    ACHIEVEMENT = "achievement"
    ACADEMIC = "academic"
    BEHAVIOUR = "behaviour"
    WARNING = "warning"


class RemarkLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ==================== REQUEST SCHEMAS ====================

class RemarkCreate(BaseModel):
    target_id: Optional[int] = Field(None, description="Target entity ID (user, class, etc.)")
    target_type: Optional[str] = Field(None, max_length=50, description="Target type e.g. 'student', 'class'")
    type: Optional[RemarkType] = Field(None, description="Remark type")
    level: Optional[RemarkLevel] = Field(None, description="Remark level/severity")
    remark: str = Field(..., min_length=1, description="Remark content")

    class Config:
        from_attributes = True


class RemarkUpdate(BaseModel):
    target_id: Optional[int] = Field(None, description="Target entity ID")
    target_type: Optional[str] = Field(None, max_length=50, description="Target type")
    type: Optional[RemarkType] = Field(None, description="Remark type")
    level: Optional[RemarkLevel] = Field(None, description="Remark level/severity")
    remark: Optional[str] = Field(None, min_length=1, description="Remark content")

    class Config:
        from_attributes = True


# ==================== RESPONSE SCHEMAS ====================

class RemarkResponse(BaseModel):
    id: int = Field(..., description="Remark ID")
    given_by_id: Optional[int] = Field(None, description="ID of the user who gave the remark")
    given_by_role: str = Field(..., description="Role of the user who gave the remark")
    target_id: Optional[int] = Field(None, description="Target entity ID")
    target_type: Optional[str] = Field(None, description="Target type")
    type: Optional[RemarkType] = Field(None, description="Remark type")
    level: Optional[RemarkLevel] = Field(None, description="Remark level/severity")
    remark: str = Field(..., description="Remark content")
    created_at: datetime = Field(..., description="Creation timestamp")

    class Config:
        from_attributes = True




# ==================== REQUEST SCHEMAS Discipiline ====================

class DisciplinaryRecordCreate(BaseModel):
    student_user_id: int = Field(..., description="Student DB ID")
    incident_date: date = Field(..., description="Date of the incident")
    incident_level: str = Field(..., max_length=50, description="Severity level of the incident")
    description: str = Field(..., min_length=1, description="Detailed description of the incident")
    action_taken: Optional[str] = Field(None, max_length=100, description="Action taken in response")
    is_locked: bool = False

    class Config:
        from_attributes = True


class DisciplinaryRecordUpdate(BaseModel):
    incident_date: Optional[date] = Field(None, description="Date of the incident")
    incident_level: Optional[str] = Field(None, max_length=50, description="Severity level")
    description: Optional[str] = Field(None, min_length=1, description="Incident description")
    action_taken: Optional[str] = Field(None, max_length=100, description="Action taken")
    is_locked: Optional[bool] = None

    class Config:
        from_attributes = True


# ==================== RESPONSE SCHEMAS ====================

class DisciplinaryRecordResponse(BaseModel):
    id: int = Field(..., description="Record ID")
    student_id: int = Field(..., description="Student DB ID")
    incident_date: date = Field(..., description="Date of the incident")
    incident_level: str = Field(..., description="Severity level of the incident")
    description: str = Field(..., description="Incident description")
    action_taken: Optional[str] = Field(None, description="Action taken")
    reported_by: int = Field(..., description="Reporter identifier")
    is_locked: bool

    class Config:
        from_attributes = True