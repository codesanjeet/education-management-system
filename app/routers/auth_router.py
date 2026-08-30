from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Request, Body, Form, BackgroundTasks

from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import re
import secrets
import asyncio
from app.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    # verify_password
)
from app.core.database import get_db
from app.crud.user_fun import authenticate_user, activate_user_with_password, session_db_create_for_refresh_token, session_db_check_valid, session_db_update_last_used, session_db_revoke, forgot_password, reset_password, check_tenant_id_by_identifier
from app.schemas.auth_schema import (
    Token,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    OTPRequest,
    OTPVerify
)
import uuid
from ..deps import decode_token
from app.schemas.auth_schema import UserActivatePassword, GoogleLoginRequest, GoogleLoginResponse
from ..services.email import send_password_reset_email
from ..core.config import settings
from app.crud.user_fun import (
    check_rate_limit_by_ip,
    log_login_attempt,
    find_user_by_google_id,
    find_user_by_email_and_institution,
    link_google_account,
    session_db_create_for_refresh_token
)
from ..services.user import get_valid_user
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from ..crud.permission_crud import get_user_permissions


# from app.services.email import EmailService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def validate_password(password: str) -> bool:
    return (
        len(password) >= 6
        and re.search(r"[A-Z]", password)
        and re.search(r"[a-z]", password)
        and re.search(r"\d", password)
    )


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# check email for tenant id
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/check-email")
async def check_email(
    request: Request,
    identifier: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    """
    Check if email exists and return institutions
    """
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "unknown")

    # Rate limit — strict, 5 attempts per 10 min
    is_rate_limited = await check_rate_limit_by_ip(
        db=db,
        ip_address=ip_address,
        max_attempts=5,
        time_window_minutes=10
    )
    if is_rate_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later."
        )

    # log every attempt
    await log_login_attempt(
        db=db,
        user_id=None,
        ip_address=ip_address,
        user_agent=user_agent,
        success=False
    )

    users = await check_tenant_id_by_identifier(
        db=db,
        identifier=identifier
    )

    if not users:
        raise HTTPException(
            status_code=404,
            detail="No account found with this email"
        )

    return users


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# FIX: rate limit moved BEFORE authenticate_user so DB auth is never hit first
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/login", response_model=Token)
async def login(
    response: Response,
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Form(...),
):
    """
    Login with email and password
    Returns JWT access token
    """

    # Get request metadata
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "unknown")

    # LAYER 1: RATE LIMITING — must be first, before any DB auth work
    is_rate_limited = await check_rate_limit_by_ip(
        db=db,
        ip_address=ip_address,
        max_attempts=5,
        time_window_minutes=10
    )
    if is_rate_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again in 10 minutes."
        )

    user = await authenticate_user(
        db,
        identifier=form_data.username,
        password=form_data.password,
        tenant_id=tenant_id
    )

    if not user:
        await log_login_attempt(
            db=db,
            user_id=None,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # LAYER 3: CHECK ACCOUNT STATUS
    if user.deleted_date:
        await log_login_attempt(
            db=db,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deleted by staff member"
        )

    if user.is_block:
        await log_login_attempt(
            db=db,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been blocked"
        )

    # LAYER 4: UPDATE LAST LOGIN
    if user.security:
        user.security.last_login = datetime.utcnow()
        user.security.failed_login_attempts = 0
        await db.commit()

    perm = await get_user_permissions(db, user.id)
    permission_names = [p.name for p in perm.permissions]

    # Create tokens
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "institution_type": user.institution.institution_type.value,
            "sub": user.email,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "permissions": permission_names,
            "is_profile_complete": user.is_profile_complete
        }
    )

    jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "jti": jti,
            "type": "refresh",
        }
    )

    expires_at = datetime.utcnow() + timedelta(days=1)

    await session_db_create_for_refresh_token(
        user_id=user.id,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
        db=db
    )

    await log_login_attempt(
        db=db,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=False,
        secure=True,           # True in production (HTTPS)
        samesite="lax",
        max_age=60 * 60 * 24 * 3,
        path="/"
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "institution_type": user.institution.institution_type.value,
        "role": user.role.value,
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "permissions": permission_names
    }


# ─────────────────────────────────────────────────────────────────────────────
# ACTIVATE PASSWORD

# ─────────────────────────────────────────────────────────────────────────────
@router.post("/activate/password")
async def activate_with_password(
    data: UserActivatePassword,
    db: AsyncSession = Depends(get_db)
):
    """
    Activate account by setting password
    """
    password = data.password

    if not validate_password(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least 6 characters, 1 uppercase, 1 lowercase, and 1 number."
        )

    user = await activate_user_with_password(
        db=db,
        activation_token=data.activation_token,
        password=data.password
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired activation token"
        )

  

    return {"message": "Account activated successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# REFRESH
# FIX: added rate limiting — was completely missing before
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token with FRESH permissions"""

    ip_address = _get_client_ip(request)

    # FIX: rate limit BEFORE any DB work — was entirely missing on this route
    is_rate_limited = await check_rate_limit_by_ip(
        db=db,
        ip_address=ip_address,
        max_attempts=20,        # more lenient than login since legitimate apps refresh often
        time_window_minutes=10
    )
    if is_rate_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later."
        )

    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    payload = decode_token(refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    # Validate session
    is_valid = await session_db_check_valid(jti=payload["jti"], db=db)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or revoked"
        )

    # Validate user still exists and is active
    user = await get_valid_user(
        db,
        identifier=payload["sub"],
        tenant_id=payload["tenant_id"]
    )

    if not user:
        raise HTTPException(status_code=401, detail="User no longer valid")

    # GET FRESH PERMISSIONS (in case they changed)
    perm = await get_user_permissions(db, user.id)
    permission_names = [p.name for p in perm.permissions]

    # Update last used
    await session_db_update_last_used(jti=payload["jti"], db=db)

    # CREATE NEW ACCESS TOKEN WITH FRESH PERMISSIONS
    new_access_token = create_access_token(
        data={
            "sub": user.email,
            "institution_type": user.institution.institution_type.value,
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "permissions": permission_names,
            "is_profile_complete": user.is_profile_complete,
            "type": "access",  
        }
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "permissions": permission_names,
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "institution_type": user.institution.institution_type.value,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LOGOUT
# FIX: added rate limiting to prevent DB pool exhaustion via session_db_revoke spam
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    ip_address = _get_client_ip(request)

    # FIX: rate limit to prevent repeated revoke DB calls — was missing before
    is_rate_limited = await check_rate_limit_by_ip(
        db=db,
        ip_address=ip_address,
        max_attempts=20,
        time_window_minutes=10
    )
    if is_rate_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later."
        )

    refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        payload = decode_token(refresh_token)

        if payload:
            jti = payload.get("jti")

            if jti:
                await session_db_revoke(jti=jti, db=db)

    response.delete_cookie(
        key="refresh_token",
        httponly=False,
        samesite="lax",
        secure=True,   # True in production (HTTPS)
        path="/"
    )

    return {"status": "success", "detail": "User logged out successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# FORGOT PASSWORD
# FIX: email sending moved to BackgroundTasks — was blocking the event loop
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/forgot-password")
async def forgot_password_endpoint(
    data: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
    Request password reset email
    """
    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "unknown")

    VAGUE_RESPONSE = {"message": "If email exists, reset link has been sent"}

    # RATE LIMIT
    is_rate_limited = await check_rate_limit_by_ip(
        db=db,
        ip_address=ip_address,
        max_attempts=3,
        time_window_minutes=15
    )
    if is_rate_limited:
        return VAGUE_RESPONSE

    # Log every attempt
    await log_login_attempt(
        db=db,
        user_id=None,
        ip_address=ip_address,
        user_agent=user_agent,
        success=False
    )

    reset_token = secrets.token_urlsafe(32)
    reset_token_expires = datetime.utcnow() + timedelta(minutes=20)

    user = await forgot_password(
        email=data.email,
        db=db,
        reset_token=reset_token,
        reset_token_expires=reset_token_expires
    )

    if not user:
        return VAGUE_RESPONSE

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    # FIX: email sending was synchronous/blocking — now runs in background
    # so the response returns immediately without waiting for SMTP
    background_tasks.add_task(
        send_password_reset_email,
        user.email,
        reset_link,
        user.first_name,
    )

    return {"message": "If email exists, reset link has been sent"}


# ─────────────────────────────────────────────────────────────────────────────
# RESET PASSWORD
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/reset-password")
async def reset_password_endpoint(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Reset password using token from email
    """
    if not validate_password(data.new_password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 6 characters, 1 uppercase letter, 1 lowercase letter, and 1 number."
        )

    user = await reset_password(
        reset_token=data.reset_token,
        new_password=data.new_password,
        db=db
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    return {"message": "Password reset successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE LOGIN
# FIX 1: id_token.verify_oauth2_token is synchronous/CPU-bound — offloaded to
#         thread pool via run_in_executor so event loop is not blocked
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/google", response_model=Token)
async def google_login(
    response: Response,
    request: Request,
    data: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Google OAuth Login

    Flow:
    1. Rate limiting
    2. Verify Google ID token (offloaded to thread pool)
    3. Find user by Google ID or email
    4. Link Google account if needed
    5. Create session and return tokens
    """

    ip_address = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "unknown")

    # LAYER 1: RATE LIMITING
    is_rate_limited = await check_rate_limit_by_ip(
        db=db,
        ip_address=ip_address,
        max_attempts=5,
        time_window_minutes=10
    )
    if is_rate_limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please try again in 10 minutes."
        )

    # LAYER 2: VERIFY GOOGLE TOKEN
    # FIX: verify_oauth2_token is synchronous + does network I/O to Google's
    #      public key endpoint — blocks the event loop on a single Uvicorn worker.
    #      run_in_executor moves it to a thread so other requests can proceed.
    def _verify_google_token():
        return id_token.verify_oauth2_token(
            data.id_token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID,
            clock_skew_in_seconds=10
        )

    try:
        loop = asyncio.get_event_loop()
        idinfo = await loop.run_in_executor(None, _verify_google_token)

        current_time = datetime.utcnow().timestamp()

        if idinfo.get('exp', 0) < current_time:
            raise ValueError("Token expired")

        if idinfo.get('aud') != settings.GOOGLE_CLIENT_ID:
            raise ValueError("Invalid audience")

        if idinfo.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
            raise ValueError("Invalid issuer")

        if not idinfo.get("email_verified", False):
            raise ValueError("Email not verified by Google")

        google_id = idinfo["sub"]
        email = idinfo["email"].lower()

    except ValueError as e:
        print(f"[Google Auth Error] ValueError: {e}")
        await log_login_attempt(
            db=db,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except Exception as e:
        await log_login_attempt(
            db=db,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication failed"
        )

    # LAYER 3: FIND OR LINK USER ACCOUNT
    user = await find_user_by_google_id(
        db=db,
        google_id=google_id,
        tenant_id=data.tenant_id
    )

    if not user:
        user = await find_user_by_email_and_institution(
            db=db,
            email=email,
            tenant_id=data.tenant_id
        )

        if user:
            user = await link_google_account(
                db=db,
                user=user,
                google_id=google_id
            )
        else:
            await log_login_attempt(
                db=db,
                ip_address=ip_address,
                user_agent=user_agent,
                success=False
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No account found. Please contact your administrator."
            )

    # LAYER 4: CHECK ACCOUNT STATUS
    if user.deleted_date:
        await log_login_attempt(
            db=db,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deleted by staff member"
        )

    if user.is_block:
        await log_login_attempt(
            db=db,
            user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=False
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account has been blocked"
        )

    # LAYER 5: UPDATE LAST LOGIN
    if user.security:
        user.security.last_login = datetime.utcnow()
        user.security.failed_login_attempts = 0
        await db.commit()

    if not user.is_active:
        user.is_active = True
        await db.commit()

    # LAYER 6: CREATE TOKENS & SESSION
    perm = await get_user_permissions(db, user.id)
    permission_names = [p.name for p in perm.permissions]

    access_token = create_access_token(
        data={
            "user_id": user.id,
            "institution_type": user.institution.institution_type.value,
            "sub": user.email,
            "tenant_id": user.tenant_id,
            "role": user.role.value,
            "permissions": permission_names,
            "is_profile_complete": user.is_profile_complete,
            "type": "access",  
        }
    )

    jti = str(uuid.uuid4())
    refresh_token = create_refresh_token(
        data={
            "sub": user.email,
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "jti": jti,
            "type": "refresh",   
        }
    )

    expires_at = datetime.utcnow() + timedelta(days=1)

    await session_db_create_for_refresh_token(
        user_id=user.id,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
        db=db
    )

    await log_login_attempt(
        db=db,
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=True
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,   # True in production (HTTPS)
            # domain=".YOUR_APP.com",
        samesite="lax",
        max_age=60 * 60 * 24 * 3,
        path="/"
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "institution_type": user.institution.institution_type.value,
        "role": user.role.value,
        "permissions": permission_names,
        "user_id": user.id,
        "tenant_id": user.tenant_id
    }


# @router.get("/me", response_model=UserResponse)
# async def get_me(
#     current_user: User = Depends(get_current_user)
# ):
#     """
#     Get current user info
#     """
#     return current_user