import os
import secrets
import uuid
import logging
import mimetypes
from io import BytesIO
from datetime import datetime, timezone
from typing import Optional

from PIL import Image
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import exists, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.institution_model import InstitutionDB,ContactSubmissionDB
from app.schemas.institution_schema import InstitutionUpdate,ContactSubmissionCreate
from ..core.storage import r2, R2StorageError          
from ..core.exceptions import (
    InstitutionNotFoundError,
    InstitutionAlreadyExistsError,
    InvalidImageError,
    ImageTooLargeError,
    DatabaseError,
)

logger = logging.getLogger(__name__)

# ── Image constants ───────────────────────────────────────────────────────────

MAX_IMAGE_SIZE = 10 * 1024 * 1024   # 10 MB

ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

OUTPUT_FORMAT       = "WEBP"
OUTPUT_CONTENT_TYPE = "image/webp"
OUTPUT_EXTENSION    = ".webp"
WEBP_QUALITY        = 85


# ── Image helpers ─────────────────────────────────────────────────────────────

def _r2_key(tenant_id: str, filename: str) -> str:
    return f"institutions/{tenant_id}/basics/{filename}"


def _sniff_mime(data: bytes, filename: str) -> str:
    """Magic-byte detection first, filename fallback."""
    try:
        img = Image.open(BytesIO(data))
        if img.format:
            return Image.MIME.get(img.format, "application/octet-stream")
    except Exception:
        pass
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _extract_r2_key_from_url(url: str) -> Optional[str]:
    """
    Pull the object key out of a public R2 URL.
    Needed because the DB stores full URLs (legacy) — we extract the key
    before calling r2.delete().
    """
    if not url:
        return None
    marker = "institutions/"
    idx = url.find(marker)
    return url[idx:] if idx != -1 else None


async def _delete_r2_image_async(url: Optional[str]) -> None:
    """
    Async best-effort R2 delete from the public bucket.
    Never raises — r2.delete() only logs on failure.
    """
    if not url:
        return
    key = _extract_r2_key_from_url(url)
    if not key:
        logger.warning("Cannot derive R2 key from URL: %s", url)
        return
    await r2.delete(key, is_private=False)


async def save_image(tenant_id: str, file: UploadFile, image_type: str) -> str:
    """
    Validate → re-encode to WebP → upload to R2 public bucket.
    Returns the full public CDN URL.

    Raises:
        ImageTooLargeError  – file exceeds MAX_IMAGE_SIZE
        InvalidImageError   – bad MIME / extension / corrupt bytes
        DatabaseError       – R2 upload failed
    """
    contents = await file.read()

    if len(contents) > MAX_IMAGE_SIZE:
        raise ImageTooLargeError(
            f"File is {len(contents):,} B — limit is {MAX_IMAGE_SIZE:,} B"
        )

    mime_type = _sniff_mime(contents, file.filename or "")
    if mime_type not in ALLOWED_MIME_TYPES:
        raise InvalidImageError(f"Unsupported image type: {mime_type}")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise InvalidImageError(f"Unsupported file extension: {ext}")

    # Re-encode to WebP (strips metadata, normalises colour mode)
    try:
        image = Image.open(BytesIO(contents))
        if image.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", image.size, (255, 255, 255))
            bg.paste(image.convert("RGBA"), mask=image.convert("RGBA").split()[3])
            image = bg
        else:
            image = image.convert("RGB")

        buf = BytesIO()
        image.save(buf, format=OUTPUT_FORMAT, quality=WEBP_QUALITY, optimize=True)
        encoded = buf.getvalue()
    except (InvalidImageError, ImageTooLargeError):
        raise
    except Exception as exc:
        logger.error("Re-encode failed for %s: %s", file.filename, exc)
        raise InvalidImageError("Cannot process image file") from exc

    key = _r2_key(tenant_id, f"{image_type}_{uuid.uuid4().hex[:8]}{OUTPUT_EXTENSION}")
    try:
        await r2.upload(key, encoded, OUTPUT_CONTENT_TYPE, is_private=False)
        return r2.public_url(key)
    except R2StorageError as exc:
        logger.error("R2 upload failed [key=%s]: %s", key, exc, exc_info=True)
        raise DatabaseError("Failed to upload image") from exc


# ── Tenant ID ─────────────────────────────────────────────────────────────────

def _generate_tenant_id() -> str:
    return secrets.token_hex(4).upper()


async def _unique_tenant_id(db: AsyncSession) -> str:
    while True:
        candidate = _generate_tenant_id()
        taken = await db.scalar(
            select(exists().where(InstitutionDB.tenant_id == candidate))
        )
        if not taken:
            return candidate


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create_institution(
    db: AsyncSession,
    institution_data: dict,
    logo: UploadFile,
) -> InstitutionDB:
    institution_data["email"] = institution_data["email"].lower()

    email_taken = await db.scalar(
        select(exists().where(InstitutionDB.email == institution_data["email"]))
    )
    if email_taken:
        raise InstitutionAlreadyExistsError(
            f"Email {institution_data['email']} is already registered"
        )

    tenant_id = await _unique_tenant_id(db)
    logo_url  = await save_image(tenant_id, logo, "logo")

    try:
        institution = InstitutionDB(
            **institution_data,
            tenant_id=tenant_id,
            logo=logo_url,
            is_verified=False,
            is_rejected=False,
            is_block=False,
        )
        db.add(institution)
        await db.commit()
        await db.refresh(institution)
        return institution

    except IntegrityError as exc:
        await db.rollback()
        await _delete_r2_image_async(logo_url)
        logger.warning("IntegrityError creating institution: %s", exc.orig)
        raise InstitutionAlreadyExistsError("Institution already exists") from exc

    except SQLAlchemyError as exc:
        await db.rollback()
        await _delete_r2_image_async(logo_url)
        logger.error("DB error creating institution: %s", exc, exc_info=True)
        raise DatabaseError("Unable to create institution") from exc


async def get_institution_by_tenant_id(
    db: AsyncSession,
    tenant_id: str,
) -> InstitutionDB:
    institution = await db.scalar(
        select(InstitutionDB).where(InstitutionDB.tenant_id == tenant_id)
    )
    if institution is None:
        raise InstitutionNotFoundError(f"Institution '{tenant_id}' not found")
    return institution


get_institution_general_data_by_tenant_id = get_institution_by_tenant_id


async def get_all_institutions(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[InstitutionDB], int]:
    try:
        rows = (
            await db.scalars(
                select(InstitutionDB)
                .order_by(InstitutionDB.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
        total = await db.scalar(select(func.count(InstitutionDB.id)))
        return list(rows), total or 0

    except SQLAlchemyError as exc:
        logger.error("DB error fetching institutions: %s", exc, exc_info=True)
        raise DatabaseError("Unable to fetch institutions") from exc


async def update_institution_by_tenant_id(
    db: AsyncSession,
    institution: InstitutionDB,
    institution_update: InstitutionUpdate,
) -> InstitutionDB:
    update_data = institution_update.model_dump(exclude_unset=True)
    if not update_data:
        raise ValueError("No fields provided for update")

    new_email = update_data.get("email")
    if new_email:
        update_data["email"] = new_email = new_email.lower()
        if new_email != institution.email:
            taken = await db.scalar(
                select(exists().where(
                    InstitutionDB.email == new_email,
                    InstitutionDB.id    != institution.id,
                ))
            )
            if taken:
                raise InstitutionAlreadyExistsError(f"Email '{new_email}' already in use")

    for field, value in update_data.items():
        setattr(institution, field, value)

    try:
        await db.commit()
        await db.refresh(institution)
        return institution

    except IntegrityError as exc:
        await db.rollback()
        logger.warning("IntegrityError updating institution: %s", exc.orig)
        raise InstitutionAlreadyExistsError("A conflicting institution already exists") from exc

    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("DB error updating institution: %s", exc, exc_info=True)
        raise DatabaseError("Unable to update institution") from exc


async def update_logo(
    db: AsyncSession,
    tenant_id: str,
    logo: UploadFile,
) -> InstitutionDB:
    """
    Replace institution logo:
      1. Upload new image to R2.
      2. Commit new URL to DB.
      3. Delete old image from R2 (only after commit succeeds).
    """
    institution = await get_institution_by_tenant_id(db, tenant_id)
    old_url     = institution.logo
    new_url     = await save_image(tenant_id, logo, "logo")

    try:
        institution.logo = new_url
        await db.commit()
        await db.refresh(institution)
    except SQLAlchemyError as exc:
        await db.rollback()
        await _delete_r2_image_async(new_url)
        logger.error("DB error saving logo [%s]: %s", tenant_id, exc, exc_info=True)
        raise DatabaseError("Unable to update logo") from exc

    # Old file deleted only after DB commit succeeds
    await _delete_r2_image_async(old_url)
    return institution


async def delete_institution_by_tenant_id(
    db: AsyncSession,
    tenant_id: str,
) -> dict:
    institution = await get_institution_by_tenant_id(db, tenant_id)
    logo_url    = institution.logo

    try:
        await db.delete(institution)
        await db.commit()
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("DB error deleting institution [%s]: %s", tenant_id, exc, exc_info=True)
        raise DatabaseError("Unable to delete institution") from exc

    # R2 cleanup after DB record is gone
    await _delete_r2_image_async(logo_url)
    return {"message": f"Institution {tenant_id} deleted successfully"}


async def soft_delete_institution_by_tenant_id(
    db: AsyncSession,
    tenant_id: str,
) -> dict:
    institution = await get_institution_by_tenant_id(db, tenant_id)
    institution.deleted_date = datetime.now(timezone.utc)

    try:
        await db.commit()
        return {"message": f"Institution {tenant_id} deleted successfully"}
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("DB error soft-deleting institution [%s]: %s", tenant_id, exc, exc_info=True)
        raise DatabaseError("Unable to delete institution") from exc
    



async def create_contact(
    db: AsyncSession,
    data: ContactSubmissionCreate,
) -> ContactSubmissionDB:
    try:
        submission = ContactSubmissionDB(**data.model_dump())
        db.add(submission)
        await db.commit()
        await db.refresh(submission)
        return submission
    except SQLAlchemyError as exc:
        await db.rollback()
        logger.error("DB error saving contact submission: %s", exc, exc_info=True)
        raise DatabaseError("Unable to save contact submission") from exc


async def get_all_contacts(
    db: AsyncSession,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[ContactSubmissionDB], int]:
    try:
        rows = (
            await db.scalars(
                select(ContactSubmissionDB)
                .order_by(ContactSubmissionDB.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        total = await db.scalar(select(func.count(ContactSubmissionDB.id)))
        return list(rows), total or 0
    except SQLAlchemyError as exc:
        logger.error("DB error fetching contact submissions: %s", exc, exc_info=True)
        raise DatabaseError("Unable to fetch contact submissions") from exc