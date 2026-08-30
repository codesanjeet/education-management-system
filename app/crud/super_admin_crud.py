import secrets
import random
import string
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_,or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.super_admin_model import (
    SuperAdminDB,
    SuperAdminSecurityDB,
    SuperAdminSessionDB,
    SuperAdminLogDB,
)
from app.core.security import verify_password, get_password_hash
from app.services.email import send_email


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — LOOKUP HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def get_super_admin_by_id(
    db: AsyncSession,
    super_admin_id: int
) -> Optional[SuperAdminDB]:
    result = await db.execute(
        select(SuperAdminDB)
        .options(selectinload(SuperAdminDB.security))
        .where(SuperAdminDB.id == super_admin_id)
    )
    return result.scalars().first()


async def get_super_admin_by_identifier(
    db: AsyncSession,
    identifier: str          # email or username
) -> Optional[SuperAdminDB]:
    """Find a super admin by email OR username (case-insensitive)."""
    ident = identifier.lower().strip()
    result = await db.execute(
        select(SuperAdminDB)
        .options(selectinload(SuperAdminDB.security))
        .where(
            (SuperAdminDB.email == ident) | (SuperAdminDB.user_name == ident)
        )
    )
    return result.scalars().first()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — PASSWORD AUTH
# ═══════════════════════════════════════════════════════════════════════════════

async def authenticate_super_admin(
    db: AsyncSession,
    identifier: str,
    password: str,
) -> Optional[SuperAdminDB]:
    """
    Verify identifier + password.
    Increments failed_login_attempts on failure.
    Resets counter on success.
    Does NOT issue tokens — that happens in the router.
    """
    admin = await get_super_admin_by_identifier(db, identifier)

    if not admin or not admin.security:
        return None

    if not verify_password(password, admin.security.password_hash):
        # Track failed attempt
        admin.security.failed_login_attempts = (admin.security.failed_login_attempts or 0) + 1
        admin.security.last_failed_login = datetime.utcnow()
        await db.commit()
        return None

    # Successful password check — reset counter
    admin.security.failed_login_attempts = 0
    await db.commit()
    return admin


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — OTP  (email-based, always on)
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


async def create_and_send_otp(
    db: AsyncSession,
    admin: SuperAdminDB
) -> bool:
    """
    Generate a 6-digit OTP, store its hash in otp_secret,
    send it to the admin's email. Returns True on success.
    """
    if not admin.security:
        return False

    otp = _generate_otp()
    # Store the raw OTP hashed so we don't keep plaintext in DB
    admin.security.otp_secret = get_password_hash(otp)
    await db.commit()

    html = f"""
    <!DOCTYPE html><html><body style="font-family:'Segoe UI',Arial,sans-serif;background:#f8fafc;">
    <div style="max-width:480px;margin:40px auto;background:#fff;border-radius:16px;
                box-shadow:0 4px 24px rgba(0,0,0,0.07);overflow:hidden;">
      <div style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);
                  padding:32px 40px 24px;">
        <p style="margin:0;color:#94a3b8;font-size:11px;letter-spacing:2px;
                  text-transform:uppercase;">Super Admin Portal</p>
        <h2 style="margin:8px 0 0;color:#fff;font-size:22px;font-weight:700;">
          Login Verification
        </h2>
      </div>
      <div style="padding:36px 40px;">
        <p style="margin:0 0 8px;font-size:14px;color:#475569;">
          Hi <strong>{admin.name}</strong>,
        </p>
        <p style="margin:0 0 28px;font-size:14px;color:#64748b;line-height:1.6;">
          Use the code below to complete your login.
          It expires in <strong>10 minutes</strong>.
        </p>
        <div style="text-align:center;background:#f1f5f9;border-radius:12px;
                    padding:28px 20px;margin-bottom:28px;">
          <span style="font-size:40px;font-weight:800;letter-spacing:14px;
                       color:#0f172a;font-family:'Courier New',monospace;">{otp}</span>
        </div>
        <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">
          Never share this code. If you didn't request this, secure your account immediately.
        </p>
      </div>
      <div style="background:#f8fafc;padding:16px 40px;border-top:1px solid #e2e8f0;">
        <p style="margin:0;font-size:11px;color:#cbd5e1;">
          This is an automated message — do not reply.
        </p>
      </div>
    </div>
    </body></html>
    """

    result = send_email(
        to=admin.email,
        subject="Your Super Admin Login Code",
        html=html,
    )
    return result.get("success", False)


async def verify_otp(
    db: AsyncSession,
    admin: SuperAdminDB,
    otp_code: str,
) -> bool:
    """
    Verify OTP. On success, clears otp_secret and updates last_login.
    On failure, increments failed_login_attempts.
    """
    if not admin.security or not admin.security.otp_secret:
        return False

    if not verify_password(otp_code, admin.security.otp_secret):
        admin.security.failed_login_attempts = (admin.security.failed_login_attempts or 0) + 1
        await db.commit()
        return False

    # Clear OTP after successful use
    admin.security.otp_secret = None
    admin.security.last_login = datetime.utcnow()
    admin.security.failed_login_attempts = 0
    await db.commit()
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

async def session_create(
    db: AsyncSession,
    super_admin_id: int,
    jti: str,
    expires_at: datetime,
    ip_address: Optional[str],
    user_agent: Optional[str],
) -> SuperAdminSessionDB:
    session = SuperAdminSessionDB(
        super_admin_id=super_admin_id,
        jti=jti,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def session_check_valid(db: AsyncSession, jti: str) -> bool:
    """Return True if session exists, is not revoked, and is not expired."""
    result = await db.execute(
        select(SuperAdminSessionDB).where(
            and_(
                SuperAdminSessionDB.jti == jti,
                SuperAdminSessionDB.revoked == False,
                SuperAdminSessionDB.expires_at > datetime.utcnow(),
            )
        )
    )
    return result.scalars().first() is not None


async def session_update_last_used(db: AsyncSession, jti: str) -> None:
    result = await db.execute(
        select(SuperAdminSessionDB).where(SuperAdminSessionDB.jti == jti)
    )
    session = result.scalars().first()
    if session:
        session.last_used_at = datetime.utcnow()
        await db.commit()


async def session_revoke(db: AsyncSession, jti: str) -> None:
    result = await db.execute(
        select(SuperAdminSessionDB).where(SuperAdminSessionDB.jti == jti)
    )
    session = result.scalars().first()
    if session:
        session.revoked = True
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — LOGIN LOG
# ═══════════════════════════════════════════════════════════════════════════════

async def log_login(
    db: AsyncSession,
    super_admin_id: int,
    ip_address: Optional[str],
    user_agent: Optional[str],
    success: bool,
) -> None:
    entry = SuperAdminLogDB(
        super_admin_id=super_admin_id,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
    )
    db.add(entry)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — FORGOT / RESET PASSWORD
# ═══════════════════════════════════════════════════════════════════════════════

async def initiate_forgot_password(
    db: AsyncSession,
    email: str,
) -> Optional[SuperAdminDB]:
    """
    Generate a reset token and persist it.
    Returns the admin so the router can email the link.
    Returns None if email not found (caller uses vague response).
    """
    result = await db.execute(
        select(SuperAdminDB)
        .options(selectinload(SuperAdminDB.security))
        .where(SuperAdminDB.email == email.lower().strip())
    )
    admin = result.scalars().first()
    if not admin or not admin.security:
        return None

    token = secrets.token_urlsafe(32)
    admin.security.password_reset_token = token
    admin.security.password_reset_expires = datetime.utcnow() + timedelta(minutes=30)
    await db.commit()
    return admin


async def reset_password_with_token(
    db: AsyncSession,
    reset_token: str,
    new_password: str,
) -> Optional[SuperAdminDB]:
    """
    Validate token, hash and set new password, clear token fields.
    Returns admin on success, None on invalid/expired token.
    """
    result = await db.execute(
        select(SuperAdminDB)
        .options(selectinload(SuperAdminDB.security))
        .join(SuperAdminSecurityDB)
        .where(
            and_(
                SuperAdminSecurityDB.password_reset_token == reset_token,
                SuperAdminSecurityDB.password_reset_expires > datetime.utcnow(),
            )
        )
    )
    admin = result.scalars().first()
    if not admin or not admin.security:
        return None

    admin.security.password_hash = get_password_hash(new_password)
    admin.security.password_reset_token = None
    admin.security.password_reset_expires = None
    admin.security.last_password_change = datetime.utcnow()
    await db.commit()
    return admin


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — PROFILE UPDATE
# ═══════════════════════════════════════════════════════════════════════════════

async def update_super_admin_profile(
    db: AsyncSession,
    super_admin_id: int,
    update_data: dict,
) -> Optional[SuperAdminDB]:
    admin = await get_super_admin_by_id(db, super_admin_id)
    if not admin:
        return None

    for key, value in update_data.items():
        if hasattr(admin, key) and value is not None:
            setattr(admin, key, value)

    await db.commit()
    await db.refresh(admin)
    return admin


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — RATE LIMITING  (IP-based, reuses super_admin_logs table)
# ═══════════════════════════════════════════════════════════════════════════════

async def check_rate_limit(
    db: AsyncSession,
    ip_address: str,
    max_attempts: int = 5,
    window_minutes: int = 10,
) -> bool:
    """Return True if IP is rate-limited (too many failed attempts)."""
    from sqlalchemy import func

    window_start = datetime.utcnow() - timedelta(minutes=window_minutes)

    result = await db.execute(
        select(func.count(SuperAdminLogDB.id)).where(
            and_(
                SuperAdminLogDB.ip_address == ip_address,
                SuperAdminLogDB.success == False,
                SuperAdminLogDB.login_time >= window_start,   # login_time is the timestamp
            )
        )
    )
    count = result.scalar() or 0
    return count >= max_attempts



# crud specific 
from ..models.super_admin_model import SuperAdminDB

async def get_super_admin_by_id(
    db: AsyncSession,
    super_admin_id: int
) -> Optional[SuperAdminDB]:
    result = await db.execute(
        select(SuperAdminDB)
        .options(selectinload(SuperAdminDB.security))
        .where(SuperAdminDB.id == super_admin_id)
    )
    return result.scalars().first()






















# Dashboard 
"""
super_admin_dashboard_fun.py
─────────────────────────────
All DB queries that power the Super-Admin dashboard.
No tenant scoping — super-admin sees everything.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, case, select, distinct, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.models.institution_model import InstitutionDB, InstitutionUsageDB
from app.models.user_model import UserDB, UserRoleEnum
from app.models.classes_model import ClassDB
from app.core.exceptions import DatabaseError, InstitutionNotFoundError

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    # DB columns are TIMESTAMP WITHOUT TIME ZONE — use naive UTC everywhere
    return datetime.utcnow()


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


# ── Institution stats ─────────────────────────────────────────────────────────

async def get_institution_stats(db: AsyncSession) -> dict[str, Any]:
    try:
        row = await db.execute(
            select(
                func.count(InstitutionDB.id).label("total"),
                func.sum(case((InstitutionDB.is_verified == True, 1), else_=0)).label("verified"),
                func.sum(case((InstitutionDB.is_rejected == True, 1), else_=0)).label("rejected"),
                func.sum(case((InstitutionDB.is_block == True, 1), else_=0)).label("blocked"),
                func.sum(
                    case(
                        (
                            (InstitutionDB.is_verified == False)
                            & (InstitutionDB.is_rejected == False)
                            & (InstitutionDB.is_block == False),
                            1,
                        ),
                        else_=0,
                    )
                ).label("pending"),
                func.sum(
                    case((InstitutionDB.deleted_date.isnot(None), 1), else_=0)
                ).label("soft_deleted"),
            )
        )
        counts = row.mappings().one()

        type_rows = await db.execute(
            select(
                InstitutionDB.institution_type.label("type"),
                func.count(InstitutionDB.id).label("count"),
            ).group_by(InstitutionDB.institution_type)
        )
        by_type = [
            {"type": r["type"], "count": r["count"]}
            for r in type_rows.mappings().all()
        ]

        six_months_ago = _month_start(_now() - timedelta(days=180))
        _inst_month = func.date_trunc("month", InstitutionDB.created_at).label("month")
        monthly_rows = await db.execute(
            select(
                _inst_month,
                func.count(InstitutionDB.id).label("count"),
            )
            .where(InstitutionDB.created_at >= six_months_ago)
            .group_by(text("month"))
            .order_by(text("month"))
        )
        monthly_signups = [
            {"month": r["month"].strftime("%b %Y"), "count": r["count"]}
            for r in monthly_rows.mappings().all()
        ]

        return {
            "total": counts["total"] or 0,
            "verified": counts["verified"] or 0,
            "rejected": counts["rejected"] or 0,
            "blocked": counts["blocked"] or 0,
            "pending": counts["pending"] or 0,
            "soft_deleted": counts["soft_deleted"] or 0,
            "by_type": by_type,
            "monthly_signups": monthly_signups,
        }

    except SQLAlchemyError as exc:
        logger.error("DB error in get_institution_stats: %s", exc, exc_info=True)
        raise DatabaseError("Unable to fetch institution stats") from exc


# ── User / role stats ─────────────────────────────────────────────────────────

async def get_user_stats(db: AsyncSession) -> dict[str, Any]:
    try:
        row = await db.execute(
            select(
                func.count(UserDB.id).label("total"),
                func.sum(case((UserDB.role == UserRoleEnum.STUDENT.value, 1), else_=0)).label("students"),
                func.sum(case((UserDB.role == UserRoleEnum.TEACHER.value, 1), else_=0)).label("teachers"),
                func.sum(case((UserDB.role == UserRoleEnum.ADMIN.value, 1), else_=0)).label("admins"),
                func.sum(case((UserDB.role == UserRoleEnum.PRINCIPAL.value, 1), else_=0)).label("principals"),
                func.sum(case((UserDB.is_block == True, 1), else_=0)).label("blocked"),
                func.sum(case((UserDB.deleted_date.isnot(None), 1), else_=0)).label("deleted"),
            )
        )
        counts = row.mappings().one()

        six_months_ago = _month_start(_now() - timedelta(days=180))
        _user_month = func.date_trunc("month", UserDB.created_at).label("month")
        monthly_rows = await db.execute(
            select(
                _user_month,
                func.count(UserDB.id).label("count"),
            )
            .where(UserDB.created_at >= six_months_ago)
            .group_by(text("month"))
            .order_by(text("month"))
        )
        monthly_users = [
            {"month": r["month"].strftime("%b %Y"), "count": r["count"]}
            for r in monthly_rows.mappings().all()
        ]

        return {
            "total": counts["total"] or 0,
            "students": counts["students"] or 0,
            "teachers": counts["teachers"] or 0,
            "admins": counts["admins"] or 0,
            "principals": counts["principals"] or 0,
            "blocked": counts["blocked"] or 0,
            "deleted": counts["deleted"] or 0,
            "monthly_new_users": monthly_users,
        }

    except SQLAlchemyError as exc:
        logger.error("DB error in get_user_stats: %s", exc, exc_info=True)
        raise DatabaseError("Unable to fetch user stats") from exc


# ── Class stats ───────────────────────────────────────────────────────────────

async def get_class_stats(db: AsyncSession) -> dict[str, Any]:
    try:
        row = await db.execute(
            select(
                func.count(ClassDB.id).label("total"),
                func.sum(ClassDB.max_student_limit).label("total_capacity"),
                func.sum(ClassDB.current_student_count).label("total_enrolled"),
                func.sum(case((ClassDB.deleted_date.isnot(None), 1), else_=0)).label("soft_deleted"),
            )
        )
        counts = row.mappings().one()

        total_capacity = counts["total_capacity"] or 0
        total_enrolled = counts["total_enrolled"] or 0
        utilisation_pct = (
            round((total_enrolled / total_capacity) * 100, 1) if total_capacity else 0.0
        )

        per_inst_rows = await db.execute(
            select(
                InstitutionDB.institute_name.label("institution"),
                InstitutionDB.tenant_id.label("tenant_id"),
                func.count(ClassDB.id).label("class_count"),
            )
            .join(ClassDB, ClassDB.institution_id == InstitutionDB.id)
            .group_by(InstitutionDB.id, InstitutionDB.institute_name, InstitutionDB.tenant_id)
            .order_by(func.count(ClassDB.id).desc())
            .limit(10)
        )
        top_institutions = [
            {"institution": r["institution"], "tenant_id": r["tenant_id"], "class_count": r["class_count"]}
            for r in per_inst_rows.mappings().all()
        ]

        return {
            "total": counts["total"] or 0,
            "soft_deleted": counts["soft_deleted"] or 0,
            "total_capacity": total_capacity,
            "total_enrolled": total_enrolled,
            "utilisation_pct": utilisation_pct,
            "top_institutions_by_classes": top_institutions,
        }

    except SQLAlchemyError as exc:
        logger.error("DB error in get_class_stats: %s", exc, exc_info=True)
        raise DatabaseError("Unable to fetch class stats") from exc


# ── Platform usage stats ──────────────────────────────────────────────────────

async def get_platform_usage_stats(db: AsyncSession) -> dict[str, Any]:
    try:
        row = await db.execute(
            select(
                func.count(InstitutionUsageDB.id).label("institutions_with_usage"),
                func.sum(InstitutionUsageDB.ai_credits_balance).label("total_ai_credits"),
                func.sum(InstitutionUsageDB.email_balance).label("total_email_balance"),
                func.sum(InstitutionUsageDB.storage_used_mb).label("total_storage_mb"),
                func.avg(InstitutionUsageDB.storage_used_mb).label("avg_storage_mb"),
            )
        )
        counts = row.mappings().one()

        storage_rows = await db.execute(
            select(
                InstitutionDB.institute_name.label("institution"),
                InstitutionDB.tenant_id.label("tenant_id"),
                InstitutionUsageDB.storage_used_mb.label("storage_mb"),
                InstitutionUsageDB.ai_credits_balance.label("ai_credits"),
            )
            .join(InstitutionDB, InstitutionDB.id == InstitutionUsageDB.institution_id)
            .order_by(InstitutionUsageDB.storage_used_mb.desc())
            .limit(10)
        )
        top_storage = [
            {
                "institution": r["institution"],
                "tenant_id": r["tenant_id"],
                "storage_mb": round(r["storage_mb"] or 0, 2),
                "ai_credits": r["ai_credits"] or 0,
            }
            for r in storage_rows.mappings().all()
        ]

        return {
            "institutions_with_usage_record": counts["institutions_with_usage"] or 0,
            "total_ai_credits": int(counts["total_ai_credits"] or 0),
            "total_email_balance": int(counts["total_email_balance"] or 0),
            "total_storage_mb": round(float(counts["total_storage_mb"] or 0), 2),
            "avg_storage_mb": round(float(counts["avg_storage_mb"] or 0), 2),
            "top_storage_consumers": top_storage,
        }

    except SQLAlchemyError as exc:
        logger.error("DB error in get_platform_usage_stats: %s", exc, exc_info=True)
        raise DatabaseError("Unable to fetch platform usage stats") from exc


# ── All institutions list (for the table) ─────────────────────────────────────

async def get_all_institutions_list(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Full institution list with per-institution user + class counts
    for the dashboard table.
    """
    try:
        # User counts per institution
        user_counts_sq = (
            select(
                UserDB.institution_id.label("institution_id"),
                func.count(UserDB.id).label("total_users"),
                func.sum(case((UserDB.role == UserRoleEnum.STUDENT.value, 1), else_=0)).label("students"),
                func.sum(case((UserDB.role == UserRoleEnum.TEACHER.value, 1), else_=0)).label("teachers"),
                func.sum(case((UserDB.role == UserRoleEnum.ADMIN.value, 1), else_=0)).label("admins"),
                func.sum(case((UserDB.role == UserRoleEnum.PRINCIPAL.value, 1), else_=0)).label("principals"),
            )
            .group_by(UserDB.institution_id)
            .subquery()
        )

        # Class counts per institution
        class_counts_sq = (
            select(
                ClassDB.institution_id.label("institution_id"),
                func.count(ClassDB.id).label("total_classes"),
                func.sum(ClassDB.max_student_limit).label("capacity"),
                func.sum(ClassDB.current_student_count).label("enrolled"),
            )
            .group_by(ClassDB.institution_id)
            .subquery()
        )

        rows = await db.execute(
            select(
                InstitutionDB.id,
                InstitutionDB.tenant_id,
                InstitutionDB.institute_name,
                InstitutionDB.institution_type,
                InstitutionDB.email,
                InstitutionDB.phone,
                InstitutionDB.phone_country_code,
                InstitutionDB.address,
                InstitutionDB.city,
                InstitutionDB.state,
                InstitutionDB.pincode,
                InstitutionDB.country,
                InstitutionDB.logo,
                InstitutionDB.primary_website,
                InstitutionDB.year_established,
                InstitutionDB.is_verified,
                InstitutionDB.is_rejected,
                InstitutionDB.is_block,
                InstitutionDB.deleted_date,
                InstitutionDB.created_at,
                InstitutionDB.updated_at,
                # user counts
                func.coalesce(user_counts_sq.c.total_users, 0).label("total_users"),
                func.coalesce(user_counts_sq.c.students, 0).label("students"),
                func.coalesce(user_counts_sq.c.teachers, 0).label("teachers"),
                func.coalesce(user_counts_sq.c.admins, 0).label("admins"),
                func.coalesce(user_counts_sq.c.principals, 0).label("principals"),
                # class counts
                func.coalesce(class_counts_sq.c.total_classes, 0).label("total_classes"),
                func.coalesce(class_counts_sq.c.capacity, 0).label("capacity"),
                func.coalesce(class_counts_sq.c.enrolled, 0).label("enrolled"),
                # per-institution platform usage (0 if no record yet)
                func.coalesce(InstitutionUsageDB.ai_credits_balance, 0).label("ai_credits"),
                func.coalesce(InstitutionUsageDB.email_balance, 0).label("email_balance"),
                func.coalesce(InstitutionUsageDB.storage_used_mb, 0.0).label("storage_used_mb"),
                func.coalesce(InstitutionUsageDB.ai_voice_agents_balance_min, 0).label("ai_voice_minutes"),
            )
            .outerjoin(user_counts_sq, user_counts_sq.c.institution_id == InstitutionDB.id)
            .outerjoin(class_counts_sq, class_counts_sq.c.institution_id == InstitutionDB.id)
            .outerjoin(InstitutionUsageDB, InstitutionUsageDB.institution_id == InstitutionDB.id)
            .order_by(InstitutionDB.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        total_count = await db.scalar(select(func.count(InstitutionDB.id)))

        items = []
        for r in rows.mappings().all():
            d = dict(r)
            # serialise non-JSON-safe types
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            if d.get("updated_at"):
                d["updated_at"] = d["updated_at"].isoformat()
            if d.get("deleted_date"):
                d["deleted_date"] = str(d["deleted_date"])
            if d.get("institution_type"):
                d["institution_type"] = str(d["institution_type"]) if not isinstance(d["institution_type"], str) else d["institution_type"]
            capacity = d.get("capacity") or 0
            enrolled = d.get("enrolled") or 0
            d["utilisation_pct"] = round((enrolled / capacity) * 100, 1) if capacity else 0.0
            items.append(d)

        return {"items": items, "total": total_count or 0}

    except SQLAlchemyError as exc:
        logger.error("DB error in get_all_institutions_list: %s", exc, exc_info=True)
        raise DatabaseError("Unable to fetch institutions list") from exc


# ── Block / Unblock institution ───────────────────────────────────────────────

async def toggle_institution_block(
    db: AsyncSession,
    tenant_id: str,
) -> dict[str, Any]:
    """Toggle is_block for an institution. Returns the new state."""
    try:
        inst = await db.scalar(
            select(InstitutionDB).where(InstitutionDB.tenant_id == tenant_id)
        )
        if inst is None:
            raise InstitutionNotFoundError(f"Institution '{tenant_id}' not found")

        inst.is_block = not inst.is_block
        await db.commit()
        await db.refresh(inst)
        return {
            "tenant_id": tenant_id,
            "is_block": inst.is_block,
            "message": f"Institution {'blocked' if inst.is_block else 'unblocked'} successfully",
        }

    except InstitutionNotFoundError:
        raise
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("DB error toggling block for %s: %s", tenant_id, exc, exc_info=True)
        raise DatabaseError("Unable to update institution block status") from exc


# ── Master aggregator ─────────────────────────────────────────────────────────

async def get_super_admin_dashboard(db: AsyncSession) -> dict[str, Any]:
    institution_stats  = await get_institution_stats(db)
    user_stats         = await get_user_stats(db)
    class_stats        = await get_class_stats(db)
    platform_usage     = await get_platform_usage_stats(db)
    institutions_list  = await get_all_institutions_list(db)

    return {
        "generated_at": _now().isoformat(),
        "institutions": institution_stats,
        "users": user_stats,
        "classes": class_stats,
        "platform_usage": platform_usage,
        "institutions_list": institutions_list,
    }