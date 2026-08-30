from pydantic import BaseModel, EmailStr, Field,field_validator
from fastapi import Form
from typing import Optional,List
from datetime import datetime
from enum import Enum


class InstitutionType(str, Enum):  
    SCHOOL = "school"
    COLLEGE = "college"
    COACHING = "coaching"
    OTHERS = "others"


# Base Schema
class InstitutionBase(BaseModel):
    institute_name: str = Field(..., min_length=3, max_length=100)
    address: str = Field(..., min_length=5, max_length=255)
    phone: str = Field(..., min_length=5, max_length=15)   
    city: str = Field(..., min_length=2, max_length=100)
    state: str = Field(..., min_length=2, max_length=100)   
    pincode: str = Field(..., min_length=4, max_length=10)   
    country: str = Field(..., min_length=2, max_length=100)   
    phone_country_code: str = Field(..., min_length=1, max_length=5)
    primary_website: Optional[str] = None
    email: EmailStr
    institution_type: InstitutionType
    year_established: Optional[int] = None



class InstitutionGeneralResponse(InstitutionBase):
    created_at: datetime
    logo: str = None

    class Config:
        from_attributes = True



class InstitutionCreate(InstitutionBase):

    @classmethod
    def as_form(
        cls,
        institute_name: str = Form(...),
        address: str = Form(...),
        phone: str = Form(...),
        city: str = Form(...),
        state: str = Form(...),
        pincode: str = Form(...),
        country: str = Form(...),
        phone_country_code: str = Form(...),
        primary_website: Optional[str] = Form(None),
        email: EmailStr = Form(...),
        institution_type: InstitutionType = Form(...),
        year_established: Optional[int] = Form(None),
    ):
        return cls(
            institute_name=institute_name,
            address=address,
            phone=phone,
            city=city,
            state=state,
            pincode=pincode,
            country=country,
            phone_country_code=phone_country_code,
            primary_website=primary_website,
            email=email,
            institution_type=institution_type,
            year_established=year_established,
        )   

# only for super admin
class InstitutionUpdateSuperAdmin(BaseModel):
    institute_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    phone_country_code: Optional[str] = None
    email: Optional[EmailStr] = None
    primary_website: Optional[str] = None
    institution_type: Optional[InstitutionType] = None
    year_established: Optional[int] = None

  
    is_verified: Optional[bool] = None
    is_rejected: Optional[bool] = None
    is_block: Optional[bool] = None



class InstitutionUpdate(BaseModel):
    institute_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    phone_country_code: Optional[str] = None
    email: Optional[EmailStr] = None
    primary_website: Optional[str] = None
    institution_type: Optional[InstitutionType] = None
    year_established: Optional[int] = None



# Response Schema
class InstitutionResponse(InstitutionBase):
    tenant_id: str = Field(..., min_length=8, max_length=8)
    logo: str
    primary_website: Optional[str] = None
    is_verified: bool
    is_rejected: bool
    is_block: bool
    updated_at: datetime

    class Config:
        from_attributes = True
    

# classroom data
class LayoutConfig(BaseModel):
    column: int
    row: int
    seat_in_each_col: int
class CreateClassRoom(BaseModel):
    layout_config: List[LayoutConfig]
    room_number: str
    floor: int
# get classroom data
class ClassRoomResponse(BaseModel):
    id: int
    layout_config: List[LayoutConfig]
    room_number: str
    floor: int
    capacity: int

    class Config:
        from_attributes = True

class UpdateClassRoom(BaseModel):
    id:int
    layout_config: Optional[List[LayoutConfig]]=None
    room_number: Optional[str] = None
    floor: Optional[int] = None


# Exam seat for a student
class ExamSitting(BaseModel):
    row_index:int
    column_index: int
    seat_in_col: int
    seat_number:Optional[int] = None

# Exam setting for all student
class ExamSittingResponse(BaseModel):
    message: str
    exam_id: int
    setting_data_list: ExamSitting


# For marketing 
# ── Contact form schemas ──────────────────────────────────────────────────────

class ContactSubmissionCreate(BaseModel):
    name:      str       = Field(..., min_length=1, max_length=100)
    institute: str       = Field(..., min_length=1, max_length=150)
    email:     EmailStr
    phone:     Optional[str] = Field(None, max_length=30)
    message:   str       = Field(..., min_length=5, max_length=2000)

    @field_validator("name", "institute", "message")
    @classmethod
    def no_scripts(cls, v: str) -> str:
        bad = ["<script", "javascript:", "onerror=", "<iframe"]
        low = v.lower()
        for p in bad:
            if p in low:
                raise ValueError(f"Invalid content: {p}")
        return v.strip()


class ContactSubmissionResponse(BaseModel):
    id:         int
    name:       str
    institute:  str
    email:      str
    phone:      Optional[str]
    message:    str
    created_at: datetime

    class Config:
        from_attributes = True










class AnnouncementType(str, Enum):
    ALERT = "alert"
    OFFICIAL = "official"
    EVENT = "event"
    ACADEMIC = "academic"


class Audience(str, Enum):
    ALL = "all"
    STUDENT = "students"
    ALL_STAFF = "all_staffs"
    TEACHER = "teachers"
    ADMIN = "admins"
    OTHER_STAFF = "other_staffs"
    PRINCIPAL = "principals"


class FileUploadResponse(BaseModel):
    filename: str
    file_path: str
    mime_type: str
    size: int


class CreateNotificationData(BaseModel):
    """Schema for creating a new notification"""
    type: AnnouncementType = Field(..., description="Type of notification")
    audience: Audience = Field(..., description="Target audience for the notification")
    class_id: Optional[int] = Field(None, description="Class ID if audience is specific class")
    title: str = Field(..., min_length=1, max_length=255, description="Notification title")
    message: str = Field(..., min_length=1, description="Notification message content")
    # send_email: Optional[bool] = Field(False, description="Whether to send email to recipients")
    attached_file: Optional[str] = Field(
        None, 
        max_length=500, 
        description="URL or path to attached file (must be validated)"
    )
    include_parents: Optional[bool] = Field(False)
    file_is_public: Optional[bool] = Field(True)

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        """Validate title doesn't contain suspicious content"""
        if not v or not v.strip():
            raise ValueError('Title cannot be empty or only whitespace')
        
        # Check for suspicious HTML/script tags
        suspicious_patterns = ['<script', 'javascript:', 'onerror=', '<iframe']
        v_lower = v.lower()
        for pattern in suspicious_patterns:
            if pattern in v_lower:
                raise ValueError(f'Title contains suspicious content: {pattern}')
        
        return v.strip()
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        """Validate message doesn't contain suspicious content"""
        if not v or not v.strip():
            raise ValueError('Message cannot be empty or only whitespace')
        
        # Check for suspicious patterns
        suspicious_patterns = ['<script', 'javascript:', 'onerror=', '<iframe']
        v_lower = v.lower()
        for pattern in suspicious_patterns:
            if pattern in v_lower:
                raise ValueError(f'Message contains suspicious content: {pattern}')
        
        return v.strip()
    
    @field_validator('attached_file')
    @classmethod
    def validate_attached_file(cls, v):
        """Validate attached file path/URL"""
        if v is None:
            return v
        
        # Basic validation - actual file validation happens during upload
        if not v.strip():
            return None
        
        # Check for path traversal attempts
        suspicious_path_patterns = ['../', '..\\', '%2e%2e', '%252e']
        v_lower = v.lower()
        for pattern in suspicious_path_patterns:
            if pattern in v_lower:
                raise ValueError('Invalid file path: path traversal detected')
        
        return v.strip()



class UpdateNotificationData(BaseModel):
    type: Optional[AnnouncementType] = Field(None, description="Type of notification")
    audience: Optional[Audience] = Field(None, description="Target audience for the notification")
    class_id: Optional[int] = Field(None, description="Class ID if audience is specific class")
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="Notification title")
    message: Optional[str] = Field(None, min_length=1, description="Notification message content")
    attached_file: Optional[str] = Field(None, max_length=500, description="URL or path to attached file")

    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        """Validate title doesn't contain suspicious content"""
        if v is None:
            return v
        
        if not v.strip():
            raise ValueError('Title cannot be empty or only whitespace')
        
        # Check for suspicious HTML/script tags
        suspicious_patterns = ['<script', 'javascript:', 'onerror=', '<iframe']
        v_lower = v.lower()
        for pattern in suspicious_patterns:
            if pattern in v_lower:
                raise ValueError(f'Title contains suspicious content: {pattern}')
        
        return v.strip()
    
    @field_validator('message')
    @classmethod
    def validate_message(cls, v):
        """Validate message doesn't contain suspicious content"""
        if v is None:
            return v
        
        if not v.strip():
            raise ValueError('Message cannot be empty or only whitespace')
        
        # Check for suspicious patterns
        suspicious_patterns = ['<script', 'javascript:', 'onerror=', '<iframe']
        v_lower = v.lower()
        for pattern in suspicious_patterns:
            if pattern in v_lower:
                raise ValueError(f'Message contains suspicious content: {pattern}')
        
        return v.strip()
    
    @field_validator('attached_file')
    @classmethod
    def validate_attached_file(cls, v):
        """Validate attached file path/URL"""
        if v is None:
            return v
        
        if not v.strip():
            return None
        
        # Check for path traversal attempts
        suspicious_path_patterns = ['../', '..\\', '%2e%2e', '%252e']
        v_lower = v.lower()
        for pattern in suspicious_path_patterns:
            if pattern in v_lower:
                raise ValueError('Invalid file path: path traversal detected')
        
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "type": "alert",
                "title": "Updated: Semester Exam Schedule",
                "message": "The exam schedule has been updated. Please review the changes."
            }
        }


class NotificationResponse(BaseModel):
    """Schema for notification response"""
    id: int
    tenant_id: str
    type: AnnouncementType
    audience: Audience
    class_id: Optional[int]
    title: str
    message: str
    attached_file: Optional[str]
    read_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "tenant_id": "TEN00001",
                "type": "academic",
                "audience": "students",
                "class_id": None,
                "title": "Semester Exam Schedule Released",
                "message": "The semester examination schedule has been released.",
                "attached_file": "/uploads/institutions/5/notifications/exam_schedule.pdf",
                "created_at": "2024-01-27T10:30:00"
            }
        }


class DeleteNotificationResponse(BaseModel):
    """Schema for delete notification response"""
    success: bool
    message: str
    deleted_notification_id: int

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Notification deleted successfully",
                "deleted_notification_id": 1
            }
        }


class NotificationListResponse(BaseModel):
    """Schema for paginated notification list"""
    notifications: list[NotificationResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

    class Config:
        json_schema_extra = {
            "example": {
                "notifications": [],
                "total": 50,
                "page": 1,
                "page_size": 10,
                "total_pages": 5
            }
        }

class NotificationReadResponse(BaseModel):
    notification_id: int
    user_id: int
    read_at: datetime

    class Config:
        from_attributes = True



"""
notification_schema.py
─────────────────────────────────────────────────────────────────────────────
Multi-channel notification schemas:
  - WhatsApp config (unchanged provider logic)
  - Email config (SMTP / SendGrid / Mailgun)
  - SMS config (stub — stored, not dispatched)
  - AutomationRule (channel-agnostic, per-channel templates)
  - MessageLog (one row per recipient per channel)
─────────────────────────────────────────────────────────────────────────────
"""

from pydantic import BaseModel, Field, model_validator, EmailStr
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


# ══════════════════════════════════════════════════════════════
# SHARED ENUMS
# ══════════════════════════════════════════════════════════════

class ChannelEnum(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL    = "email"
    SMS      = "sms"      # stored but not dispatched yet


class ConfigStatusEnum(str, Enum):
    CONNECTED = "connected"
    FAILED    = "failed"
    EXPIRED   = "expired"
    PENDING   = "pending"


class MessageStatusEnum(str, Enum):
    QUEUED    = "queued"
    SENT      = "sent"
    DELIVERED = "delivered"
    READ      = "read"
    FAILED    = "failed"


class MessageTypeEnum(str, Enum):
    TEXT     = "text"
    TEMPLATE = "template"
    HTML     = "html"


class RuleTypeEnum(str, Enum):
    FEE_REMINDER        = "fee_reminder"
    ATTENDANCE_REMINDER = "attendance_reminder"
    CUSTOM              = "custom"


# ══════════════════════════════════════════════════════════════
# WHATSAPP CONFIG SCHEMAS  (unchanged from original)
# ══════════════════════════════════════════════════════════════

class ProviderEnum(str, Enum):
    TWILIO   = "twilio"
    GUPSHUP  = "gupshup"
    META     = "meta"


class TwilioConfig(BaseModel):
    account_sid: str = Field(..., min_length=1)
    auth_token:  str = Field(..., min_length=1)


class GupshupConfig(BaseModel):
    api_key:  str           = Field(..., min_length=1)
    app_name: Optional[str] = None


class MetaConfig(BaseModel):
    access_token:        str           = Field(..., min_length=1)
    phone_number_id:     str           = Field(..., min_length=1)
    business_account_id: Optional[str] = None
    app_id:              Optional[str] = None
    app_secret:          Optional[str] = None


class WhatsAppConfigCreate(BaseModel):
    provider:     ProviderEnum
    phone_number: str               = Field(..., min_length=10, max_length=20)
    config:       Dict[str, Any]    = Field(..., description="Provider-specific credentials")
    webhook_url:  Optional[str]     = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_config_for_provider(self):
        p, c = self.provider, self.config
        if p == ProviderEnum.TWILIO:   TwilioConfig(**c)
        elif p == ProviderEnum.GUPSHUP: GupshupConfig(**c)
        elif p == ProviderEnum.META:    MetaConfig(**c)
        return self


class WhatsAppConfigUpdate(BaseModel):
    phone_number: Optional[str]          = Field(None, min_length=10, max_length=20)
    config:       Optional[Dict[str, Any]] = None
    webhook_url:  Optional[str]          = Field(None, max_length=500)
    is_active:    Optional[bool]         = None


class WhatsAppConfigResponse(BaseModel):
    id:           int
    tenant_id:    str
    institution_id: int
    provider:     ProviderEnum
    phone_number: str
    webhook_url:  Optional[str]
    is_active:    bool
    status:       ConfigStatusEnum
    last_error:   Optional[str]
    created_at:   datetime
    updated_at:   datetime
    # NOTE: `config` intentionally excluded (contains secrets)

    class Config:
        from_attributes = True


class WhatsAppConfigVerifyResponse(BaseModel):
    status:   ConfigStatusEnum
    message:  str
    provider: ProviderEnum


# ══════════════════════════════════════════════════════════════
# EMAIL CONFIG SCHEMAS
# ══════════════════════════════════════════════════════════════

class EmailProviderEnum(str, Enum):
    SMTP      = "smtp"
    SENDGRID  = "sendgrid"
    MAILGUN   = "mailgun"


class SmtpConfig(BaseModel):
    host:     str  = Field(..., min_length=1)
    port:     int  = Field(..., ge=1, le=65535)
    username: str  = Field(..., min_length=1)
    password: str  = Field(..., min_length=1)
    use_tls:  bool = True


class SendGridConfig(BaseModel):
    api_key: str = Field(..., min_length=1)


class MailgunConfig(BaseModel):
    api_key: str = Field(..., min_length=1)
    domain:  str = Field(..., min_length=1)


class EmailConfigCreate(BaseModel):
    provider:   EmailProviderEnum
    from_email: str               = Field(..., max_length=200)
    from_name:  Optional[str]     = Field(None, max_length=200)
    reply_to:   Optional[str]     = Field(None, max_length=200)
    config:     Dict[str, Any]    = Field(..., description="Provider-specific credentials")

    @model_validator(mode="after")
    def validate_config_for_provider(self):
        p, c = self.provider, self.config
        if p == EmailProviderEnum.SMTP:      SmtpConfig(**c)
        elif p == EmailProviderEnum.SENDGRID: SendGridConfig(**c)
        elif p == EmailProviderEnum.MAILGUN:  MailgunConfig(**c)
        return self


class EmailConfigUpdate(BaseModel):
    from_email: Optional[str]          = Field(None, max_length=200)
    from_name:  Optional[str]          = Field(None, max_length=200)
    reply_to:   Optional[str]          = Field(None, max_length=200)
    config:     Optional[Dict[str, Any]] = None
    is_active:  Optional[bool]         = None


class EmailConfigResponse(BaseModel):
    id:             int
    tenant_id:      str
    institution_id: int
    provider:       EmailProviderEnum
    from_email:     str
    from_name:      Optional[str]
    reply_to:       Optional[str]
    is_active:      bool
    status:         ConfigStatusEnum
    last_error:     Optional[str]
    created_at:     datetime
    updated_at:     datetime
    # NOTE: `config` intentionally excluded (contains secrets)

    class Config:
        from_attributes = True


class EmailConfigVerifyResponse(BaseModel):
    status:  ConfigStatusEnum
    message: str
    provider: EmailProviderEnum


# ══════════════════════════════════════════════════════════════
# SMS CONFIG SCHEMAS  — stub
# ══════════════════════════════════════════════════════════════

class SmsProviderEnum(str, Enum):
    TWILIO     = "twilio"
    TEXTLOCAL  = "textlocal"
    MSG91      = "msg91"


class SmsConfigResponse(BaseModel):
    """Read-only stub. No create/update endpoints exposed yet."""
    id:             int
    institution_id: int
    provider:       SmsProviderEnum
    is_active:      bool   # always False
    status:         ConfigStatusEnum
    created_at:     datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# PER-CHANNEL TEMPLATE SCHEMAS
# ══════════════════════════════════════════════════════════════

class WhatsAppTemplate(BaseModel):
    """Template content for WhatsApp channel."""
    body: str = Field(..., min_length=1, max_length=4096,
                      description="Supports {student_name} {parent_name} {amount} {due_date} {days} {date}")


class EmailTemplate(BaseModel):
    """Template content for Email channel."""
    subject:  str  = Field(..., min_length=1, max_length=500)
    body:     str  = Field(..., min_length=1, max_length=50000)
    is_html:  bool = False


class SmsTemplate(BaseModel):
    """Template content for SMS channel — stored but not dispatched yet."""
    body: str = Field(..., min_length=1, max_length=160)


class ChannelTemplates(BaseModel):
    """
    Per-channel message content.
    Only provide templates for channels included in AutomationRuleCreate.channels.
    """
    whatsapp: Optional[WhatsAppTemplate] = None
    email:    Optional[EmailTemplate]    = None
    sms:      Optional[SmsTemplate]      = None  # stored, not dispatched

    @model_validator(mode="after")
    def at_least_one(self):
        if not any([self.whatsapp, self.email, self.sms]):
            raise ValueError("At least one channel template must be provided.")
        return self


# ══════════════════════════════════════════════════════════════
# AUTOMATION RULE SCHEMAS  — channel-agnostic
# ══════════════════════════════════════════════════════════════

class AutomationRuleCreate(BaseModel):
    name:              str               = Field(..., min_length=1, max_length=200)
    type:              RuleTypeEnum
    channels:          List[ChannelEnum] = Field(..., min_length=1,
                                                  description="['whatsapp'], ['email'], or ['whatsapp','email']")
    audience:          str               = Field(..., min_length=1, max_length=200)
    channel_templates: ChannelTemplates
    schedule:          str               = Field(..., min_length=1, max_length=200,
                                                  description="Human-readable, e.g. '1st of every month, 9:00 AM'")
    cron_expression:   Optional[str]     = Field(None, max_length=100)
    enabled:           bool              = True

    @model_validator(mode="after")
    def templates_match_channels(self):
        t = self.channel_templates
        for ch in self.channels:
            if ch == ChannelEnum.WHATSAPP and not t.whatsapp:
                raise ValueError("whatsapp template required when whatsapp channel is selected")
            if ch == ChannelEnum.EMAIL and not t.email:
                raise ValueError("email template required when email channel is selected")
            if ch == ChannelEnum.SMS and not t.sms:
                raise ValueError("sms template required when sms channel is selected")
        return self


class AutomationRuleUpdate(BaseModel):
    name:              Optional[str]               = Field(None, min_length=1, max_length=200)
    channels:          Optional[List[ChannelEnum]] = None
    audience:          Optional[str]               = Field(None, min_length=1, max_length=200)
    channel_templates: Optional[ChannelTemplates]  = None
    schedule:          Optional[str]               = Field(None, min_length=1, max_length=200)
    cron_expression:   Optional[str]               = Field(None, max_length=100)
    enabled:           Optional[bool]              = None


class AutomationRuleResponse(BaseModel):
    id:                int
    institution_id:    int
    name:              str
    type:              RuleTypeEnum
    enabled:           bool
    channels:          List[str]
    audience:          str
    channel_templates: Dict[str, Any]
    schedule:          str
    cron_expression:   Optional[str]
    last_run:          Optional[datetime]
    next_run:          Optional[datetime]
    sent_count:        int
    created_at:        datetime
    updated_at:        datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# MESSAGE LOG SCHEMAS
# ══════════════════════════════════════════════════════════════

class MessageLogCreate(BaseModel):
    """Internal use — not exposed via API directly."""
    rule_id:             Optional[int]      = None
    channel:             ChannelEnum
    whatsapp_config_id:  Optional[int]      = None
    email_config_id:     Optional[int]      = None
    recipient_name:      str
    recipient_contact:   str               # phone or email
    subject:             Optional[str]     = None   # email only
    message_body:        str
    message_type:        MessageTypeEnum   = MessageTypeEnum.TEXT
    provider_message_id: Optional[str]    = None
    status:              MessageStatusEnum = MessageStatusEnum.QUEUED


class MessageLogResponse(BaseModel):
    id:                  int
    institution_id:      int
    rule_id:             Optional[int]
    channel:             str
    recipient_name:      str
    recipient_contact:   str
    subject:             Optional[str]
    message_body:        str
    message_type:        str
    status:              str
    provider_message_id: Optional[str]
    error_message:       Optional[str]
    sent_at:             Optional[datetime]
    delivered_at:        Optional[datetime]
    created_at:          datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
# WEBHOOK SCHEMAS
# ══════════════════════════════════════════════════════════════

class WebhookPayload(BaseModel):
    """Generic normalised webhook payload (all channels)."""
    channel:             ChannelEnum
    provider:            str   # "twilio" | "meta" | "gupshup" | "smtp" | "sendgrid" | "mailgun"
    provider_message_id: str
    status:              MessageStatusEnum
    error_message:       Optional[str]     = None
    timestamp:           Optional[datetime] = None
    raw:                 Optional[Dict[str, Any]] = None


# ══════════════════════════════════════════════════════════════
# PAGINATION
# ══════════════════════════════════════════════════════════════

class PaginationMeta(BaseModel):
    total:       int
    page:        int
    page_size:   int
    total_pages: int


class MessageLogListResponse(BaseModel):
    items:      List[MessageLogResponse]
    pagination: PaginationMeta