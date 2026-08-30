from pydantic import BaseModel, EmailStr,validator
from typing import Optional


class Token(BaseModel):
    """
    OAuth2 token response
    """
    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class TokenData(BaseModel):
    """
    Data stored in JWT token
    """
    sub: str  # email or username
    tenant_id: str
    role: str
    exp: Optional[int] = None


class LoginRequest(BaseModel):
    """
    Email/Password login
    """
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    """
    Request password reset
    """
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """
    Reset password with token
    """
    reset_token: str
    new_password: str


class OTPRequest(BaseModel):
    """
    Request OTP
    """
    email: EmailStr


class OTPVerify(BaseModel):
    """
    Verify OTP
    """
    email: EmailStr
    otp_code: str



# Activate with Password
class UserActivatePassword(BaseModel):
    activation_token: str
    password: str



# GOOGLE
class GoogleLoginRequest(BaseModel):
    id_token: str
    tenant_id: str
    
    @validator('id_token')
    def validate_token(cls, v):
        if not v or len(v) > 2048:
            raise ValueError('Invalid Google token')
        return v
    
    # @validator('institution_id')
    # def validate_institution(cls, v):
    #     if v <= 0:
    #         raise ValueError('Invalid institution ID')
    #     return v


class GoogleLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    
    class Config:
        from_attributes = True
