from pydantic import BaseModel, EmailStr, Field, computed_field
from typing import Optional, Dict, Any
from datetime import datetime
from ..models.super_admin_model import SuperAdminRole


# ---------------------------------------------------------------------------
# Auth / Login
# ---------------------------------------------------------------------------

class SuperAdminLoginRequest(BaseModel):
    identifier: str = Field(..., description="username or email")
    password: str = Field(..., min_length=1)


class SuperAdminOTPVerify(BaseModel):
    """Second step — verify OTP after password check passes."""
    session_token: str = Field(..., description="Temporary token issued after password check")
    otp_code: str = Field(..., min_length=6, max_length=6)


class SuperAdminForgotPasswordRequest(BaseModel):
    email: EmailStr


class SuperAdminResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str = Field(..., min_length=6)


class SuperAdminToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    super_admin_id: int


# ---------------------------------------------------------------------------
# Profile / Response
# ---------------------------------------------------------------------------

class SuperAdminProfileResponse(BaseModel):
    id: int
    name: str
    email: EmailStr
    user_name: str
    contact_num: str
    num_country_code: str
    role: SuperAdminRole
    is_block: bool
    permissions: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    profile_image_raw: Optional[str] = Field(None, alias="profile_image", exclude=True)

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def profile_image(self) -> Optional[Dict[str, str]]:
        if not self.profile_image_raw:
            return None
        return {
            "thumb": f"/api/super-admin/profile-image?type=thumb",
            "main":  f"/api/super-admin/profile-image?type=main",
        }


class SuperAdminUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=50)
    contact_num: Optional[str] = Field(None, min_length=10, max_length=15)
    num_country_code: Optional[str] = Field(None, min_length=1, max_length=5)
    address: Optional[str] = Field(None, max_length=255)
    profile_image: Optional[str] = None


# ---------------------------------------------------------------------------
# Security info (read-only, for dashboard display)
# ---------------------------------------------------------------------------

class SuperAdminSecurityInfo(BaseModel):
    last_login: Optional[datetime]
    last_password_change: datetime
    failed_login_attempts: int
    is_2fa_enabled: bool

    model_config = {"from_attributes": True}

class CurrentSuperAdminResponse(BaseModel):
    id: int
    user_name: str
    email: EmailStr
    role: str
    permissions: list[str]
    is_block: bool
    profile_image: Optional[str]
    name: Optional[str]


    model_config = {"from_attributes": True}