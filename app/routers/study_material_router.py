from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from app.rate_limiter import RateLimiter, user_id_key
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
from ..crud.dashboard_crud import create_recent_activity_log
from ..crud.study_material_curd import (
    ALLOWED_EXTENSIONS,
    MAX_DOCUMENT_SIZE,
    MAX_IMAGE_SIZE,
    STORAGE_LIMIT_MB,
    delete_study_material,
    get_study_material_by_id,
    get_study_material_download_url,
    get_study_materials,
    get_storage_usage,
    save_study_material,
    update_study_material,
)
from ..deps import require_any_permission, require_permission_or_owner
from ..schemas.study_material_schema import (
    DeleteResponse,
    FileUploadResponse,
    StudyMaterialListResponse,
    StudyMaterialResponse,
    StudyMaterialUpdate,
    UpdateResponse,
)
from ..schemas.user_schema import CurrentUserResponse

router = APIRouter()


# ── Rate limiter instances ────────────────────────────────────────────────────
upload_limiter   = RateLimiter(max_calls=10, window_seconds=60)
download_limiter = RateLimiter(max_calls=30, window_seconds=60)


# ── Exception → HTTP mapping ──────────────────────────────────────────────────

def _handle_crud_exc(exc: Exception) -> None:
    if isinstance(exc, InvalidFileTypeError):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc))
    if isinstance(exc, FileTooLargeError):
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc))
    if isinstance(exc, StorageLimitExceededError):
        raise HTTPException(status_code=status.HTTP_507_INSUFFICIENT_STORAGE,    detail=str(exc))
    if isinstance(exc, (FileUploadError, DatabaseError)):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,   detail=str(exc))
    if isinstance(exc, (ClassNotFoundError, InstitutionNotFoundError, StudyMaterialNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,               detail=str(exc))
    raise exc


# ══════════════════════════════════════════════════════════════════════════════
# STORAGE USAGE  (register first — no path params, never shadowed)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/institutions/study-materials/storage-usage",
    summary="Get live storage usage for the institution",
    description=(
        "Returns current storage used (MB), the hard limit "
        f"({STORAGE_LIMIT_MB / 1024:.0f} GB), usage percentage, "
        "and whether the limit has been reached."
    ),
)
async def get_storage_usage_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission("content:basic_management", "content:full_management")
    ),
):
    try:
        return await get_storage_usage(db=db, tenant_id=current_user.tenant_id)
    except Exception as exc:
        _handle_crud_exc(exc)


# ══════════════════════════════════════════════════════════════════════════════
# UPLOAD  (class-scoped)
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/institutions/classes/{class_code}/study-materials",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload study material",
    description=(
        f"**Allowed extensions:** {', '.join(sorted(ALLOWED_EXTENSIONS))}\n\n"
        f"**Size limits:** images ≤ {MAX_IMAGE_SIZE // (1024*1024)} MB, "
        f"documents ≤ {MAX_DOCUMENT_SIZE // (1024*1024)} MB\n\n"
        f"**Institution storage cap:** {STORAGE_LIMIT_MB / 1024:.0f} GB total. "
        "Upload is rejected with HTTP 507 when the cap is reached.\n\n"
        "Files are stored in a private R2 bucket; access is only via "
        "time-limited presigned URLs."
    ),
)
async def upload_study_material_endpoint(
    request: Request,
    class_code: str,
    subject_name: str           = Form(..., description="Subject name"),
    title: str                  = Form(..., min_length=1, max_length=200),
    description: Optional[str]  = Form(None, max_length=1000),
    downloadable: bool          = Form(False),
    file: UploadFile            = File(...),
    db: AsyncSession            = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission("content:basic_management", "content:full_management")
    ),
):
    upload_limiter.check(request, key=user_id_key(current_user.id))

    try:
        result = await save_study_material(
            db           = db,
            tenant_id    = current_user.tenant_id,
            file         = file,
            class_code   = class_code,
            subject_name = subject_name,
            title        = title,
            description  = description,
            downloadable = downloadable,
            uploaded_by  = current_user.id,
        )
    except Exception as exc:
        _handle_crud_exc(exc)

    await create_recent_activity_log(
        db          = db,
        tenant_id   = current_user.tenant_id,
        user_id     = current_user.id,
        action_type = "study_material_created",
        message     = f"Study material uploaded: {title}",
    )

    return FileUploadResponse(message="Study material uploaded successfully", data=result)


# ══════════════════════════════════════════════════════════════════════════════
# LIST  (class-scoped)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/institutions/classes/{class_code}/study-materials",
    response_model=StudyMaterialListResponse,
    summary="List study materials for a class",
)
async def list_study_materials_endpoint(
    request: Request,
    class_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission("content:basic_management", "content:full_management")
    ),
):
    try:
        materials = await get_study_materials(
            db=db, tenant_id=current_user.tenant_id, class_code=class_code
        )
    except Exception as exc:
        _handle_crud_exc(exc)

    return StudyMaterialListResponse(count=len(materials), data=materials)


# ══════════════════════════════════════════════════════════════════════════════
# PRESIGNED DOWNLOAD URL — registered BEFORE /{material_id} to avoid shadowing
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/institutions/study-materials/{material_id}/download",
    summary="Get a time-limited presigned download URL (expires in 1 hour)",
)
async def get_study_material_download_url_endpoint(
    request: Request,
    material_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission("content:basic_management", "content:full_management")
    ),
):
    download_limiter.check(request, key=user_id_key(current_user.id))

    try:
        material = await get_study_material_by_id(db=db, material_id=material_id)
    except Exception as exc:
        _handle_crud_exc(exc)

    has_full = "content:full_management" in (current_user.permissions or [])
    if not material.downloadable and not has_full:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This material is not available for download",
        )

    try:
        url = await get_study_material_download_url(
            db=db, material_id=material_id, tenant_id=current_user.tenant_id
        )
    except Exception as exc:
        _handle_crud_exc(exc)

    return {"download_url": url, "expires_in_seconds": 3600}


# ══════════════════════════════════════════════════════════════════════════════
# GET SINGLE — registered AFTER /download and /storage-usage
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/institutions/study-materials/{material_id}",
    response_model=StudyMaterialResponse,
    summary="Get study material metadata by ID",
)
async def get_study_material_endpoint(
    material_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission("content:basic_management", "content:full_management")
    ),
):
    try:
        return await get_study_material_by_id(db=db, material_id=material_id)
    except Exception as exc:
        _handle_crud_exc(exc)


# ══════════════════════════════════════════════════════════════════════════════
# UPDATE
# ══════════════════════════════════════════════════════════════════════════════

@router.patch(
    "/institutions/study-materials/{material_id}",
    response_model=UpdateResponse,
    summary="Update study material metadata (title / description)",
)
async def update_study_material_endpoint(
    material_id: int,
    update_data: StudyMaterialUpdate,
    db: AsyncSession   = Depends(get_db),
    current_user: dict = Depends(require_permission_or_owner("content:basic_management")),
):
    user     = current_user["current_user"]
    is_owner = current_user["is_owner"]
    has_full = "content:full_management" in (user.permissions or [])

    if not (has_full or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update this material",
        )

    try:
        result = await update_study_material(
            db          = db,
            material_id = material_id,
            tenant_id   = user.tenant_id,
            title       = update_data.title,
            description = update_data.description,
        )
    except Exception as exc:
        _handle_crud_exc(exc)

    return UpdateResponse(**result)


# ══════════════════════════════════════════════════════════════════════════════
# DELETE
# ══════════════════════════════════════════════════════════════════════════════

@router.delete(
    "/institutions/study-materials/{material_id}",
    response_model=DeleteResponse,
    summary="Delete study material (DB record + R2 object + usage decrement)",
)
async def delete_study_material_endpoint(
    material_id: int,
    db: AsyncSession   = Depends(get_db),
    current_user: dict = Depends(require_permission_or_owner("content:basic_management")),
):
    user     = current_user["current_user"]
    is_owner = current_user["is_owner"]
    has_full = "content:full_management" in (user.permissions or [])

    if not (has_full or is_owner):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to delete this material",
        )

    try:
        result = await delete_study_material(
            db=db, material_id=material_id, tenant_id=user.tenant_id
        )
    except Exception as exc:
        _handle_crud_exc(exc)

    await create_recent_activity_log(
        db          = db,
        tenant_id   = user.tenant_id,
        user_id     = user.id,
        action_type = "study_material_deleted",
        message     = f"Study material deleted: {result['title']}",
    )

    return DeleteResponse(**result)