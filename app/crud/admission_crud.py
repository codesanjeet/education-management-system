from __future__ import annotations

import io
import logging
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import magic
from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import case, cast, Date, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from ..core.storage import r2, R2StorageError              # ← centralised singleton
from ..models.admission_model import AdmissionFormDB, AdmissionStatus, InstitutionPageDB
from ..schemas.admission_schema import (
    AdmissionFormCreate,
    AdmissionFormStatusUpdate,
    AdmissionGrowthPoint,
    AdmissionStatsResponse,
    InstitutionPageCreate,
    InstitutionPageUpdate,
    slugify,
)

logger = logging.getLogger(__name__)


# ─── Config ───────────────────────────────────────────────────────────────────

FRONTEND_BASE_URL: str = os.getenv("FRONTEND_BASE_URL", "").rstrip("/")
BACKEND_BASE_URL:  str = os.getenv("BACKEND_BASE_URL",  "").rstrip("/")

if not FRONTEND_BASE_URL:
    logger.warning("FRONTEND_BASE_URL is not set — page/chat URLs will be broken")


# ─── Constants ────────────────────────────────────────────────────────────────

_ALLOWED_PAGE_FIELDS = frozenset({
    "page_name", "slider_items", "about_title", "about_body",
    "about_image_key", "stats_items", "features_items", "contact_items",
    "map_embed_url", "social_links", "admission_open", "admission_note",
    "chatbot_enabled", "chatbot_label", "logo_key", "is_published",
})

_SLUG_RE = re.compile(r'^[a-z0-9-]{3,100}$')


# ─── Image upload (page images) ───────────────────────────────────────────────
# Validation pipeline lives here — storage.py only holds the R2 connection.
# Mirrors the pattern used by institution_crud.save_image.

MAX_PAGE_IMAGE_SIZE_MB:    int = 10
MAX_PAGE_IMAGE_SIZE_BYTES: int = MAX_PAGE_IMAGE_SIZE_MB * 1024 * 1024

_ALLOWED_MIME_TYPES: dict[str, str] = {
    "image/jpeg": "jpeg",
    "image/jpg":  "jpeg",
    "image/png":  "png",
    "image/webp": "webp",
    "image/gif":  "gif",
    "image/avif": "avif",
    "image/heic": "heic",
    "image/heif": "heif",
}

_ALLOWED_PILLOW_FORMATS: set[str] = {"JPEG", "PNG", "WEBP", "GIF", "AVIF"}

_PILLOW_FORMAT_TO_EXT: dict[str, str] = {
    "JPEG": "jpg",
    "PNG":  "png",
    "WEBP": "webp",
    "GIF":  "gif",
    "AVIF": "avif",
}

_EXT_TO_CONTENT_TYPE: dict[str, str] = {
    "jpg":  "image/jpeg",
    "png":  "image/png",
    "webp": "image/webp",
    "gif":  "image/gif",
    "avif": "image/avif",
}

# Valid image_type folder segments — mirrors ImageType in the old storage module
_VALID_IMAGE_TYPES: set[str] = {
    "slider-desktop", "slider-mobile", "about", "logo", "attachment",
}


def _page_image_folder(tenant_id: str, image_type: str) -> str:
    """
    Return the canonical R2 folder for a page image.
    Both segments are validated so no user-supplied value can escape the hierarchy.

    Structure:  institutions/{tenant_id}/page/{image_type}
    """
    if not re.fullmatch(r"[a-zA-Z0-9_\-]+", str(tenant_id)):
        raise ValueError(f"Invalid tenant_id for storage path: {tenant_id!r}")
    if image_type not in _VALID_IMAGE_TYPES:
        raise ValueError(f"Invalid image_type: {image_type!r}")
    return f"institutions/{tenant_id}/page/{image_type}"


async def save_page_image(
    tenant_id: str,
    image_type: str,
    file: UploadFile,
) -> dict[str, str]:
    """
    Validate and upload a page image to the R2 public bucket.

    Validation pipeline:
      1. Content-Type header whitelist
      2. Size cap (MAX_PAGE_IMAGE_SIZE_BYTES)
      3. Magic-byte check via python-magic
      4. Pillow verify() — rejects corrupt / polyglot files
      5. Pillow format whitelist
      6. Upload via r2 singleton

    Returns:
        {"key": "<r2-key>", "url": "<public-url>"}

    Raises:
        HTTPException 400 for all validation failures
        HTTPException 500 for R2 errors
    """
    # 1. Content-Type header whitelist
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{content_type}'. "
                f"Allowed: {', '.join(sorted(set(_ALLOWED_MIME_TYPES.keys())))}."
            ),
        )

    # 2. Read bytes + size cap
    raw_bytes: bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw_bytes) > MAX_PAGE_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum allowed size is {MAX_PAGE_IMAGE_SIZE_MB} MB.",
        )

    # 3. Magic-byte check
    try:
        detected_mime: str = magic.from_buffer(raw_bytes[:4096], mime=True)
    except Exception as exc:
        logger.warning("python-magic failed: %s", exc)
        raise HTTPException(status_code=400, detail="Could not verify file type.")

    if detected_mime not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File content does not match an allowed image type "
                f"(detected: {detected_mime})."
            ),
        )

    # 4 & 5. Pillow verify + format whitelist
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.verify()
        pillow_format: str = img.format or ""
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="File is not a recognised image.")
    except Exception as exc:
        logger.warning("Pillow verify failed: %s", exc)
        raise HTTPException(status_code=400, detail="Image validation failed.")

    # Re-open after verify() — verify() leaves the stream exhausted
    try:
        img2 = Image.open(io.BytesIO(raw_bytes))
        pillow_format = img2.format or pillow_format
    except Exception:
        pass

    if pillow_format not in _ALLOWED_PILLOW_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Image format '{pillow_format}' is not accepted.",
        )

    # Derive safe extension from Pillow format (never trust the filename)
    ext:                 str = _PILLOW_FORMAT_TO_EXT.get(pillow_format, "jpg")
    content_type_upload: str = _EXT_TO_CONTENT_TYPE.get(ext, "image/jpeg")

    # Build folder-scoped key
    folder = _page_image_folder(tenant_id, image_type)
    key    = f"{folder}/{uuid.uuid4().hex}.{ext}"

    # 6. Upload
    try:
        await r2.upload(key, raw_bytes, content_type_upload, is_private=False)
    except R2StorageError as exc:
        logger.error("R2 upload failed for page image [key=%s]: %s", key, exc)
        raise HTTPException(status_code=500, detail="Storage upload failed.")

    return {"key": key, "url": r2.public_url(key)}


# ─── Image URL helpers ────────────────────────────────────────────────────────

def _resolve_image_url(key_or_url: Optional[str]) -> Optional[str]:
    """
    Convert an R2 object key to a public CDN URL via the centralised r2 singleton.
    Already-absolute http(s) URLs are passed through unchanged.
    """
    if not key_or_url:
        return None
    if key_or_url.startswith("http://") or key_or_url.startswith("https://"):
        return key_or_url
    return r2.public_url(key_or_url)


def _resolve_slider_items(items: list) -> list:
    """Inject resolved image_url (desktop) and image_url_mobile into each slider item dict."""
    resolved = []
    for item in (items or []):
        d = dict(item)
        d["image_url"]        = _resolve_image_url(d.get("image_key") or d.get("image"))
        d["image_url_mobile"] = _resolve_image_url(d.get("image_key_mobile"))
        resolved.append(d)
    return resolved


# ─── Slug validation ──────────────────────────────────────────────────────────

def _validate_slug(page_name: str) -> str:
    if not _SLUG_RE.match(page_name):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "page_name must be 3–100 characters and contain only "
                "lowercase letters, numbers, and hyphens."
            ),
        )
    return page_name


# ─── Institution helpers ──────────────────────────────────────────────────────

async def _get_institution(db: AsyncSession, institution_id: int) -> Any:
    from ..models.institution_model import InstitutionDB
    result = await db.execute(
        select(InstitutionDB).where(InstitutionDB.id == institution_id)
    )
    inst = result.scalar_one_or_none()
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found.")
    return inst


async def _get_institution_info(db: AsyncSession, institution_id: int) -> Optional[Any]:
    try:
        from ..models.institution_model import InstitutionInfoDB
        result = await db.execute(
            select(InstitutionInfoDB).where(
                InstitutionInfoDB.institution_id == institution_id
            )
        )
        return result.scalar_one_or_none()
    except Exception:
        logger.error(
            "Failed to fetch institution info | institution=%s",
            institution_id, exc_info=True,
        )
        return None


async def _sync_institution_info(
    db: AsyncSession,
    institution_id: int,
    page_name: str,
) -> None:
    """
    Upsert InstitutionInfoDB with canonical page + chat URLs.
    Flush only — outer function owns the commit.
    """
    try:
        from ..models.institution_model import InstitutionInfoDB
        page_url = f"{FRONTEND_BASE_URL}/institution/{page_name}"
        chat_url = f"{FRONTEND_BASE_URL}/institution/{page_name}/chat"

        result = await db.execute(
            select(InstitutionInfoDB).where(
                InstitutionInfoDB.institution_id == institution_id
            )
        )
        info = result.scalar_one_or_none()
        if info:
            info.institution_page_url = page_url
            info.ai_chat_url          = chat_url
        else:
            db.add(InstitutionInfoDB(
                institution_id=institution_id,
                institution_page_url=page_url,
                ai_chat_url=chat_url,
            ))
        await db.flush()
    except Exception:
        logger.warning(
            "Could not sync InstitutionInfoDB | institution=%s",
            institution_id, exc_info=True,
        )


# ─── Page enrichment ──────────────────────────────────────────────────────────

def _enrich_page(
    page: InstitutionPageDB,
    inst: Any,
    info: Optional[Any] = None,
    seo_warning: Optional[str] = None,
) -> Dict[str, Any]:
    logo_key = page.logo_key or getattr(inst, "logo", None)
    return {
        "page_name":       page.page_name,
        "institute_name":  inst.institute_name,
        "logo_url":        _resolve_image_url(logo_key),
        "slider_items":    _resolve_slider_items(page.slider_items or []),
        "about_title":     page.about_title,
        "about_body":      page.about_body,
        "about_image_url": _resolve_image_url(page.about_image_key),
        "stats_items":     page.stats_items    or [],
        "features_items":  page.features_items or [],
        "contact_items":   page.contact_items  or [],
        "map_embed_url":   page.map_embed_url,
        "social_links":    page.social_links   or {},
        "admission_open":  page.admission_open,
        "admission_note":  page.admission_note,
        "chatbot_enabled": page.chatbot_enabled,
        "chatbot_label":   page.chatbot_label,
        "chat_url":        getattr(info, "ai_chat_url",          None) if info else None,
        "page_url":        getattr(info, "institution_page_url", None) if info else None,
        "is_published":    page.is_published,
        "created_at":      page.created_at,
        "updated_at":      page.updated_at,
        "seo_warning":     seo_warning,
    }


# ══════════════════════════════════════════════════════════════════════════════
# SLUG HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def check_page_name_available(
    db: AsyncSession,
    raw_name: str,
    exclude_institution_id: Optional[int] = None,
) -> Dict[str, Any]:
    slug = slugify(raw_name)
    _validate_slug(slug)

    stmt = select(InstitutionPageDB).where(InstitutionPageDB.page_name == slug)
    if exclude_institution_id:
        stmt = stmt.where(InstitutionPageDB.institution_id != exclude_institution_id)

    result    = await db.execute(stmt)
    available = result.scalar_one_or_none() is None
    return {
        "slug":      slug,
        "available": available,
        "message":   "Slug is available." if available else f"'{slug}' is already taken.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# INSTITUTION PAGE CRUD
# ══════════════════════════════════════════════════════════════════════════════

async def get_institution_page(
    db: AsyncSession,
    institution_id: int,
) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        select(InstitutionPageDB).where(
            InstitutionPageDB.institution_id == institution_id
        )
    )
    page = result.scalar_one_or_none()
    if page is None:
        return None
    inst = await _get_institution(db, institution_id)
    info = await _get_institution_info(db, institution_id)
    return _enrich_page(page, inst, info)


async def get_institution_page_by_slug(
    db: AsyncSession,
    page_name: str,
) -> Optional[Dict[str, Any]]:
    """Public — fetch by slug, only published pages."""
    _validate_slug(page_name)

    from ..models.institution_model import InstitutionDB
    result = await db.execute(
        select(InstitutionPageDB, InstitutionDB)
        .join(InstitutionDB, InstitutionDB.id == InstitutionPageDB.institution_id)
        .where(InstitutionPageDB.page_name    == page_name)
        .where(InstitutionPageDB.is_published == True)          # noqa: E712
    )
    row = result.first()
    if row is None:
        return None
    page, inst = row
    info = await _get_institution_info(db, inst.id)
    return _enrich_page(page, inst, info)


async def get_institution_by_slug(
    db: AsyncSession,
    page_name: str,
) -> Optional[Any]:
    """Return the InstitutionDB row for a given page_name slug."""
    _validate_slug(page_name)

    from ..models.institution_model import InstitutionDB
    result = await db.execute(
        select(InstitutionDB)
        .join(InstitutionPageDB, InstitutionPageDB.institution_id == InstitutionDB.id)
        .where(InstitutionPageDB.page_name    == page_name)
        .where(InstitutionPageDB.is_published == True)          # noqa: E712
    )
    return result.scalar_one_or_none()


async def create_institution_page(
    db: AsyncSession,
    institution_id: int,
    data: InstitutionPageCreate,
) -> Dict[str, Any]:
    _validate_slug(data.page_name)

    existing = await db.execute(
        select(InstitutionPageDB).where(
            InstitutionPageDB.institution_id == institution_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Institution page already exists. Use PATCH to update.",
        )

    slug_taken = await db.execute(
        select(InstitutionPageDB).where(InstitutionPageDB.page_name == data.page_name)
    )
    if slug_taken.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Page name '{data.page_name}' is already taken.",
        )

    page = InstitutionPageDB(
        institution_id =institution_id,
        page_name      =data.page_name,
        slider_items   =[s.model_dump() for s in data.slider_items],
        about_title    =data.about_title,
        about_body     =data.about_body,
        about_image_key=data.about_image_key,
        stats_items    =[s.model_dump() for s in data.stats_items],
        features_items =[f.model_dump() for f in data.features_items],
        contact_items  =[c.model_dump() for c in data.contact_items],
        map_embed_url  =data.map_embed_url,
        social_links   =data.social_links.model_dump(exclude_none=True),
        admission_open =data.admission_open,
        admission_note =data.admission_note,
        chatbot_enabled=data.chatbot_enabled,
        chatbot_label  =data.chatbot_label,
        logo_key       =data.logo_key,
        is_published   =data.is_published,
    )
    db.add(page)

    try:
        await db.flush()
        await _sync_institution_info(db, institution_id, data.page_name)
        await db.commit()
        await db.refresh(page)
    except Exception:
        await db.rollback()
        logger.error(
            "create_institution_page failed | institution=%s",
            institution_id, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create institution page.",
        )

    inst = await _get_institution(db, institution_id)
    info = await _get_institution_info(db, institution_id)
    return _enrich_page(page, inst, info)


async def update_institution_page(
    db: AsyncSession,
    institution_id: int,
    data: InstitutionPageUpdate,
) -> Dict[str, Any]:
    result = await db.execute(
        select(InstitutionPageDB).where(
            InstitutionPageDB.institution_id == institution_id
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(
            status_code=404,
            detail="Institution page not found. Create it first.",
        )

    payload = data.model_dump(exclude_unset=True)

    seo_warning: Optional[str] = None
    if "page_name" in payload and payload["page_name"] != page.page_name:
        _validate_slug(payload["page_name"])

        slug_taken = await db.execute(
            select(InstitutionPageDB).where(
                InstitutionPageDB.page_name      == payload["page_name"],
                InstitutionPageDB.institution_id != institution_id,
            )
        )
        if slug_taken.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Page name '{payload['page_name']}' is already taken.",
            )
        if page.is_published:
            seo_warning = (
                "⚠️ You changed the page URL slug after it was published. "
                "All existing links and search engine rankings for the old URL "
                "will break. Set up a redirect from the old slug if possible."
            )

    if "slider_items"   in payload and payload["slider_items"]   is not None:
        payload["slider_items"]   = [s.model_dump() for s in data.slider_items]
    if "stats_items"    in payload and payload["stats_items"]    is not None:
        payload["stats_items"]    = [s.model_dump() for s in data.stats_items]
    if "features_items" in payload and payload["features_items"] is not None:
        payload["features_items"] = [f.model_dump() for f in data.features_items]
    if "contact_items"  in payload and payload["contact_items"]  is not None:
        payload["contact_items"]  = [c.model_dump() for c in data.contact_items]
    if "social_links"   in payload and payload["social_links"]   is not None:
        payload["social_links"]   = data.social_links.model_dump(exclude_none=True)

    for key, val in payload.items():
        if key not in _ALLOWED_PAGE_FIELDS:
            logger.warning(
                "Blocked attempt to set unauthorised page field | field=%s institution=%s",
                key, institution_id,
            )
            continue
        setattr(page, key, val)

    page.updated_at = datetime.utcnow()

    new_slug = payload.get("page_name") or page.page_name
    if new_slug:
        await _sync_institution_info(db, institution_id, new_slug)

    try:
        await db.commit()
        await db.refresh(page)
    except Exception:
        await db.rollback()
        logger.error(
            "update_institution_page failed | institution=%s",
            institution_id, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update institution page.",
        )

    inst = await _get_institution(db, institution_id)
    info = await _get_institution_info(db, institution_id)
    return _enrich_page(page, inst, info, seo_warning=seo_warning)


async def toggle_publish_page(
    db: AsyncSession,
    institution_id: int,
    publish: bool,
) -> Dict[str, Any]:
    result = await db.execute(
        select(InstitutionPageDB).where(
            InstitutionPageDB.institution_id == institution_id
        )
    )
    page = result.scalar_one_or_none()
    if not page:
        raise HTTPException(status_code=404, detail="Institution page not found.")

    page.is_published = publish
    page.updated_at   = datetime.utcnow()

    try:
        await db.commit()
        await db.refresh(page)
    except Exception:
        await db.rollback()
        logger.error(
            "toggle_publish_page failed | institution=%s publish=%s",
            institution_id, publish, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update publish status.",
        )

    inst = await _get_institution(db, institution_id)
    info = await _get_institution_info(db, institution_id)
    return _enrich_page(page, inst, info)


# ══════════════════════════════════════════════════════════════════════════════
# ADMISSION FORMS
# ══════════════════════════════════════════════════════════════════════════════

async def submit_admission_form(
    db: AsyncSession,
    institution_id: int,
    data: AdmissionFormCreate,
) -> AdmissionFormDB:
    """
    Save a new admission enquiry.
    Honeypot check must be done at router level before calling this.
    """
    form = AdmissionFormDB(
        institution_id     =institution_id,
        first_name         =data.first_name,
        last_name          =data.last_name,
        date_of_birth      =data.date_of_birth,
        gender             =data.gender,
        email              =str(data.email) if data.email else None,
        phone              =data.phone,
        applying_for_class =data.applying_for_class,
        previous_school    =data.previous_school,
        previous_percentage=data.previous_percentage,
        guardian_name      =data.guardian_name,
        guardian_phone     =data.guardian_phone,
        guardian_relation  =data.guardian_relation,
        address            =data.address,
        city               =data.city,
        state              =data.state,
        pincode            =data.pincode,
        message            =data.message,
        status             =AdmissionStatus.PENDING,
    )
    db.add(form)

    try:
        await db.commit()
        await db.refresh(form)
        return form
    except Exception:
        await db.rollback()
        logger.error(
            "submit_admission_form failed | institution=%s",
            institution_id, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit admission form. Please try again.",
        )


async def get_admission_form(
    db: AsyncSession,
    form_id: int,
    institution_id: int,
) -> AdmissionFormDB:
    result = await db.execute(
        select(AdmissionFormDB).where(
            AdmissionFormDB.id             == form_id,
            AdmissionFormDB.institution_id == institution_id,
        )
    )
    form = result.scalar_one_or_none()
    if not form:
        raise HTTPException(status_code=404, detail="Admission form not found.")
    return form


async def list_admission_forms(
    db: AsyncSession,
    institution_id: int,
    page: int                    = 1,
    limit: int                   = 20,
    status_filter: Optional[str] = None,
    search: Optional[str]        = None,
) -> Tuple[List[AdmissionFormDB], int]:
    if search and len(search) > 100:
        search = search[:100]

    base_filter = AdmissionFormDB.institution_id == institution_id
    stmt        = select(AdmissionFormDB).where(base_filter)
    count_stmt  = select(func.count()).select_from(AdmissionFormDB).where(base_filter)

    if status_filter:
        stmt       = stmt.where(AdmissionFormDB.status == status_filter)
        count_stmt = count_stmt.where(AdmissionFormDB.status == status_filter)

    if search:
        like        = f"%{search}%"
        filter_expr = or_(
            AdmissionFormDB.first_name.ilike(like),
            AdmissionFormDB.last_name.ilike(like),
            AdmissionFormDB.email.ilike(like),
            AdmissionFormDB.phone.ilike(like),
        )
        stmt       = stmt.where(filter_expr)
        count_stmt = count_stmt.where(filter_expr)

    total_result = await db.execute(count_stmt)
    total        = total_result.scalar() or 0

    stmt   = stmt.order_by(AdmissionFormDB.created_at.desc())
    stmt   = stmt.offset((page - 1) * limit).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all()), total


async def update_admission_status(
    db: AsyncSession,
    form_id: int,
    institution_id: int,
    data: AdmissionFormStatusUpdate,
    reviewed_by_user_id: int,
) -> AdmissionFormDB:
    form = await get_admission_form(db, form_id, institution_id)
    form.status      = data.status
    form.admin_notes = data.admin_notes
    form.reviewed_by = reviewed_by_user_id
    form.reviewed_at = datetime.utcnow()
    form.updated_at  = datetime.utcnow()

    try:
        await db.commit()
        await db.refresh(form)
        return form
    except Exception:
        await db.rollback()
        logger.error(
            "update_admission_status failed | form=%s institution=%s",
            form_id, institution_id, exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update admission status.",
        )


# ══════════════════════════════════════════════════════════════════════════════
# STATS  (2 queries)
# ══════════════════════════════════════════════════════════════════════════════

async def get_admission_stats(
    db: AsyncSession,
    institution_id: int,
) -> AdmissionStatsResponse:
    now         = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    since       = now - timedelta(days=29)

    stats_result = await db.execute(
        select(
            func.count().label("total"),
            func.count(case(
                (AdmissionFormDB.status == AdmissionStatus.PENDING,    1)
            )).label("pending"),
            func.count(case(
                (AdmissionFormDB.status == AdmissionStatus.REVIEWED,   1)
            )).label("reviewed"),
            func.count(case(
                (AdmissionFormDB.status == AdmissionStatus.ACCEPTED,   1)
            )).label("accepted"),
            func.count(case(
                (AdmissionFormDB.status == AdmissionStatus.REJECTED,   1)
            )).label("rejected"),
            func.count(case(
                (AdmissionFormDB.status == AdmissionStatus.WAITLISTED, 1)
            )).label("waitlisted"),
            func.count(case(
                (AdmissionFormDB.created_at >= month_start,            1)
            )).label("this_month"),
        )
        .select_from(AdmissionFormDB)
        .where(AdmissionFormDB.institution_id == institution_id)
    )
    row = stats_result.mappings().one()

    growth_result = await db.execute(
        select(
            cast(AdmissionFormDB.created_at, Date).label("date"),
            func.count().label("count"),
        )
        .where(
            AdmissionFormDB.institution_id == institution_id,
            AdmissionFormDB.created_at     >= since,
        )
        .group_by(cast(AdmissionFormDB.created_at, Date))
        .order_by(cast(AdmissionFormDB.created_at, Date))
    )

    return AdmissionStatsResponse(
        total      =row["total"],
        pending    =row["pending"],
        reviewed   =row["reviewed"],
        accepted   =row["accepted"],
        rejected   =row["rejected"],
        waitlisted =row["waitlisted"],
        this_month =row["this_month"],
        growth     =[
            AdmissionGrowthPoint(date=str(r.date), count=r.count)
            for r in growth_result.all()
        ],
    )