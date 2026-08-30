"""
super_admin_router.py
---------------------
Auth routes for SuperAdmin:
  POST /super-admin/auth/login          — step 1: password check → issues OTP
  POST /super-admin/auth/verify-otp     — step 2: OTP verify → issues tokens
  POST /super-admin/auth/refresh        — refresh access token
  POST /super-admin/auth/logout         — revoke session
  POST /super-admin/auth/forgot-password
  POST /super-admin/auth/reset-password
  GET  /super-admin/auth/me             — current profile
  PUT  /super-admin/auth/me             — update profile

All tokens carry  "type": "super_admin"  so they are NEVER accepted on
regular user endpoints (which check for  "type": "user" / "refresh").
Session lifetime: 6 hours (access) + 1 day (refresh cookie).
"""

import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.services.email import send_email
from app.schemas.super_admin_schema import (
    SuperAdminLoginRequest,
    SuperAdminOTPVerify,
    SuperAdminForgotPasswordRequest,
    SuperAdminResetPasswordRequest,
    SuperAdminToken,
    SuperAdminProfileResponse,
    SuperAdminUpdateRequest,
)
from app.crud.super_admin_crud import (
    authenticate_super_admin,
    create_and_send_otp,
    verify_otp,
    session_create,
    session_check_valid,
    session_update_last_used,
    session_revoke,
    log_login,
    initiate_forgot_password,
    reset_password_with_token,
    update_super_admin_profile,
    check_rate_limit,
    get_super_admin_by_id,
)
from app.super_admin_deps import get_current_super_admin
from app.crud.super_admin_crud import get_super_admin_dashboard
router = APIRouter(prefix="/super-admin/auth", tags=["Super Admin Auth"])

SESSION_MINUTES = 15    # access token lifetime
REFRESH_DAYS  = 3       # refresh cookie lifetime


# ─── helpers ────────────────────────────────────────────────────────────────

def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _make_access_token(admin) -> str:
    return create_access_token(
        data={
            "sub": admin.email,
            "super_admin_id": admin.id,
            "role": admin.role.value,
            "type": "super_admin",          # ← guards against token-swap with user tokens
            "permissions": admin.permissions or {},
        },
        expires_delta=timedelta(minutes=SESSION_MINUTES),
    )


def _make_refresh_token(admin, jti: str) -> str:
    return create_refresh_token(
        data={
            "sub": admin.email,
            "super_admin_id": admin.id,
            "jti": jti,
            "type": "super_admin_refresh",
        },
        expires_delta=timedelta(days=REFRESH_DAYS),
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="sa_refresh_token",         # separate cookie key from regular user
        value=token,
        httponly=True,
        secure=True,                    # set True in production (HTTPS)
        samesite="none",
        max_age=60 * 60 * 24 * REFRESH_DAYS,
        path="/",        # scoped — not sent to user routes
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1 — PASSWORD LOGIN  →  sends OTP
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/login")
async def login_step1(
    data: SuperAdminLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate identifier + password.
    On success: generate OTP, email it, return a short-lived session_token
    that the client must present at /verify-otp.
    """
    ip          = _get_ip(request)
    user_agent  = request.headers.get("User-Agent", "unknown")

    # Rate limit — strict: 5 failures per 10 min per IP
    if await check_rate_limit(db, ip_address=ip, max_attempts=5, window_minutes=10):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again in 10 minutes.",
        )

    admin = await authenticate_super_admin(db, data.identifier, data.password)

    if not admin:
        # Log failed attempt (no admin id available)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if admin.is_block:
        await log_login(db, admin.id, ip, user_agent, success=False)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    # Send OTP
    sent = await create_and_send_otp(db, admin)
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send OTP email. Please try again.",
        )

    # Issue a short-lived session_token (10 min) so the client can call /verify-otp
    # This token is NOT an access token — it only permits the OTP step.
    session_token = create_access_token(
        data={
            "sub": admin.email,
            "super_admin_id": admin.id,
            "type": "super_admin_otp_pending",
        },
        expires_delta=timedelta(minutes=10),
    )

    return {
        "message": "OTP sent to your registered email",
        "session_token": session_token,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2 — OTP VERIFY  →  issues real tokens
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/verify-otp", response_model=SuperAdminToken)
async def login_step2(
    data: SuperAdminOTPVerify,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    ip         = _get_ip(request)
    user_agent = request.headers.get("User-Agent", "unknown")

    # Validate session_token from step 1
    payload = decode_token(data.session_token)
    if not payload or payload.get("type") != "super_admin_otp_pending":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP session",
        )

    super_admin_id = payload.get("super_admin_id")
    admin = await get_super_admin_by_id(db, super_admin_id)

    if not admin:
        raise HTTPException(status_code=404, detail="Super admin not found")

    if not await verify_otp(db, admin, data.otp_code):
        await log_login(db, admin.id, ip, user_agent, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )

    # OTP good — issue real tokens
    jti           = str(uuid.uuid4())
    access_token  = _make_access_token(admin)
    refresh_token = _make_refresh_token(admin, jti)
    expires_at    = datetime.utcnow() + timedelta(days=REFRESH_DAYS)

    await session_create(
        db            = db,
        super_admin_id = admin.id,
        jti           = jti,
        expires_at    = expires_at,
        ip_address    = ip,
        user_agent    = user_agent,
    )

    await log_login(db, admin.id, ip, user_agent, success=True)

    _set_refresh_cookie(response, refresh_token)

    return SuperAdminToken(
        access_token=access_token,
        role=admin.role.value,
        super_admin_id=admin.id,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REFRESH
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/refresh")
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = _get_ip(request)

    if await check_rate_limit(db, ip_address=ip, max_attempts=30, window_minutes=10):
        raise HTTPException(status_code=429, detail="Too many requests")

    token = request.cookies.get("sa_refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="Missing refresh token")

    payload = decode_token(token)
    if not payload or payload.get("type") != "super_admin_refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    jti = payload.get("jti")
    if not jti or not await session_check_valid(db, jti):
        raise HTTPException(status_code=401, detail="Session expired or revoked")

    admin = await get_super_admin_by_id(db, payload.get("super_admin_id"))
    if not admin:
        raise HTTPException(status_code=401, detail="Super admin not found")

    await session_update_last_used(db, jti)

    return {
        "access_token": _make_access_token(admin),
        "token_type": "bearer",
        "role": admin.role.value,
        "super_admin_id": admin.id,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# LOGOUT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = request.cookies.get("sa_refresh_token")
    if token:
        payload = decode_token(token)
        if payload:
            jti = payload.get("jti")
            if jti:
                await session_revoke(db, jti)

    response.delete_cookie(
        key="sa_refresh_token",
        httponly=True,
        samesite="none",
        secure=True,
        path="/",
    )
    return {"status": "success", "detail": "Logged out"}


# ═══════════════════════════════════════════════════════════════════════════════
# FORGOT PASSWORD
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/forgot-password")
async def forgot_password(
    data: SuperAdminForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    ip = _get_ip(request)
    VAGUE = {"message": "If that email exists, a reset link has been sent"}

    if await check_rate_limit(db, ip_address=ip, max_attempts=3, window_minutes=15):
        return VAGUE

    admin = await initiate_forgot_password(db, data.email)
    if not admin:
        return VAGUE

    reset_link = f"{settings.FRONTEND_URL}/super-admin/reset-password?token={admin.security.password_reset_token}"

    def _send_reset_email():
        html = f"""
        <!DOCTYPE html><html><body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;">
        <div style="max-width:480px;margin:40px auto;background:#fff;border-radius:16px;
                    box-shadow:0 4px 24px rgba(0,0,0,0.07);overflow:hidden;">
          <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);padding:32px 40px 24px;">
            <p style="margin:0;color:#94a3b8;font-size:11px;letter-spacing:2px;text-transform:uppercase;">
              Super Admin Portal
            </p>
            <h2 style="margin:8px 0 0;color:#fff;font-size:22px;font-weight:700;">Password Reset</h2>
          </div>
          <div style="padding:36px 40px;">
            <p style="margin:0 0 16px;font-size:14px;color:#475569;">Hi <strong>{admin.name}</strong>,</p>
            <p style="margin:0 0 28px;font-size:14px;color:#64748b;line-height:1.6;">
              Click the button below to reset your password. This link expires in <strong>30 minutes</strong>.
            </p>
            <div style="text-align:center;margin-bottom:28px;">
              <a href="{reset_link}" style="display:inline-block;background:#0f172a;color:#fff;
                 text-decoration:none;font-size:14px;font-weight:700;padding:14px 36px;
                 border-radius:10px;letter-spacing:0.3px;">Reset Password</a>
            </div>
            <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">
              If you didn't request this, ignore this email.
            </p>
          </div>
        </div>
        </body></html>
        """
        send_email(to=admin.email, subject="Super Admin — Password Reset", html=html)

    background_tasks.add_task(_send_reset_email)
    return {"message": "If that email exists, a reset link has been sent"}


# ═══════════════════════════════════════════════════════════════════════════════
# RESET PASSWORD
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/reset-password")
async def reset_password(
    data: SuperAdminResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    admin = await reset_password_with_token(db, data.reset_token, data.new_password)
    if not admin:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    return {"message": "Password reset successfully"}


# ═══════════════════════════════════════════════════════════════════════════════
# ME — current profile (requires valid access token)
# ═══════════════════════════════════════════════════════════════════════════════

def _require_super_admin(request: Request) -> dict:
    """Minimal inline guard — extracts payload from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = auth.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    if not payload or payload.get("type") != "super_admin":
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


@router.get("/me", response_model=SuperAdminProfileResponse)
async def get_me(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = _require_super_admin(request)
    admin = await get_super_admin_by_id(db, payload["super_admin_id"])
    if not admin:
        raise HTTPException(status_code=404, detail="Not found")
    return SuperAdminProfileResponse.model_validate(admin)


@router.put("/me", response_model=SuperAdminProfileResponse)
async def update_me(
    data: SuperAdminUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = _require_super_admin(request)
    updated = await update_super_admin_profile(
        db,
        payload["super_admin_id"],
        data.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Not found")
    return SuperAdminProfileResponse.model_validate(updated)



# dashboard 
"""
super_admin_dashboard_router.py
────────────────────────────────
Routes:
  GET  /super-admin/dashboard               — full dashboard payload
  GET  /super-admin/institutions            — paginated institution list with counts
  POST /super-admin/institutions/{tenant_id}/toggle-block  — block / unblock
"""

from fastapi import  Query

# from app.core.security import get_current_super_admin   # uncomment when auth is ready
from app.crud.super_admin_crud import (

    get_all_institutions_list,
    toggle_institution_block,
)

# router = APIRouter(prefix="/super-admin", tags=["Super Admin – Dashboard"])


@router.get(
    "/dashboard",
    summary="Super-admin platform overview dashboard",
)
async def super_admin_dashboard_endpoint(
    current=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_super_admin_dashboard(db)


@router.get(
    "/institutions",
    summary="Paginated institution list with user & class counts",
)
async def list_institutions_endpoint(
    offset: int = Query(0, ge=0),
    limit:  int = Query(100, ge=1, le=500),
    current=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await get_all_institutions_list(db, offset=offset, limit=limit)


@router.post(
    "/institutions/{tenant_id}/toggle-block",
    summary="Block or unblock an institution",
)
async def toggle_block_endpoint(
    tenant_id: str,
    current=Depends(get_current_super_admin),
    db: AsyncSession = Depends(get_db),
):
    return await toggle_institution_block(db, tenant_id)