from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import (
    APIRouter, Depends, Query, UploadFile, File, Request,
    HTTPException, status,
)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from app.rate_limiter import RateLimiter
from ..schemas.admission_schema import (
    InstitutionPageCreate,
    InstitutionPageUpdate,
    InstitutionPageResponse,
    AdmissionFormCreate,
    AdmissionFormResponse,
    AdmissionFormStatusUpdate,
    AdmissionListResponse,
    AdmissionStatsResponse,
    ImageUploadResponse,
    PageNameCheckRequest,
    PageNameCheckResponse,
    IMAGE_SPECS,
)
from ..schemas.user_schema import CurrentUserResponse
from ..crud.admission_crud import (
    get_institution_page,
    get_institution_page_by_slug,
    get_institution_by_slug,
    create_institution_page,
    update_institution_page,
    toggle_publish_page,
    submit_admission_form,
    get_admission_form,
    list_admission_forms,
    update_admission_status,
    get_admission_stats,
    check_page_name_available,
    save_page_image,
)
from ..routers.fee_router import get_institution_id
from ..deps import require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Rate limiter instances ────────────────────────────────────────────────────
admission_submit_limiter = RateLimiter(max_calls=5, window_seconds=60)


# ── Valid image_type values (mirrors _VALID_IMAGE_TYPES in admission_crud) ───
_VALID_SPEC_KEYS: set[str] = {
    "slider-desktop", "slider-mobile", "about", "logo",
}

# ── Slug pattern: lowercase letters, digits, hyphens, 3–80 chars ─────────────
_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9\-]{1,78}[a-z0-9]$')


def _validate_slug(page_name: str) -> str:
    """Raise 400 if page_name does not look like a safe slug."""
    if not _SLUG_RE.match(page_name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid page name. "
                "Use 3–80 lowercase letters, digits, or hyphens; "
                "must start and end with a letter or digit."
            ),
        )
    return page_name


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS  (no auth)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/public/{page_name}/page",
    response_model=InstitutionPageResponse,
    tags=["Admission — Public"],
    summary="Get published institution landing page by slug",
)
async def public_get_page(
    page_name: str,
    db: AsyncSession = Depends(get_db),
):
    _validate_slug(page_name)                              # FIX 3: slug guard
    page = await get_institution_page_by_slug(db, page_name)
    if not page:
        raise HTTPException(
            status_code=404,
            detail="Page not found or not yet published.",
        )
    return page


@router.post(
    "/public/{page_name}/admission",
    response_model=AdmissionFormResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admission — Public"],
    summary="Submit an admission enquiry",
)
async def public_submit_admission(
    page_name: str,
    data: AdmissionFormCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    No auth required.
    Resolves page_name → institution_id, then saves the admission enquiry.
    Rate-limited: 5 submissions per IP per 60 seconds.
    """
    _validate_slug(page_name)                              # FIX 3: slug guard

                # FIX 2: real IP
    admission_submit_limiter.check(request)

    inst = await get_institution_by_slug(db, page_name)
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found.")

    return await submit_admission_form(db, inst.id, data)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — SLUG CHECK
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/institutions/admission/page/check-slug",
    response_model=PageNameCheckResponse,
    tags=["Admission — Admin"],
    summary="Check if a page name slug is available",
)
async def admin_check_slug(
    body: PageNameCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("system:settings")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await check_page_name_available(
        db,
        body.raw_name,
        exclude_institution_id=institution_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — IMAGE UPLOAD
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/institutions/admission/image/upload",
    response_model=ImageUploadResponse,
    tags=["Admission — Admin"],
    summary="Upload an image for the institution landing page",
)
async def admin_upload_image(
    file: UploadFile = File(...),
    spec_key: Optional[str] = Query(
        None,
        description=(
            "Image type — controls the storage folder. "
            "Accepted: slider-desktop | slider-mobile | about | logo"
        ),
    ),
    current_user: CurrentUserResponse = Depends(
        require_permission("system:settings")
    ),
):
    image_type = spec_key if spec_key in _VALID_SPEC_KEYS else "about"

    result = await save_page_image(
        tenant_id  =str(current_user.tenant_id),
        image_type =image_type,
        file       =file,
    )

    spec = IMAGE_SPECS.get(spec_key) if spec_key else None
    return ImageUploadResponse(key=result["key"], url=result["url"], spec=spec)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — INSTITUTION PAGE MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/institutions/admission/page",
    response_model=InstitutionPageResponse,
    tags=["Admission — Admin"],
    summary="Get own institution page config",
)
async def admin_get_page(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("system:settings")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    page = await get_institution_page(db, institution_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not configured yet.")
    return page


@router.post(
    "/institutions/admission/page",
    response_model=InstitutionPageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Admission — Admin"],
    summary="Create institution landing page",
)
async def admin_create_page(
    data: InstitutionPageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("system:settings")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await create_institution_page(db, institution_id, data)


@router.patch(
    "/institutions/admission/page",
    response_model=InstitutionPageResponse,
    tags=["Admission — Admin"],
    summary="Update institution landing page (partial)",
)
async def admin_update_page(
    data: InstitutionPageUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("system:settings")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await update_institution_page(db, institution_id, data)


class PublishToggle(BaseModel):
    publish: bool


@router.post(
    "/institutions/admission/page/publish",
    response_model=InstitutionPageResponse,
    tags=["Admission — Admin"],
    summary="Publish or unpublish the institution landing page",
)
async def admin_toggle_publish(
    body: PublishToggle,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("system:settings")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await toggle_publish_page(db, institution_id, body.publish)


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN — ADMISSION FORM MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/institutions/admission/forms",
    response_model=AdmissionListResponse,
    tags=["Admission — Admin"],
    summary="List all admission enquiries",
)
async def admin_list_forms(
    page:          int           = Query(1,    ge=1),
    limit:         int           = Query(20,   ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),  # FIX 1: renamed
    search:        Optional[str] = Query(None, description="Search by name / phone / email"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("admission:management")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    items, total   = await list_admission_forms(
        db,
        institution_id=institution_id,
        page=page,
        limit=limit,
        status_filter=status_filter,
        search=search,
    )
    return AdmissionListResponse(items=items, total=total, page=page, limit=limit)


@router.get(
    "/institutions/admission/forms/{form_id}",
    response_model=AdmissionFormResponse,
    tags=["Admission — Admin"],
    summary="Get a single admission form",
)
async def admin_get_form(
    form_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("admission:management")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await get_admission_form(db, form_id, institution_id)


@router.patch(
    "/institutions/admission/forms/{form_id}/status",
    response_model=AdmissionFormResponse,
    tags=["Admission — Admin"],
    summary="Update admission form status (accept / reject / etc.)",
)
async def admin_update_form_status(
    form_id: int,
    data: AdmissionFormStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("admission:management")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await update_admission_status(
        db, form_id, institution_id, data, current_user.id
    )


@router.get(
    "/institutions/admission/stats",
    response_model=AdmissionStatsResponse,
    tags=["Admission — Admin"],
    summary="Admission statistics + 30-day growth data",
)
async def admin_admission_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("admission:management")
    ),
):
    institution_id = await get_institution_id(db, current_user.tenant_id)
    return await get_admission_stats(db, institution_id)