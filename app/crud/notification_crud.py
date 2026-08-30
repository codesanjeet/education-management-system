# TODO (fix before scale-out):
# 1. mark_notification_as_read → replace with pg_insert + on_conflict_do_nothing
# 2. _NotifCarrier → replace with explicit kwargs
# 3. datetime.utcnow() → datetime.now(timezone.utc)  [Python 3.12 deprecation]
# 4. partial-send race in _check_and_deduct_email_credits (safe for now, single worker only)
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

import anyio
import bleach
import jwt
from fastapi import BackgroundTasks
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from ..core.database import AsyncSessionLocal
from ..core.exceptions import (
    DatabaseError,
    FileTooLargeError,
    InstitutionNotFoundError,
    InvalidFileTypeError,
    UserNotFoundException,
)
from ..core.storage import R2StorageError, r2          
from ..models.institution_model import InstitutionDB, InstitutionUsageDB
from ..models.notification_model import NotificationReadDB, NotificationsDB, WhatsAppConfigDB
from ..models.role_specific.student_model import StudentDB
from ..models.user_model import UserDB
from ..schemas.institution_schema import (
    CreateNotificationData,
    DeleteNotificationResponse,
    NotificationListResponse,
    NotificationReadResponse,
    NotificationResponse,
    UpdateNotificationData,
    WhatsAppConfigCreate,
)
from ..services.email import send_notification_email

import os
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── JWT secret (notification-specific — separate from auth JWT) ───────────────
_EMAIL_TOKEN_SECRET = os.getenv("NOTIFICATION_EMAIL_TOKEN_SECRET")
if not _EMAIL_TOKEN_SECRET:
    raise RuntimeError(
        "NOTIFICATION_EMAIL_TOKEN_SECRET env var is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# ── Timing constants ──────────────────────────────────────────────────────────
PORTAL_SIGNED_URL_SECONDS = 3_600      # 1 hour  — portal auth-gated links
EMAIL_TOKEN_TTL_SECONDS   = 604_800    # 7 days  — email download links

# ── Notification domain constants ─────────────────────────────────────────────
PRIVATE_NOTIFICATION_TYPES = {"academic", "alert"}

# ── File limits ───────────────────────────────────────────────────────────────
MAX_IMAGE_SIZE    = 10 * 1024 * 1024   # 10 MB
MAX_DOCUMENT_SIZE = 25 * 1024 * 1024   # 25 MB

# ── MIME / extension allow-lists ──────────────────────────────────────────────
ALLOWED_MIME_TYPES: set[str] = {
    "image/jpeg", "image/png", "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel", "text/csv",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint", "text/plain",
}
IMAGE_MIME_TYPES: set[str] = {"image/jpeg", "image/png"}
ALLOWED_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".pdf", ".xlsx", ".xls",
    ".csv", ".docx", ".doc", ".pptx", ".ppt", ".txt",
}

_GENERIC_CONTAINERS: set[str] = {
    "application/zip",
    "application/octet-stream",
    "application/x-zip-compressed",
}

_EXT_TO_MIME: dict[str, str] = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc":  "application/msword",
    ".xls":  "application/vnd.ms-excel",
    ".ppt":  "application/vnd.ms-powerpoint",
    ".csv":  "text/csv",
    ".txt":  "text/plain",
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
}

# ── Audience / role mappings ──────────────────────────────────────────────────
PARENT_INCLUSIVE_AUDIENCES = {"students", "all"}
AUDIENCE_TO_ROLES: dict[str, list[str]] = {
    "all":          ["admin", "principal", "teacher", "other_staff", "student"],
    "students":     ["student"],
    "teachers":     ["teacher"],
    "admins":       ["admin"],
    "all_staffs":   ["admin", "principal", "teacher", "other_staff"],
    "other_staffs": ["other_staff"],
    "principals":   ["principal"],
    "parents":      [],
}

ROLE_LABELS: dict[str, str] = {
    "admin":       "Administrator",
    "principal":   "Principal",
    "teacher":     "Teacher",
    "other_staff": "Staff Member",
    "student":     "Student",
    "parent":      "Parent / Guardian",
}

# ── HTML / template token config ──────────────────────────────────────────────
_TOKEN_RE = re.compile(r"\{\{(\w+)\}\}")

ALLOWED_TAGS = [
    "p", "br", "strong", "em", "u", "ul", "ol", "li",
    "a", "h1", "h2", "h3", "span", "div",
]
ALLOWED_ATTRS = {"a": ["href", "target"]}


# ══════════════════════════════════════════════════════════════════════════════
# JWT-based email download tokens
# ══════════════════════════════════════════════════════════════════════════════

def generate_email_download_token(
    notif_id: int,
    tenant_id: str,
    ttl: int = EMAIL_TOKEN_TTL_SECONDS,
) -> str:
    """Return a signed JWT usable as a 7-day email download link."""
    now = int(time.time())
    return jwt.encode(
        {"nid": notif_id, "tid": tenant_id, "exp": now + ttl, "iat": now},
        _EMAIL_TOKEN_SECRET,
        algorithm="HS256",
    )


def verify_email_download_token(token: str) -> dict | None:
    """
    Verify and decode a JWT email download token.
    Returns the payload dict on success, None if expired or invalid.
    Never raises — callers treat None as invalid/expired.
    """
    try:
        return jwt.decode(
            token,
            _EMAIL_TOKEN_SECRET,
            algorithms=["HS256"],
            options={"require": ["exp", "iat", "nid", "tid"]},
        )
    except jwt.ExpiredSignatureError:
        logger.info("[EMAIL TOKEN] expired token presented")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning(f"[EMAIL TOKEN] invalid token: {exc}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# HTML sanitisation / template interpolation helpers
# ══════════════════════════════════════════════════════════════════════════════

def _sanitize_tokens(html: str) -> str:
    """
    1. Decode HTML-entity-mangled {{ }} that rich-text editors produce.
    2. Strip any HTML tags injected inside a {{token}} by the editor.
    3. Normalise whitespace inside tokens: {{ first_name }} → {{first_name}}.
    4. Run bleach to strip disallowed tags/attrs.
    """
    result = html
    result = result.replace("&#123;", "{").replace("&#125;", "}")
    result = result.replace("&lbrace;", "{").replace("&rbrace;", "}")
    result = result.replace("&#x7B;", "{").replace("&#x7D;", "}")
    result = re.sub(
        r"\{\{[^}]*\}\}",
        lambda m: re.sub(r"<[^>]+>", "", m.group(0)),
        result,
    )
    result = re.sub(
        r"\{\{\s*(\w+)\s*\}\}",
        lambda m: "{{" + m.group(1) + "}}",
        result,
    )
    return bleach.clean(result, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)


def _interpolate(text: str, ctx: dict[str, str]) -> str:
    """Replace {{tokens}} per-recipient. Unknown tokens left untouched."""
    return _TOKEN_RE.sub(lambda m: ctx.get(m.group(1), m.group(0)), text)


def _build_ctx(
    first_name: str,
    last_name: str,
    role: str,
    institution_name: str,
) -> dict[str, str]:
    fn   = (first_name or "").strip()
    ln   = (last_name  or "").strip()
    full = f"{fn} {ln}".strip() or "there"
    return {
        "full_name":   full,
        "first_name":  fn,
        "last_name":   ln,
        "role":        ROLE_LABELS.get(role, role.replace("_", " ").title()) if role else "Member",
        "institution": (institution_name or "").strip(),
        "today_date":  datetime.utcnow().strftime("%B %d, %Y"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Notification-type / bucket helpers
# ══════════════════════════════════════════════════════════════════════════════

def is_private_type(notification_type: str) -> bool:
    return notification_type.lower() in PRIVATE_NOTIFICATION_TYPES


# ══════════════════════════════════════════════════════════════════════════════
# File validation
# (R2 config lives in storage.py; validation logic stays here)
# ══════════════════════════════════════════════════════════════════════════════

def _get_mime_sync(content: bytes) -> str:
    import magic
    try:
        return magic.Magic(mime=True).from_buffer(content)
    except Exception:
        raise InvalidFileTypeError("Cannot detect file type")


def _check_image_sync(content: bytes) -> None:
    from PIL import Image
    try:
        img = Image.open(BytesIO(content))
        img.verify()
        img = Image.open(BytesIO(content))
        if img.size[0] * img.size[1] > 89_478_485:
            raise InvalidFileTypeError("Image dimensions too large")
    except Image.DecompressionBombError:
        raise InvalidFileTypeError("Image too large")
    except InvalidFileTypeError:
        raise
    except Exception:
        raise InvalidFileTypeError("Invalid image file")


def _norm_mime(m: str) -> str:
    m = m.lower().strip()
    if "spreadsheet"    in m: return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if "wordprocessing" in m: return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if "presentation"   in m: return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return m


async def validate_file(filename: str, content: bytes) -> Tuple[str, int]:
    """
    Full validation pipeline. Returns (normalised_mime, file_size_bytes).
    Raises InvalidFileTypeError or FileTooLargeError on failure.
    All blocking work runs in anyio thread pools.
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(f"Extension '{ext}' not allowed")

    size = len(content)
    mime = await anyio.to_thread.run_sync(lambda: _get_mime_sync(content))
    norm = _norm_mime(mime)

    if norm in _GENERIC_CONTAINERS or norm not in ALLOWED_MIME_TYPES:
        norm = _EXT_TO_MIME.get(ext, norm)

    if norm not in ALLOWED_MIME_TYPES:
        raise InvalidFileTypeError(f"File type '{mime}' not allowed")

    if norm in IMAGE_MIME_TYPES:
        if size > MAX_IMAGE_SIZE:
            raise FileTooLargeError(f"Image too large (max {MAX_IMAGE_SIZE // (1024*1024)} MB)")
        await anyio.to_thread.run_sync(lambda: _check_image_sync(content))
    else:
        if size > MAX_DOCUMENT_SIZE:
            raise FileTooLargeError(f"Document too large (max {MAX_DOCUMENT_SIZE // (1024*1024)} MB)")

    return norm, size


# ══════════════════════════════════════════════════════════════════════════════
# Public file-handling API (called from routers)
# ══════════════════════════════════════════════════════════════════════════════

async def save_uploaded_file(
    filename: str,
    file_content: bytes,
    tenant_id: str,
    institution_id: int,
    db: AsyncSession,
    notification_type: str = "official",
) -> Tuple[str, str, int]:
    """
    Validate → upload to R2 → update storage accounting.
    Returns (r2_key, mime, size_bytes).
    """
    try:
        mime, size = await validate_file(filename, file_content)
        private    = is_private_type(notification_type)
        key        = r2.build_key(tenant_id, "notifications", filename)
        await r2.upload(key, file_content, mime, is_private=private)
        await _update_storage_usage(db, institution_id, size)
        return key, mime, size
    except (InvalidFileTypeError, FileTooLargeError):
        raise
    except R2StorageError as exc:
        logger.error(f"[R2] upload failed in save_uploaded_file: {exc}")
        raise DatabaseError("Failed to upload file to storage")
    except Exception as exc:
        logger.error(f"save_uploaded_file: {exc}", exc_info=True)
        raise DatabaseError("Failed to save file")


async def get_file_url_for_download(
    tenant_id: str,
    notification_id: int,
    db: AsyncSession,
) -> str:
    """Return the correct URL (presigned or CDN) for a notification attachment."""
    row = (await db.execute(
        select(NotificationsDB.attached_file, NotificationsDB.type).where(
            NotificationsDB.tenant_id == tenant_id,
            NotificationsDB.id        == notification_id,
        )
    )).one_or_none()

    if not row or not row[0]:
        raise UserNotFoundException("File not found")

    key, notif_type = row
    try:
        return await r2.url_for(key, is_private=is_private_type(notif_type),
                                expires=PORTAL_SIGNED_URL_SECONDS)
    except R2StorageError as exc:
        logger.error(f"[R2] url_for failed for notification {notification_id}: {exc}")
        raise DatabaseError("Could not generate file download URL")


def get_file_upload_info() -> dict:
    return {
        "allowed_extensions": list(ALLOWED_EXTENSIONS),
        "allowed_mime_types": list(ALLOWED_MIME_TYPES),
        "max_sizes": {
            "images":    f"{MAX_IMAGE_SIZE    // (1024 * 1024)} MB",
            "documents": f"{MAX_DOCUMENT_SIZE // (1024 * 1024)} MB",
        },
        "storage": {
            "private_types": list(PRIVATE_NOTIFICATION_TYPES),
            "note": "Private types use auth-gated portal URLs. All others use permanent CDN URLs.",
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# Usage / credit accounting
# ══════════════════════════════════════════════════════════════════════════════

async def _update_storage_usage(
    db: AsyncSession, institution_id: int, delta_bytes: int
) -> None:
    """
    Best-effort storage accounting. Failures are logged but never raised —
    drift is corrected by the nightly reconciliation job.
    """
    try:
        await db.execute(
            update(InstitutionUsageDB)
            .where(InstitutionUsageDB.institution_id == institution_id)
            .values(
                storage_used_mb=InstitutionUsageDB.storage_used_mb
                + (delta_bytes / (1024 * 1024))
            )
        )
        # Clamp to zero — avoids negative values on delete
        await db.execute(
            update(InstitutionUsageDB)
            .where(
                InstitutionUsageDB.institution_id  == institution_id,
                InstitutionUsageDB.storage_used_mb <  0,
            )
            .values(storage_used_mb=0.0)
        )
        await db.commit()
    except Exception as exc:
        logger.warning(f"[STORAGE] update failed for inst {institution_id}: {exc}")
        await db.rollback()


async def _check_and_deduct_email_credits(
    db: AsyncSession, institution_id: int, count: int
) -> int:
    """
    Atomically deduct up to `count` email credits.
    Returns credits actually deducted (0 if balance insufficient).
    Uses WHERE-guard UPDATE to eliminate the TOCTOU race condition.
    """
    try:
        # Attempt full deduct first
        result = await db.execute(
            update(InstitutionUsageDB)
            .where(
                InstitutionUsageDB.institution_id == institution_id,
                InstitutionUsageDB.email_balance  >= count,
            )
            .values(email_balance=InstitutionUsageDB.email_balance - count)
            .returning(InstitutionUsageDB.email_balance)
        )
        if result.one_or_none() is not None:
            await db.commit()
            return count

        # Full deduct failed — partial: read current balance, deduct whatever remains
        bal_row = await db.execute(
            select(InstitutionUsageDB.email_balance).where(
                InstitutionUsageDB.institution_id == institution_id
            )
        )
        current = bal_row.scalar_one_or_none() or 0
        if current <= 0:
            return 0
        allowed = min(count, current)
        await db.execute(
            update(InstitutionUsageDB)
            .where(InstitutionUsageDB.institution_id == institution_id)
            .values(email_balance=InstitutionUsageDB.email_balance - allowed)
        )
        await db.commit()
        logger.warning(
            f"[CREDITS] partial send: {allowed}/{count} credits for inst {institution_id}"
        )
        return allowed
    except Exception as exc:
        logger.warning(f"[CREDITS] deduct failed for inst {institution_id}: {exc}")
        await db.rollback()
        return 0


async def get_usage_info(db: AsyncSession, institution_id: int) -> dict:
    try:
        r = await db.execute(
            select(InstitutionUsageDB).where(
                InstitutionUsageDB.institution_id == institution_id
            )
        )
        u = r.scalar_one_or_none()
        if u:
            return {
                "email_balance":      u.email_balance      or 0,
                "storage_used_mb":    round(u.storage_used_mb or 0, 2),
                "ai_credits_balance": u.ai_credits_balance  or 0,
            }
    except Exception as exc:
        logger.warning(f"[USAGE] fetch failed for inst {institution_id}: {exc}")
    return {"email_balance": 0, "storage_used_mb": 0.0, "ai_credits_balance": 0}


# ══════════════════════════════════════════════════════════════════════════════
# Institution info
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_institution_info(tenant_id: str, db: AsyncSession) -> dict:
    row = (await db.execute(
        select(
            InstitutionDB.id, InstitutionDB.institute_name,
            InstitutionDB.address, InstitutionDB.city,
            InstitutionDB.state, InstitutionDB.logo,
        ).where(InstitutionDB.tenant_id == tenant_id)
    )).one_or_none()

    if not row:
        return {"id": None, "name": "School Portal", "address": "", "logo_url": None}

    inst_id, name, address, city, state, logo = row
    parts = [p for p in [address, city, state] if p]

    # Logo stored as a raw key or a full URL
    if logo:
        logo_url = logo if logo.startswith("http") else r2.public_url(logo.lstrip("/"))
    else:
        logo_url = None

    return {"id": inst_id, "name": name, "address": ", ".join(parts), "logo_url": logo_url}


# ══════════════════════════════════════════════════════════════════════════════
# Recipient fetching
# ══════════════════════════════════════════════════════════════════════════════

async def _fetch_recipients_with_data(
    tenant_id: str,
    audience: str,
    class_id: int | None,
    db: AsyncSession,
    include_parents: bool = False,
) -> list[dict]:
    recipients: dict[str, dict] = {}

    roles = AUDIENCE_TO_ROLES.get(audience, [])
    if roles:
        stmt = select(
            UserDB.email, UserDB.first_name, UserDB.last_name, UserDB.role,
        ).where(
            UserDB.tenant_id == tenant_id,
            UserDB.role.in_(roles),
            UserDB.is_active == True,  # noqa: E712
        )
        if class_id and audience == "students":
            stmt = stmt.where(UserDB.class_id == class_id)
        for email, fn, ln, role in (await db.execute(stmt)).fetchall():
            if email:
                recipients[email] = {
                    "email": email, "first_name": fn or "",
                    "last_name": ln or "", "role": role or "",
                }

    needs_parents = (
        include_parents and audience in PARENT_INCLUSIVE_AUDIENCES
    ) or audience == "parents"

    if needs_parents:
        try:
            ps = select(StudentDB.parent_email).where(
                StudentDB.tenant_id    == tenant_id,
                StudentDB.parent_email.isnot(None),
                StudentDB.parent_email != "",
            )
            if class_id:
                ps = ps.where(StudentDB.class_id == class_id)
            for (email,) in (await db.execute(ps)).fetchall():
                if email and email not in recipients:
                    recipients[email] = {
                        "email": email, "first_name": "",
                        "last_name": "", "role": "parent",
                    }
        except Exception as exc:
            logger.warning(f"Could not fetch parent emails: {exc}")

    return list(recipients.values())


# ══════════════════════════════════════════════════════════════════════════════
# Email dispatch
# ══════════════════════════════════════════════════════════════════════════════

def _build_portal_file_url(base_url: str, notification_id: int) -> str:
    return f"{base_url.rstrip('/')}/notifications/{notification_id}/download"


async def _dispatch_emails_async(
    recipients: list[dict],
    title: str,
    message: str,
    institution_name: str,
    institution_address: str,
    institution_logo_url: str | None,
    file_url: str | None,
    file_fallback_url: str | None = None,
    batch_size: int = 50,
    concurrency: int = 10,
) -> tuple[int, int]:
    """
    Async email dispatch with:
    - Per-recipient token interpolation
    - Bounded concurrency via semaphore (default: 10 concurrent sends)
    - Batched processing to keep memory flat for large recipient lists
    - Individual error isolation — one failure never kills the batch
    """
    import asyncio

    sent = failed = 0
    clean_message = _sanitize_tokens(message)
    sem = asyncio.Semaphore(concurrency)

    async def send_one(rec: dict) -> bool:
        async with sem:
            ctx       = _build_ctx(rec.get("first_name", ""), rec.get("last_name", ""),
                                   rec.get("role", ""), institution_name)
            p_title   = _interpolate(title,         ctx)
            p_message = _interpolate(clean_message, ctx)
            try:
                res = await anyio.to_thread.run_sync(
                    lambda: send_notification_email(
                        to=rec["email"],
                        title=p_title,
                        message=p_message,
                        institution_name=institution_name,
                        institution_address=institution_address,
                        institution_logo=institution_logo_url,
                        file_download_url=file_url,
                        file_fallback_url=file_fallback_url,
                    )
                )
                return bool(res.get("success"))
            except Exception as exc:
                logger.error(f"[EMAIL] exception for {rec['email']}: {exc}", exc_info=True)
                return False

    for i in range(0, len(recipients), batch_size):
        batch   = recipients[i : i + batch_size]
        results = await asyncio.gather(*[send_one(r) for r in batch])
        bs = sum(1 for ok in results if ok)
        bf = sum(1 for ok in results if not ok)
        sent   += bs
        failed += bf
        logger.info(
            f"[EMAIL] batch {i // batch_size + 1}: "
            f"{bs} sent, {bf} failed (running total: {sent}/{sent+failed})"
        )

    logger.info(
        f"[EMAIL] '{title}' → {sent} sent, {failed} failed "
        f"out of {len(recipients)} recipients."
    )
    return sent, failed


# ══════════════════════════════════════════════════════════════════════════════
# CRUD — Create
# ══════════════════════════════════════════════════════════════════════════════

async def create_notification(
    db: AsyncSession,
    tenant_id: str,
    notification_data: CreateNotificationData,
    current_user_id: int,
    background_tasks: BackgroundTasks = None,
    portal_base_url: str = "",
) -> NotificationResponse:

    inst_id = (await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not inst_id:
        raise InstitutionNotFoundError("Institution not found")

    try:
        notif = NotificationsDB(
            institution_id = inst_id,
            tenant_id      = tenant_id,
            type           = notification_data.type,
            audience       = notification_data.audience,
            class_id       = notification_data.class_id,
            title          = notification_data.title,
            message        = _sanitize_tokens(notification_data.message),
            attached_file  = notification_data.attached_file,
            created_by     = current_user_id,
            created_at     = datetime.utcnow(),
        )
        db.add(notif)
        await db.commit()
        await db.refresh(notif)
    except Exception as exc:
        await db.rollback()
        if notification_data.attached_file:
            await r2.delete(
                notification_data.attached_file,
                is_private=is_private_type(notification_data.type),
            )
        logger.error(f"Error creating notification: {exc}", exc_info=True)
        raise DatabaseError("Unable to create notification")

    response = NotificationResponse.model_validate(notif, from_attributes=True)

    if getattr(notification_data, "send_email", False):
        _dispatch = _send_notification_emails
        kwargs = dict(
            tenant_id=tenant_id, notif_id=notif.id,
            notification_data=notification_data,
            notif_message=notif.message, portal_base_url=portal_base_url,
        )
        if background_tasks:
            background_tasks.add_task(_dispatch, **kwargs)
        else:
            await _dispatch(**kwargs)

    if getattr(notification_data, "send_whatsapp", False):
        logger.info(
            f"[WHATSAPP STUB] '{notification_data.title}' | "
            f"audience={notification_data.audience} | "
            f"target={getattr(notification_data, 'whatsapp_target', 'both')}"
        )

    return response


# ── Background email sender ───────────────────────────────────────────────────

async def _send_notification_emails(
    tenant_id: str,
    notif_id: int,
    notification_data,
    notif_message: str,
    portal_base_url: str,
) -> None:
    """
    Always opens its own DB session — the request-scoped session is already
    closed by the time a BackgroundTask runs.
    """
    async with AsyncSessionLocal() as db:
        try:
            institution = await _fetch_institution_info(tenant_id, db)
            inst_id     = institution["id"]
            if not inst_id:
                logger.warning(f"[EMAIL] institution not found for tenant {tenant_id}")
                return

            include_parents = getattr(notification_data, "include_parents", False)
            audience_str    = str(
                notification_data.audience.value
                if hasattr(notification_data.audience, "value")
                else notification_data.audience
            )

            recipients = await _fetch_recipients_with_data(
                tenant_id=tenant_id, audience=audience_str,
                class_id=getattr(notification_data, "class_id", None),
                db=db, include_parents=include_parents,
            )

            if not recipients:
                logger.warning(
                    f"[EMAIL] no recipients for audience='{audience_str}' tenant='{tenant_id}'"
                )
                return

            # Hard cap — never send more than 5000 in one shot
            if len(recipients) > 5000:
                logger.warning(
                    f"[EMAIL] recipient list capped at 5000 (was {len(recipients)}) "
                    f"for notif {notif_id}"
                )
                recipients = recipients[:5000]

            allowed = await _check_and_deduct_email_credits(db, inst_id, len(recipients))
            if allowed == 0:
                logger.warning(f"[EMAIL] no credits for inst {inst_id}, notif {notif_id}")
                return
            if allowed < len(recipients):
                logger.warning(
                    f"[EMAIL] partial send: {allowed}/{len(recipients)} for notif {notif_id}"
                )

            file_email_url = file_fallback_url = None
            if getattr(notification_data, "attached_file", None):
                token          = generate_email_download_token(notif_id, tenant_id)
                file_email_url = (
                    f"{portal_base_url.rstrip('/')}/api/institutions/notifications"
                    f"/{notif_id}/file/email-download?token={token}"
                )
                file_fallback_url = _build_portal_file_url(portal_base_url, notif_id)

            await _dispatch_emails_async(
                recipients=recipients[:allowed],
                title=getattr(notification_data, "title", ""),
                message=notif_message,
                institution_name=institution["name"],
                institution_address=institution["address"],
                institution_logo_url=institution["logo_url"],
                file_url=file_email_url,
                file_fallback_url=file_fallback_url,
            )

        except Exception as exc:
            logger.error(
                f"[EMAIL][BACKGROUND] failed for notif {notif_id}: {exc}", exc_info=True
            )


# ══════════════════════════════════════════════════════════════════════════════
# CRUD — Update
# ══════════════════════════════════════════════════════════════════════════════

async def update_notification(
    tenant_id: str,
    db: AsyncSession,
    notification_id: int,
    notification_data: UpdateNotificationData,
    send_email: bool = False,
    send_whatsapp: bool = False,
    include_parents: bool = False,
    whatsapp_target: str = "both",
    portal_base_url: str = "",
    background_tasks: BackgroundTasks = None,
) -> NotificationResponse:

    notif = (await db.execute(
        select(NotificationsDB).where(
            NotificationsDB.id        == notification_id,
            NotificationsDB.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if not notif:
        raise UserNotFoundException(f"Notification {notification_id} not found")

    old_file = notif.attached_file
    old_type = notif.type
    _SKIP    = {"send_email", "send_whatsapp", "include_parents", "whatsapp_target"}

    try:
        for k, v in notification_data.model_dump(exclude_unset=True).items():
            if k not in _SKIP:
                if k == "message" and v:
                    v = _sanitize_tokens(v)
                setattr(notif, k, v)
        await db.commit()
        await db.refresh(notif)
        # Clean up the replaced file from R2 (best-effort — never raises)
        if old_file and notification_data.attached_file and old_file != notification_data.attached_file:
            await r2.delete(old_file, is_private=is_private_type(old_type))
    except Exception as exc:
        await db.rollback()
        # Clean up the newly uploaded file that we can't attach now
        if notification_data.attached_file and notification_data.attached_file != old_file:
            await r2.delete(
                notification_data.attached_file,
                is_private=is_private_type(notification_data.type or old_type),
            )
        logger.error(f"Error updating notification: {exc}", exc_info=True)
        raise DatabaseError("Unable to update notification")

    response = NotificationResponse.model_validate(notif, from_attributes=True)

    if send_email:
        class _NotifCarrier:
            def __init__(self, n, ip):
                self.audience        = n.audience
                self.class_id        = n.class_id
                self.title           = n.title
                self.attached_file   = n.attached_file
                self.include_parents = ip

        carrier = _NotifCarrier(notif, include_parents)
        kwargs  = dict(
            tenant_id=tenant_id, notif_id=notif.id,
            notification_data=carrier,
            notif_message=notif.message, portal_base_url=portal_base_url,
        )
        if background_tasks:
            background_tasks.add_task(_send_notification_emails, **kwargs)
        else:
            await _send_notification_emails(**kwargs)

    if send_whatsapp:
        logger.info(f"[WHATSAPP STUB][UPDATE] '{notif.title}' | audience={notif.audience}")

    return response


# ══════════════════════════════════════════════════════════════════════════════
# CRUD — Mark as read
# ══════════════════════════════════════════════════════════════════════════════

async def mark_notification_as_read(
    tenant_id: str, db: AsyncSession,
    notification_ids: list[int], user_id: int,
):
    try:
        already_read = set(
            (await db.execute(
                select(NotificationReadDB.notification_id).where(
                    NotificationReadDB.tenant_id       == tenant_id,
                    NotificationReadDB.user_id         == user_id,
                    NotificationReadDB.notification_id.in_(notification_ids),
                )
            )).scalars().all()
        )
        for nid in notification_ids:
            if nid not in already_read:
                db.add(NotificationReadDB(
                    tenant_id=tenant_id, user_id=user_id,
                    notification_id=nid, read_at=datetime.utcnow(),
                ))
        await db.commit()
        return {"message": "Notifications marked as read"}
    except Exception as exc:
        await db.rollback()
        raise DatabaseError(f"Unable to update notification: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# CRUD — Delete
# ══════════════════════════════════════════════════════════════════════════════

async def delete_notification(
    tenant_id: str, notification_id: int, db: AsyncSession,
) -> DeleteNotificationResponse:

    notif = (await db.execute(
        select(NotificationsDB).where(
            NotificationsDB.id        == notification_id,
            NotificationsDB.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    if not notif:
        raise UserNotFoundException(f"Notification {notification_id} not found")

    attached   = notif.attached_file
    notif_type = str(notif.type.value if hasattr(notif.type, "value") else notif.type)
    private    = is_private_type(notif_type)

    inst_id = (await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )).scalar_one_or_none()

    # Read file size before deleting the record (for storage accounting)
    fsize = 0
    if attached:
        fsize = await r2.size(attached, is_private=private)

    try:
        await db.delete(notif)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"Error deleting notification: {exc}", exc_info=True)
        raise DatabaseError("Unable to delete notification")

    # Best-effort R2 + storage accounting cleanup after DB record is gone
    if attached:
        await r2.delete(attached, is_private=private)
        if inst_id and fsize:
            await _update_storage_usage(db, inst_id, -fsize)

    return DeleteNotificationResponse(
        success=True,
        message="Notification deleted successfully",
        deleted_notification_id=notification_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# CRUD — Read helpers
# ══════════════════════════════════════════════════════════════════════════════

async def get_notification_by_id(
    notification_id: int, tenant_id: str, db: AsyncSession,
) -> Optional[NotificationResponse]:
    n = (await db.execute(
        select(NotificationsDB).where(
            NotificationsDB.id        == notification_id,
            NotificationsDB.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    return NotificationResponse.model_validate(n, from_attributes=True) if n else None


async def get_all_notification_reads(
    tenant_id: str, user_id: int,
    notification_ids: list[int], db: AsyncSession,
) -> list[NotificationReadResponse]:
    rows = (await db.execute(
        select(NotificationReadDB).where(
            NotificationReadDB.notification_id.in_(notification_ids),
            NotificationReadDB.user_id   == user_id,
            NotificationReadDB.tenant_id == tenant_id,
        )
    )).scalars().all()
    return [NotificationReadResponse.model_validate(x) for x in rows]


async def get_all_notifications(
    tenant_id: str, db: AsyncSession,
    skip: int = 0, limit: int = 100,
    audience_filter: Optional[str] = None,
    type_filter: Optional[str] = None,
) -> NotificationListResponse:
    base = select(NotificationsDB).where(NotificationsDB.tenant_id == tenant_id)
    if audience_filter:
        base = base.where(NotificationsDB.audience == audience_filter)
    if type_filter:
        base = base.where(NotificationsDB.type == type_filter)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    rows  = (await db.execute(
        base.order_by(NotificationsDB.created_at.desc()).offset(skip).limit(limit)
    )).scalars().all()

    items       = [NotificationResponse.model_validate(n, from_attributes=True) for n in rows]
    page        = (skip // limit) + 1 if limit > 0 else 1
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    return NotificationListResponse(
        notifications=items, total=total, page=page,
        page_size=limit, total_pages=total_pages,
    )


async def get_notifications_by_audience(
    tenant_id: str, audience: str, db: AsyncSession, limit: int = 50,
) -> list[NotificationResponse]:
    rows = (await db.execute(
        select(NotificationsDB)
        .where(
            NotificationsDB.tenant_id == tenant_id,
            NotificationsDB.audience  == audience,
        )
        .order_by(NotificationsDB.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [NotificationResponse.model_validate(n, from_attributes=True) for n in rows]


async def stream_notification_file(
    tenant_id: str,
    notification_id: int,
    db: AsyncSession,
) -> tuple[str, str, str, int | None]:
    """
    Return (url, content_type, filename, file_size) for streaming a notification
    attachment. Private files get a presigned URL; public files get a CDN URL.
    """
    row = (await db.execute(
        select(NotificationsDB.attached_file, NotificationsDB.type).where(
            NotificationsDB.tenant_id == tenant_id,
            NotificationsDB.id        == notification_id,
        )
    )).one_or_none()

    if not row or not row[0]:
        raise UserNotFoundException("File not found")

    key, notif_type = row
    filename        = key.split("/")[-1] or "download"
    private         = is_private_type(notif_type)

    try:
        url = await r2.url_for(key, is_private=private, expires=PORTAL_SIGNED_URL_SECONDS)
    except R2StorageError as exc:
        logger.error(f"[R2] url_for failed for notification {notification_id}: {exc}")
        raise DatabaseError("Could not generate file URL")

    meta         = await r2.head(key, is_private=private)
    content_type = meta.get("content_type", "application/octet-stream")
    file_size    = meta.get("size") or None   # 0 → None so callers can distinguish

    return url, content_type, filename, file_size


# ══════════════════════════════════════════════════════════════════════════════
# WhatsApp config CRUD
# ══════════════════════════════════════════════════════════════════════════════

async def create_whatsapp_config(
    db: AsyncSession,
    institution_id: int,
    tenant_id: str,
    data: WhatsAppConfigCreate,
) -> WhatsAppConfigDB:
    """Deactivate any existing active config, then create a new one."""
    try:
        await db.execute(
            update(WhatsAppConfigDB)
            .where(
                WhatsAppConfigDB.institution_id == institution_id,
                WhatsAppConfigDB.is_active      == True,  # noqa: E712
            )
            .values(is_active=False)
        )
        new_config = WhatsAppConfigDB(
            tenant_id=tenant_id,
            institution_id=institution_id,
            provider=data.provider.value,
            phone_number=data.phone_number,
            config=data.config,
            webhook_url=data.webhook_url,
            is_active=True,
            status="pending",
        )
        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)
        return new_config
    except IntegrityError:
        await db.rollback()
        raise DatabaseError("WhatsApp config already exists for this institution.")
    except Exception as exc:
        await db.rollback()
        logger.error("create_whatsapp_config error", exc_info=True)
        raise DatabaseError("Failed to create WhatsApp config")











# async def get_active_wa_config(
#     db: AsyncSession, institution_id: int
# ) -> Optional[WhatsAppConfigDB]:
#     result = await db.execute(
#         select(WhatsAppConfigDB).where(
#             WhatsAppConfigDB.institution_id == institution_id,
#             WhatsAppConfigDB.is_active == True,
#         )
#     )
#     return result.scalar_one_or_none()


# async def get_wa_config_by_id(
#     db: AsyncSession, config_id: int, institution_id: int
# ) -> WhatsAppConfigDB:
#     result = await db.execute(
#         select(WhatsAppConfigDB).where(
#             WhatsAppConfigDB.id == config_id,
#             WhatsAppConfigDB.institution_id == institution_id,
#         )
#     )
#     config = result.scalar_one_or_none()
#     if not config:
#         raise WhatsAppConfigNotFound(f"WhatsApp config {config_id} not found.")
#     return config


# async def update_whatsapp_config(
#     db: AsyncSession, config_id: int, institution_id: int, data: WhatsAppConfigUpdate,
# ) -> WhatsAppConfigDB:
#     config = await get_wa_config_by_id(db, config_id, institution_id)
#     try:
#         if data.phone_number is not None: config.phone_number = data.phone_number
#         if data.config       is not None: config.config       = data.config
#         if data.webhook_url  is not None: config.webhook_url  = data.webhook_url
#         if data.is_active    is not None: config.is_active    = data.is_active
#         config.updated_at = datetime.utcnow()
#         config.status     = "pending"
#         config.last_error = None
#         await db.commit()
#         await db.refresh(config)
#         return config
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"update_whatsapp_config error: {e}", exc_info=True)
#         raise DatabaseError("Failed to update WhatsApp config")


# async def set_wa_config_status(
#     db: AsyncSession, config_id: int, status: str, last_error: Optional[str] = None,
# ) -> None:
#     try:
#         await db.execute(
#             update(WhatsAppConfigDB)
#             .where(WhatsAppConfigDB.id == config_id)
#             .values(status=status, last_error=last_error, updated_at=datetime.utcnow())
#         )
#         await db.commit()
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"set_wa_config_status error: {e}", exc_info=True)
#         raise DatabaseError("Failed to update WhatsApp config status")


# async def delete_whatsapp_config(
#     db: AsyncSession, config_id: int, institution_id: int
# ) -> None:
#     config = await get_wa_config_by_id(db, config_id, institution_id)
#     try:
#         await db.delete(config)
#         await db.commit()
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"delete_whatsapp_config error: {e}", exc_info=True)
#         raise DatabaseError("Failed to delete WhatsApp config")


# ══════════════════════════════════════════════════════════════
# EMAIL CONFIG CRUD
# ══════════════════════════════════════════════════════════════

# async def create_email_config(
#     db: AsyncSession,
#     institution_id: int,
#     tenant_id: str,
#     data: EmailConfigCreate,
# ) -> EmailConfigDB:
#     """Deactivate any existing active email config, then create new one."""
#     try:
#         await db.execute(
#             update(EmailConfigDB)
#             .where(
#                 EmailConfigDB.institution_id == institution_id,
#                 EmailConfigDB.is_active == True,
#             )
#             .values(is_active=False)
#         )
#         new_config = EmailConfigDB(
#             tenant_id=tenant_id,
#             institution_id=institution_id,
#             provider=data.provider.value,
#             from_email=data.from_email,
#             from_name=data.from_name,
#             reply_to=data.reply_to,
#             config=data.config,
#             is_active=True,
#             status="pending",
#         )
#         db.add(new_config)
#         await db.commit()
#         await db.refresh(new_config)
#         return new_config
#     except IntegrityError:
#         await db.rollback()
#         raise ConfigAlreadyExists("Email config already exists for this institution.")
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"create_email_config error: {e}", exc_info=True)
#         raise DatabaseError("Failed to create email config")


# async def get_active_email_config(
#     db: AsyncSession, institution_id: int
# ) -> Optional[EmailConfigDB]:
#     result = await db.execute(
#         select(EmailConfigDB).where(
#             EmailConfigDB.institution_id == institution_id,
#             EmailConfigDB.is_active == True,
#         )
#     )
#     return result.scalar_one_or_none()


# async def get_email_config_by_id(
#     db: AsyncSession, config_id: int, institution_id: int
# ) -> EmailConfigDB:
#     result = await db.execute(
#         select(EmailConfigDB).where(
#             EmailConfigDB.id == config_id,
#             EmailConfigDB.institution_id == institution_id,
#         )
#     )
#     config = result.scalar_one_or_none()
#     if not config:
#         raise EmailConfigNotFound(f"Email config {config_id} not found.")
#     return config


# async def update_email_config(
#     db: AsyncSession, config_id: int, institution_id: int, data: EmailConfigUpdate,
# ) -> EmailConfigDB:
#     config = await get_email_config_by_id(db, config_id, institution_id)
#     try:
#         if data.from_email is not None: config.from_email = data.from_email
#         if data.from_name  is not None: config.from_name  = data.from_name
#         if data.reply_to   is not None: config.reply_to   = data.reply_to
#         if data.config     is not None: config.config     = data.config
#         if data.is_active  is not None: config.is_active  = data.is_active
#         config.updated_at = datetime.utcnow()
#         config.status     = "pending"
#         config.last_error = None
#         await db.commit()
#         await db.refresh(config)
#         return config
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"update_email_config error: {e}", exc_info=True)
#         raise DatabaseError("Failed to update email config")


# async def set_email_config_status(
#     db: AsyncSession, config_id: int, status: str, last_error: Optional[str] = None,
# ) -> None:
#     try:
#         await db.execute(
#             update(EmailConfigDB)
#             .where(EmailConfigDB.id == config_id)
#             .values(status=status, last_error=last_error, updated_at=datetime.utcnow())
#         )
#         await db.commit()
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"set_email_config_status error: {e}", exc_info=True)
#         raise DatabaseError("Failed to update email config status")


# async def delete_email_config(
#     db: AsyncSession, config_id: int, institution_id: int
# ) -> None:
#     config = await get_email_config_by_id(db, config_id, institution_id)
#     try:
#         await db.delete(config)
#         await db.commit()
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"delete_email_config error: {e}", exc_info=True)
#         raise DatabaseError("Failed to delete email config")


# ══════════════════════════════════════════════════════════════
# AUTOMATION RULE CRUD  — channel-agnostic
# ══════════════════════════════════════════════════════════════

# async def create_rule(
#     db: AsyncSession, institution_id: int, data: AutomationRuleCreate,
# ) -> AutomationRuleDB:
#     try:
#         rule = AutomationRuleDB(
#             institution_id=institution_id,
#             name=data.name,
#             type=data.type.value,
#             enabled=data.enabled,
#             channels=[ch.value for ch in data.channels],
#             audience=data.audience,
#             channel_templates=data.channel_templates.model_dump(exclude_none=True),
#             schedule=data.schedule,
#             cron_expression=data.cron_expression,
#         )
#         db.add(rule)
#         await db.commit()
#         await db.refresh(rule)
#         return rule
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"create_rule error: {e}", exc_info=True)
#         raise DatabaseError("Failed to create automation rule")


# async def get_rules(
#     db: AsyncSession,
#     institution_id: int,
#     channel: Optional[str] = None,
# ) -> list[AutomationRuleDB]:
#     query = (
#         select(AutomationRuleDB)
#         .where(AutomationRuleDB.institution_id == institution_id)
#         .order_by(AutomationRuleDB.created_at.desc())
#     )
#     if channel:
#         query = query.where(AutomationRuleDB.channels.contains([channel]))
#     result = await db.execute(query)
#     return result.scalars().all()


# async def get_rule_by_id(
#     db: AsyncSession, rule_id: int, institution_id: int
# ) -> AutomationRuleDB:
#     result = await db.execute(
#         select(AutomationRuleDB).where(
#             AutomationRuleDB.id == rule_id,
#             AutomationRuleDB.institution_id == institution_id,
#         )
#     )
#     rule = result.scalar_one_or_none()
#     if not rule:
#         raise AutomationRuleNotFound(f"Rule {rule_id} not found.")
#     return rule


# async def update_rule(
#     db: AsyncSession, rule_id: int, institution_id: int, data: AutomationRuleUpdate,
# ) -> AutomationRuleDB:
#     rule = await get_rule_by_id(db, rule_id, institution_id)
#     try:
#         if data.name              is not None: rule.name              = data.name
#         if data.channels          is not None: rule.channels          = [ch.value for ch in data.channels]
#         if data.audience          is not None: rule.audience          = data.audience
#         if data.channel_templates is not None:
#             rule.channel_templates = data.channel_templates.model_dump(exclude_none=True)
#         if data.schedule          is not None: rule.schedule          = data.schedule
#         if data.cron_expression   is not None: rule.cron_expression   = data.cron_expression
#         if data.enabled           is not None: rule.enabled           = data.enabled
#         rule.updated_at = datetime.utcnow()
#         await db.commit()
#         await db.refresh(rule)
#         return rule
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"update_rule error: {e}", exc_info=True)
#         raise DatabaseError("Failed to update rule")


# async def toggle_rule(
#     db: AsyncSession, rule_id: int, institution_id: int
# ) -> AutomationRuleDB:
#     rule = await get_rule_by_id(db, rule_id, institution_id)
#     try:
#         rule.enabled    = not rule.enabled
#         rule.updated_at = datetime.utcnow()
#         await db.commit()
#         await db.refresh(rule)
#         return rule
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"toggle_rule error: {e}", exc_info=True)
#         raise DatabaseError("Failed to toggle rule")


# async def delete_rule(
#     db: AsyncSession, rule_id: int, institution_id: int
# ) -> None:
#     rule = await get_rule_by_id(db, rule_id, institution_id)
#     try:
#         await db.delete(rule)
#         await db.commit()
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"delete_rule error: {e}", exc_info=True)
#         raise DatabaseError("Failed to delete rule")


# async def increment_rule_sent_count(
#     db: AsyncSession, rule_id: int, count: int = 1
# ) -> None:
#     try:
#         await db.execute(
#             update(AutomationRuleDB)
#             .where(AutomationRuleDB.id == rule_id)
#             .values(
#                 sent_count=AutomationRuleDB.sent_count + count,
#                 last_run=datetime.utcnow(),
#             )
#         )
#         await db.commit()
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"increment_rule_sent_count error: {e}", exc_info=True)


# ══════════════════════════════════════════════════════════════
# MESSAGE LOG CRUD
# ══════════════════════════════════════════════════════════════

# async def create_message_log(
#     db: AsyncSession, institution_id: int, data: MessageLogCreate,
# ) -> MessageLogDB:
#     try:
#         log = MessageLogDB(
#             institution_id=institution_id,
#             rule_id=data.rule_id,
#             channel=data.channel.value,
#             whatsapp_config_id=data.whatsapp_config_id,
#             email_config_id=data.email_config_id,
#             recipient_name=data.recipient_name,
#             recipient_contact=data.recipient_contact,
#             subject=data.subject,
#             message_body=data.message_body,
#             message_type=data.message_type.value,
#             status=data.status.value,
#             provider_message_id=data.provider_message_id,
#             sent_at=datetime.utcnow() if data.status == MessageStatusEnum.SENT else None,
#         )
#         db.add(log)
#         await db.commit()
#         await db.refresh(log)
#         return log
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"create_message_log error: {e}", exc_info=True)
#         raise DatabaseError("Failed to create message log")


# async def get_message_logs(
#     db: AsyncSession,
#     institution_id: int,
#     page: int = 1,
#     page_size: int = 20,
#     rule_id: Optional[int] = None,
#     channel: Optional[str] = None,
# ) -> tuple[list[MessageLogDB], int]:
#     query = select(MessageLogDB).where(
#         MessageLogDB.institution_id == institution_id
#     )
#     if rule_id is not None:
#         if rule_id == 0:
#             query = query.where(MessageLogDB.rule_id == None)
#         else:
#             query = query.where(MessageLogDB.rule_id == rule_id)
#     if channel:
#         query = query.where(MessageLogDB.channel == channel)

#     count_result = await db.execute(
#         select(func.count()).select_from(query.subquery())
#     )
#     total = count_result.scalar_one()
#     result = await db.execute(
#         query.order_by(MessageLogDB.created_at.desc())
#         .offset((page - 1) * page_size)
#         .limit(page_size)
#     )
#     return result.scalars().all(), total


# async def update_message_status_by_provider_id(
#     db: AsyncSession,
#     provider_message_id: str,
#     status: MessageStatusEnum,
#     error_message: Optional[str] = None,
# ) -> Optional[MessageLogDB]:
#     result = await db.execute(
#         select(MessageLogDB).where(
#             MessageLogDB.provider_message_id == provider_message_id
#         )
#     )
#     log = result.scalar_one_or_none()
#     if not log:
#         logger.warning(f"Webhook: no log for provider_message_id={provider_message_id}")
#         return None
#     try:
#         log.status        = status.value
#         log.error_message = error_message
#         if status == MessageStatusEnum.DELIVERED:
#             log.delivered_at = datetime.utcnow()
#         await db.commit()
#         await db.refresh(log)
#         return log
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"update_message_status_by_provider_id error: {e}", exc_info=True)
#         raise DatabaseError("Failed to update message status")