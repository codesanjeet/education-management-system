from fastapi import APIRouter, Depends, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..deps import get_current_user, require_permission
from ..schemas.user_schema import CurrentUserResponse
from ..schemas.setting_schema import SecuritySettingResponse, SecuritySettingUpdate
from ..schemas.institution_schema import InstitutionResponse, InstitutionUpdate
from ..crud import institution_crud
from ..crud.setting_crud import get_security_setting, update_security_setting

router = APIRouter(
    prefix="/institutions/settings",
    tags=["Settings"],
)


# ── General ───────────────────────────────────────────────────────────────────

@router.get(
    "/general",
    response_model=InstitutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get general institution settings",
)
async def get_general_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    return await institution_crud.get_institution_by_tenant_id(
        db=db,
        tenant_id=current_user.tenant_id,
    )


@router.patch(
    "/general",
    response_model=InstitutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Update general institution settings",
)
async def update_general_settings(
    updated_data: InstitutionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("system:settings")),
):
    existing = await institution_crud.get_institution_by_tenant_id(
        db=db, tenant_id=current_user.tenant_id
    )
    return await institution_crud.update_institution_by_tenant_id(
        db=db, institution=existing, institution_update=updated_data
    )


# ── Logo ──────────────────────────────────────────────────────────────────────

@router.patch(
    "/logo",
    status_code=status.HTTP_200_OK,
    summary="Update institution logo",
)
async def update_logo(
    logo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("system:settings")),
):
    institution = await institution_crud.update_logo(
        db=db,
        tenant_id=current_user.tenant_id,
        logo=logo,
    )
    return {"message": "Logo updated successfully", "logo": institution.logo}


# ── Lifecycle ─────────────────────────────────────────────────────────────────

@router.delete(
    "",
    status_code=status.HTTP_200_OK,
    summary="Soft-delete institution",
)
async def soft_delete_institution(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("system:settings")),
):
    return await institution_crud.soft_delete_institution_by_tenant_id(
        db=db, tenant_id=current_user.tenant_id
    )


# ── Security ──────────────────────────────────────────────────────────────────

@router.get(
    "/security",
    response_model=SecuritySettingResponse,
    status_code=status.HTTP_200_OK,
    summary="Get security settings",
)
async def get_security_settings(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("system:settings")),
):
    return await get_security_setting(db=db, tenant_id=current_user.tenant_id)


@router.patch(
    "/security",
    response_model=SecuritySettingResponse,
    status_code=status.HTTP_200_OK,
    summary="Update security settings",
)
async def update_security_settings(
    payload: SecuritySettingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("system:settings")),
):
    return await update_security_setting(
        tenant_id=current_user.tenant_id, payload=payload, db=db
    )