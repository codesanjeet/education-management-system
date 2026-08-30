from __future__ import annotations

import logging
import re
import uuid
from io import BytesIO
from pathlib import Path
from typing import Tuple

import anyio
from sqlalchemy import select, exists, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.exceptions import (
    ClassNotFoundError,
    DatabaseError,
    FileTooLargeError,
    FileUploadError,
    InvalidFileTypeError,
    InstitutionNotFoundError,
    StorageLimitExceededError,       
    StudyMaterialNotFoundError,
)
from ..core.storage import r2, R2StorageError
from ..models.classes_model import ClassDB
from ..models.institution_model import InstitutionDB
from ..models.institution_model import InstitutionUsageDB
from app.models import StudyMaterialDB
from app.schemas.study_material_schema import StudyMaterialResponse

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
PRESIGNED_URL_SECONDS   = 3_600                     # 1 hour
MAX_IMAGE_SIZE          = 10 * 1024 * 1024           # 10 MB
MAX_DOCUMENT_SIZE       = 25 * 1024 * 1024           # 25 MB
STORAGE_LIMIT_BYTES     = 1 * 1024 * 1024 * 1024    # 1 GB hard cap per institution
STORAGE_LIMIT_MB        = STORAGE_LIMIT_BYTES / (1024 * 1024)

# ── MIME / extension allow-lists ───────────────────────────────────────────────
ALLOWED_MIME_TYPES: set[str] = {
    "image/jpeg", "image/png",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-powerpoint",
    "text/plain",
}

IMAGE_MIME_TYPES: set[str] = {"image/jpeg", "image/png"}

ALLOWED_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png",
    ".pdf",
    ".docx", ".doc",
    ".xlsx", ".xls",
    ".csv",
    ".pptx", ".ppt",
    ".txt",
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


# ── Key builder ────────────────────────────────────────────────────────────────

def _build_r2_key(
    tenant_id: str, class_name: str, subject_name: str, filename: str
) -> str:
    safe_class   = re.sub(r"[^a-z0-9_-]", "_", class_name.lower().strip())
    safe_subject = re.sub(r"[^a-z0-9_-]", "_", subject_name.lower().strip())
    ext          = Path(filename).suffix.lower()
    unique_name  = f"{uuid.uuid4().hex}{ext}"
    return f"institutions/{tenant_id}/study_material/{safe_class}/{safe_subject}/{unique_name}"


# ── File validation ────────────────────────────────────────────────────────────

def _get_mime_sync(content: bytes) -> str:
    import magic
    try:
        return magic.Magic(mime=True).from_buffer(content)
    except Exception as exc:
        logger.error(f"libmagic error: {exc}")
        raise InvalidFileTypeError("Cannot detect file type")


def _norm_mime(raw: str) -> str:
    m = raw.lower().strip()
    if "spreadsheet"    in m:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if "wordprocessing" in m:
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if "presentation"   in m:
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return m


def _verify_image_sync(content: bytes) -> None:
    from PIL import Image
    MAX_PIXELS = 89_478_485
    try:
        img = Image.open(BytesIO(content))
        img.verify()
        img = Image.open(BytesIO(content))
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise InvalidFileTypeError(f"Image dimensions {w}×{h} exceed the allowed maximum")
    except Image.DecompressionBombError:
        raise InvalidFileTypeError("Image is a decompression bomb and was rejected")
    except InvalidFileTypeError:
        raise
    except Exception as exc:
        raise InvalidFileTypeError(f"Invalid or corrupt image file: {exc}")


async def validate_upload(filename: str, content: bytes) -> Tuple[str, int]:
    """Full validation pipeline. Returns (normalised_mime, file_size_bytes)."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(
            f"File extension '{ext}' is not allowed. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    size     = len(content)
    raw_mime = await anyio.to_thread.run_sync(lambda: _get_mime_sync(content))
    norm     = _norm_mime(raw_mime)

    if norm in _GENERIC_CONTAINERS or norm not in ALLOWED_MIME_TYPES:
        norm = _EXT_TO_MIME.get(ext, norm)

    if norm not in ALLOWED_MIME_TYPES:
        raise InvalidFileTypeError(f"File type '{raw_mime}' is not allowed.")

    if norm in IMAGE_MIME_TYPES:
        if size > MAX_IMAGE_SIZE:
            raise FileTooLargeError(
                f"Image too large ({size // (1024*1024)} MB). "
                f"Maximum allowed: {MAX_IMAGE_SIZE // (1024*1024)} MB"
            )
        await anyio.to_thread.run_sync(lambda: _verify_image_sync(content))
    else:
        if size > MAX_DOCUMENT_SIZE:
            raise FileTooLargeError(
                f"Document too large ({size // (1024*1024)} MB). "
                f"Maximum allowed: {MAX_DOCUMENT_SIZE // (1024*1024)} MB"
            )

    return norm, size


# ── Storage accounting helpers ─────────────────────────────────────────────────

async def _check_storage_limit(
    db: AsyncSession, institution_id: int, incoming_bytes: int
) -> None:
    """
    Raise StorageLimitExceededError when adding *incoming_bytes* would exceed
    STORAGE_LIMIT_BYTES (1 GB).  Reads from InstitutionUsageDB — the same row
    that notifications/email-credits already maintain — no new table needed.

    Call this BEFORE touching R2 so we never upload a file we then have to
    roll back.
    """
    result = await db.execute(
        select(InstitutionUsageDB.storage_used_mb)
        .where(InstitutionUsageDB.institution_id == institution_id)
    )
    current_mb    = result.scalar_one_or_none() or 0.0
    current_bytes = current_mb * 1024 * 1024

    if current_bytes + incoming_bytes > STORAGE_LIMIT_BYTES:
        used_gb     = current_bytes / (1024 ** 3)
        limit_gb    = STORAGE_LIMIT_BYTES / (1024 ** 3)
        incoming_mb = incoming_bytes / (1024 * 1024)
        raise StorageLimitExceededError(
            f"Storage limit reached ({used_gb:.2f} GB used / {limit_gb:.0f} GB limit). "
            f"This file is {incoming_mb:.1f} MB. "
            f"Delete unused materials to free space."
        )


async def _update_storage_usage(
    db: AsyncSession, institution_id: int, delta_bytes: int
) -> None:
    """
    Best-effort storage accounting — failures are logged, never raised.
    Drift is corrected by the nightly reconciliation job.

    delta_bytes > 0  → upload   (increment)
    delta_bytes < 0  → delete   (decrement, clamped to 0)
    """
    try:
        await db.execute(
            update(InstitutionUsageDB)
            .where(InstitutionUsageDB.institution_id == institution_id)
            .values(
                storage_used_mb=(
                    InstitutionUsageDB.storage_used_mb
                    + (delta_bytes / (1024 * 1024))
                )
            )
        )
        # Clamp to zero — prevents negative values from racing deletes
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
        logger.warning(
            f"[STORAGE] usage update failed for inst {institution_id}: {exc}"
        )
        await db.rollback()


# ── CRUD ───────────────────────────────────────────────────────────────────────

async def save_study_material(
    db: AsyncSession,
    tenant_id: str,
    file,                           # FastAPI UploadFile
    class_code: str,
    subject_name: str,
    downloadable: bool,
    title: str,
    description: str | None = None,
    uploaded_by: int | None = None,
) -> StudyMaterialResponse:
    """
    Full pipeline:
      validate → check storage limit → upload R2 → persist DB → update usage

    Storage limit is checked BEFORE R2 upload so we never waste bandwidth.
    Usage counter is updated AFTER a successful DB commit so the number only
    moves when the file is truly persisted.
    On DB failure the R2 object is cleaned up to keep them consistent.
    """
    # 1. Read bytes
    contents = await file.read()

    # 2. Safety validation
    mime, file_size = await validate_upload(file.filename, contents)

    # 3. Resolve institution (single query, returns id directly)
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_result.scalar_one_or_none()
    if not institution_id:
        raise InstitutionNotFoundError("Institution not found")

    # 4. Storage limit gate — fail fast before touching R2
    await _check_storage_limit(db, institution_id, file_size)

    # 5. Resolve class
    class_result = await db.execute(
        select(ClassDB.id, ClassDB.class_or_year_or_name)
        .where(ClassDB.class_code == class_code)
    )
    row = class_result.first()
    if not row:
        raise ClassNotFoundError(f"Class '{class_code}' not found")
    class_id, class_name = row

    # 6. Normalise path components
    class_name_norm   = class_name.lower().strip()
    subject_name_norm = subject_name.lower().strip()

    # 7. Upload to R2
    r2_key = _build_r2_key(tenant_id, class_name_norm, subject_name_norm, file.filename)
    try:
        await r2.upload(r2_key, contents, mime, is_private=True)
    except R2StorageError as exc:
        logger.error(f"[R2] upload failed for study material: {exc}")
        raise FileUploadError("Failed to upload file to storage")

    # 8. Persist metadata
    try:
        material = StudyMaterialDB(
            subject_name    = subject_name_norm,
            tenant_id       = tenant_id,
            class_name      = class_name_norm,
            title           = title,
            class_id        = class_id,
            description     = description,
            file_url        = r2_key,
            file_type       = mime,
            file_size_bytes = file_size,        # used for accurate usage accounting
            uploaded_by     = uploaded_by,
            downloadable    = downloadable,
        )
        db.add(material)
        await db.commit()
        await db.refresh(material)
    except Exception as exc:
        await db.rollback()
        await r2.delete(r2_key, is_private=True)   # orphan cleanup
        logger.error(f"[DB] save_study_material failed: {exc}", exc_info=True)
        raise DatabaseError("Failed to save study material")

    # 9. Update storage usage (best-effort, after successful commit)
    await _update_storage_usage(db, institution_id, file_size)

    return StudyMaterialResponse.model_validate(material, from_attributes=True)


async def delete_study_material(
    db: AsyncSession,
    material_id: int,
    tenant_id: str,
) -> dict:
    """
    Delete DB record → R2 object → decrement storage usage.
    DB is deleted first; R2 cleanup and usage decrement are best-effort.
    """
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_result.scalar_one_or_none()
    if not institution_id:
        raise InstitutionNotFoundError("Institution not found")

    result = await db.execute(
        select(StudyMaterialDB).where(StudyMaterialDB.id == material_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise StudyMaterialNotFoundError(f"Study material {material_id} not found")

    saved_key   = material.file_url
    saved_title = material.title
    saved_bytes: int = getattr(material, "file_size_bytes", 0) or 0

    try:
        await db.delete(material)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error(f"[DB] delete_study_material failed: {exc}", exc_info=True)
        raise DatabaseError("Failed to delete study material")

    # Best-effort R2 cleanup — r2.delete() never raises, only logs warnings
    await r2.delete(saved_key, is_private=True)

    # Decrement usage after successful delete
    if saved_bytes > 0:
        await _update_storage_usage(db, institution_id, -saved_bytes)

    return {
        "message": "Study material deleted successfully",
        "id":      material_id,
        "title":   saved_title,
    }


async def get_study_materials(
    db: AsyncSession,
    tenant_id: str,
    class_code: str,
) -> list[StudyMaterialResponse]:
    """Return all materials for a class, ordered newest-first."""
    class_query = await db.execute(
        select(ClassDB.id).where(ClassDB.class_code == class_code)
    )
    class_id = class_query.scalar_one_or_none()
    if not class_id:
        raise ClassNotFoundError(f"Class '{class_code}' not found")

    result    = await db.execute(
        select(StudyMaterialDB)
        .where(
            StudyMaterialDB.tenant_id == tenant_id,
            StudyMaterialDB.class_id  == class_id,
        )
        .order_by(StudyMaterialDB.uploaded_at.desc())
    )
    materials = result.scalars().all()
    return [
        StudyMaterialResponse.model_validate(m, from_attributes=True)
        for m in materials
    ]


async def get_study_material_by_id(
    db: AsyncSession,
    material_id: int,
) -> StudyMaterialResponse:
    result   = await db.execute(
        select(StudyMaterialDB).where(StudyMaterialDB.id == material_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise StudyMaterialNotFoundError(f"Study material {material_id} not found")
    return StudyMaterialResponse.model_validate(material, from_attributes=True)


async def update_study_material(
    db: AsyncSession,
    material_id: int,
    tenant_id: str,
    title: str | None = None,
    description: str | None = None,
) -> dict:
    inst_check = await db.execute(
        select(exists().where(InstitutionDB.tenant_id == tenant_id))
    )
    if not inst_check.scalar():
        raise InstitutionNotFoundError("Institution not found")

    result   = await db.execute(
        select(StudyMaterialDB).where(StudyMaterialDB.id == material_id)
    )
    material = result.scalar_one_or_none()
    if not material:
        raise StudyMaterialNotFoundError(f"Study material {material_id} not found")

    if title       is not None: material.title       = title
    if description is not None: material.description = description

    try:
        await db.commit()
        await db.refresh(material)
        return {
            "message": "Study material updated successfully",
            "data": {
                "id":          material.id,
                "title":       material.title,
                "description": material.description,
            },
        }
    except Exception as exc:
        await db.rollback()
        logger.error(f"[DB] update_study_material failed: {exc}", exc_info=True)
        raise DatabaseError("Failed to update study material")


async def get_study_material_download_url(
    db: AsyncSession,
    material_id: int,
    tenant_id: str,
) -> str:
    """Generate a short-lived presigned URL. Expires after PRESIGNED_URL_SECONDS (1 h)."""
    result   = await db.execute(
        select(StudyMaterialDB).where(
            StudyMaterialDB.id        == material_id,
            StudyMaterialDB.tenant_id == tenant_id,
        )
    )
    material = result.scalar_one_or_none()
    if not material:
        raise StudyMaterialNotFoundError(f"Study material {material_id} not found")

    try:
        return await r2.signed_url(material.file_url, expires=PRESIGNED_URL_SECONDS)
    except R2StorageError as exc:
        logger.error(f"[R2] presign failed for material {material_id}: {exc}")
        raise DatabaseError("Could not generate file download URL")


async def get_storage_usage(
    db: AsyncSession,
    tenant_id: str,
) -> dict:
    """
    Return live storage usage for the institution.
    Consumed by the study-materials page header to render the storage bar.
    Reads from InstitutionUsageDB — same source as the notifications panel.
    """
    inst_result = await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == tenant_id)
    )
    institution_id = inst_result.scalar_one_or_none()
    if not institution_id:
        raise InstitutionNotFoundError("Institution not found")

    usage_result = await db.execute(
        select(InstitutionUsageDB.storage_used_mb)
        .where(InstitutionUsageDB.institution_id == institution_id)
    )
    used_mb  = usage_result.scalar_one_or_none() or 0.0
    limit_mb = STORAGE_LIMIT_MB

    return {
        "storage_used_mb":  round(used_mb,  2),
        "storage_limit_mb": round(limit_mb, 2),
        "storage_used_pct": round(min(100.0, (used_mb / limit_mb) * 100), 1),
        "limit_reached":    used_mb >= limit_mb,
    }