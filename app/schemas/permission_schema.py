from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import datetime
from enum import Enum


# ============================================================================
# Permission Enum - Matches Database DEFAULT_PERMISSIONS
# ============================================================================

class PermissionEnum(str, Enum):
    # SYSTEM
    SYSTEM_SETTINGS = "system:settings"
    USER_ROLE_MANAGE = "user:role_manage"
    PERMISSION_MANAGE = "permission:manage"
    BULK_ENTRY = "bulk:entry"

    # STUDENT
    STUDENT_CREATE = "student:create"
    STUDENT_UPDATE = "student:update"
    STUDENT_DELETE = "student:delete"
    STUDENT_VIEW = "student:view"
    STUDENT_VIEW_ALL = "student:view_all"
    STUDENT_VIEW_CLASS = "student:view_class"
    STUDENT_STATUS_CHANGE = "student:status_change"

    # STAFF
    STAFF_CREATE = "staff:create"
    STAFF_UPDATE = "staff:update"
    STAFF_DELETE = "staff:delete"
    STAFF_VIEW = "staff:view"
    STAFF_VIEW_ALL = "staff:view_all"

    # CLASS
    CLASS_MANAGEMENT = "class:management"

    # ATTENDANCE
    ATTENDANCE_STUDENT_MANAGEMENT = "attendance:student_attendance_management"
    ATTENDANCE_STAFF_MANAGEMENT = "attendance:staff_attendance_management"

    # EXAM
    EXAM_FULL_MANAGEMENT = "exam:full_management"
    GRADE_ASSIGN = "grade:assign"
    RESULT_PUBLISH = "result:publish"
    RESULT_VIEW = "result:view"

    # FINANCE
    FEE_VIEW = "fee:view"
    FEE_STRUCTURE_MANAGE = "fee:structure_manage"
    FEE_COLLECTION = "fee:collection"
    FEE_REPORT = "fee:report"
    FEE_DISCOUNT = "fee:discount"
    FEE_REFUND = "fee:refund"

    # COMMUNICATION
    NOTIFICATION_STUDENT_LEVEL = "notification:student_level"
    NOTIFICATION_ALL_STAFF_LEVEL = "notification:all_staff_level"
    NOTIFICATION_ADMIN_LEVEL = "notification:admin_level"

    # SPECIAL
    CONTENT_FULL_MANAGEMENT = "content:full_management"
    CONTENT_BASIC_MANAGEMENT = "content:basic_management"
    VOICE_AGENT_MANAGE = "voice_agent:ai_voice_agent_manage"
    REPORT_MASTER = "report:master"
    REPORT_BASIC = "report:basic"
    RECYCLE_BIN_USER = "recycle_bin:user"
    DISCIPLINE_STUDENT = "discipline:management"
    RECENT_ACTIVITY_LOGS = "recent_activity_logs:view"
    ADMISSION_MANAGEMENT = "admission:management"
    FEE_MANAGEMENT = "fee:management"


# ============================================================================
# Request Schemas
# ============================================================================

class AssignPermissionsRequest(BaseModel):
    """Request schema for assigning permissions to a user"""
    user_id: int = Field(..., gt=0, description="ID of the user to assign permissions to")
    permissions: List[PermissionEnum] = Field(
        ..., 
        min_length=1, 
        description="List of permissions to assign"
    )
    
    @field_validator('permissions')
    @classmethod
    def validate_unique_permissions(cls, v):
        """Ensure no duplicate permissions"""
        if len(v) != len(set(v)):
            raise ValueError("Duplicate permissions are not allowed")
        return v


class UpdatePermissionsRequest(BaseModel):
    """Request schema for updating user permissions"""
    permissions: List[PermissionEnum] = Field(
        ..., 
        min_length=1,
        description="Complete list of permissions (replaces existing)"
    )
    
    @field_validator('permissions')
    @classmethod
    def validate_unique_permissions(cls, v):
        if len(v) != len(set(v)):
            raise ValueError("Duplicate permissions are not allowed")
        return v


# ============================================================================
# Response Schemas
# ============================================================================

class PermissionDetail(BaseModel):
    """Individual permission detail"""
    id: int
    name: str
    description: str
    granted_at: datetime
    granted_by: Optional[int] = None
    
    class Config:
        from_attributes = True


class UserPermissionsResponse(BaseModel):
    """Response schema for user's permissions"""
    user_id: int
    permissions: List[PermissionDetail]
    total_permissions: int
    
    class Config:
        from_attributes = True


class AssignPermissionsResponse(BaseModel):
    """Response after assigning permissions"""
    success: bool
    message: str
    user_id: int
    assigned_permissions: List[str]
    total_assigned: int


class UpdatePermissionsResponse(BaseModel):
    """Response after updating permissions"""
    success: bool
    message: str
    user_id: int
    current_permissions: List[str]
    total_permissions: int


class AvailablePermissionsResponse(BaseModel):
    """Response for listing all available permissions"""
    permissions: List[dict]
    total: int
    categories: List[str]