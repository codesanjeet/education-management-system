from typing import Generic, List, TypeVar

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.institution_model import InstitutionDB
from app.core.database import get_db
from app.rate_limiter import RateLimiter, user_id_key
from app.crud import institution_crud
from app.schemas.institution_schema import (
    InstitutionCreate,
    InstitutionResponse,
    InstitutionGeneralResponse,
    InstitutionUpdateSuperAdmin,
    ContactSubmissionCreate,
    ContactSubmissionResponse,
)
from app.core.exceptions import InstitutionNotFoundError
from ..crud.dashboard_crud import get_dashboard_data, get_recent_activity_for_dashboard
from ..deps import get_current_user, require_permission
from ..super_admin_deps import get_current_super_admin
from ..schemas.user_schema import CurrentUserResponse
from ..schemas.super_admin_schema import CurrentSuperAdminResponse
from ..models.user_model import UserRoleEnum
from ..services.email import send_welcome_email_for_owner

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    offset: int
    limit: int


public_limiter     = RateLimiter(max_calls=10, window_seconds=60)
public_get_limiter = RateLimiter(max_calls=30, window_seconds=60)

admin_read_limiter  = RateLimiter(max_calls=60, window_seconds=60)
admin_write_limiter = RateLimiter(max_calls=20, window_seconds=60)

dashboard_limiter = RateLimiter(max_calls=30, window_seconds=60)
contact_limiter   = RateLimiter(max_calls=10, window_seconds=60)

router = APIRouter()


# ── Public ────────────────────────────────────────────────────────────────────

@router.post(
    "/institutions",
    response_model=InstitutionGeneralResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new institution",
)
async def create_institution_endpoint(
    request: Request,
    institute_data: InstitutionCreate = Depends(InstitutionCreate.as_form),
    logo: UploadFile  = File(...),
    db:  AsyncSession = Depends(get_db),
):
    public_limiter.check(request)

    institution = await institution_crud.create_institution(
        db=db,
        institution_data=institute_data.model_dump(),
        logo=logo,
    )
    send_welcome_email_for_owner(to=institution.email, institute_name=institution.institute_name)
    return institution


@router.patch(
    "/logo",
    status_code=status.HTTP_200_OK,
    summary="Update institution logo",
)
async def update_logo(
    request: Request,
    logo: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    admin_write_limiter.check(request, key=user_id_key(current_user.id))

    institution = await institution_crud.update_logo(
        db=db,
        tenant_id=current_user.tenant_id,
        logo=logo,
    )
    return {"message": "Logo updated successfully", "logo": institution.logo}


@router.get(
    "/institutions/{tenant_id}/public",
    response_model=InstitutionGeneralResponse,
    summary="Get public institution info",
)
async def get_institution_public_endpoint(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
):
    public_get_limiter.check(request)

    return await institution_crud.get_institution_general_data_by_tenant_id(
        db=db, tenant_id=tenant_id
    )


# ── Super-admin ───────────────────────────────────────────────────────────────

@router.get(
    "/super-admin/institutions",
    response_model=PaginatedResponse[InstitutionResponse],
    summary="List all institutions (paginated)",
)
async def get_all_institutions_endpoint(
    request: Request,
    offset: int = Query(0, ge=0),
    limit:  int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    admin_read_limiter.check(request, key=user_id_key(current_user.id))

    rows, total = await institution_crud.get_all_institutions(db=db, offset=offset, limit=limit)
    return {"items": rows, "total": total, "offset": offset, "limit": limit}


@router.get(
    "/super-admin/institutions/{tenant_id}",
    response_model=InstitutionResponse,
    summary="Get institution by tenant_id",
)
async def get_institution_endpoint(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    admin_read_limiter.check(request, key=user_id_key(current_user.id))

    return await institution_crud.get_institution_by_tenant_id(db=db, tenant_id=tenant_id)


@router.post("/institutions/{tenant_id}/verify")
async def verify_institution(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    result = await db.execute(
        select(InstitutionDB).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst = result.scalars().first()
    if not inst:
        raise InstitutionNotFoundError("Institution not found")
    inst.is_verified = True
    inst.is_rejected = False
    await db.commit()
    return {"message": "Verified"}


@router.post("/institutions/{tenant_id}/reject")
async def reject_institution(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    result = await db.execute(
        select(InstitutionDB).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst = result.scalars().first()
    if not inst:
        raise InstitutionNotFoundError("Institution not found")
    inst.is_verified = False
    inst.is_rejected = True
    await db.commit()
    return {"message": "Rejected"}


@router.post("/institutions/{tenant_id}/restore")
async def restore_institution(
    tenant_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    result = await db.execute(
        select(InstitutionDB).where(InstitutionDB.tenant_id == tenant_id)
    )
    inst = result.scalars().first()
    if not inst:
        raise InstitutionNotFoundError("Institution not found")
    inst.is_verified = False
    inst.is_rejected = False
    await db.commit()
    return {"message": "Restored to pending"}


@router.patch(
    "/super-admin/institutions/{tenant_id}",
    response_model=InstitutionResponse,
    summary="Update institution metadata",
)
async def update_institution_endpoint(
    request: Request,
    tenant_id:          str  = ...,
    institute_name:     str  = Form(None),
    address:            str  = Form(None),
    city:               str  = Form(None),
    state:              str  = Form(None),
    pincode:            str  = Form(None),
    country:            str  = Form(None),
    phone:              str  = Form(None),
    phone_country_code: str  = Form(None),
    email:              str  = Form(None),
    primary_website:    str  = Form(None),
    institution_type:   str  = Form(None),
    year_established:   int  = Form(None),
    is_verified:        bool = Form(None),
    is_rejected:        bool = Form(None),
    is_block:           bool = Form(None),
    db: AsyncSession         = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    admin_write_limiter.check(request, key=user_id_key(current_user.id))

    institution = await institution_crud.get_institution_by_tenant_id(db, tenant_id)
    update_data = InstitutionUpdateSuperAdmin(
        institute_name=institute_name,
        address=address,
        city=city,
        state=state,
        pincode=pincode,
        country=country,
        phone=phone,
        phone_country_code=phone_country_code,
        email=email,
        primary_website=primary_website,
        institution_type=institution_type,
        year_established=year_established,
        is_verified=is_verified,
        is_rejected=is_rejected,
        is_block=is_block,
    )
    return await institution_crud.update_institution_by_tenant_id(db, institution, update_data)


@router.patch(
    "/super-admin/institutions/{tenant_id}/logo",
    summary="Replace institution logo",
)
async def update_logo_endpoint(
    request: Request,
    tenant_id: str,
    logo: UploadFile  = File(...),
    db:  AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    admin_write_limiter.check(request, key=user_id_key(current_user.id))

    institution = await institution_crud.update_logo(db=db, tenant_id=tenant_id, logo=logo)
    return {"message": "Logo updated successfully", "logo": institution.logo}


@router.delete(
    "/super-admin/institutions/{tenant_id}",
    summary="Hard-delete institution",
)
async def delete_institution_endpoint(
    request: Request,
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    admin_write_limiter.check(request, key=user_id_key(current_user.id))

    return await institution_crud.delete_institution_by_tenant_id(db=db, tenant_id=tenant_id)


# ── Institution-admin dashboard ───────────────────────────────────────────────

@router.get(
    "/institutions/dashboard/admin/me",
    summary="Dashboard stats for current admin/principal",
)
async def get_dashboard_stats_endpoint(
    request: Request,
    current_user: CurrentUserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dashboard_limiter.check(request, key=user_id_key(current_user.id))

    if current_user.role not in (UserRoleEnum.ADMIN.value, UserRoleEnum.PRINCIPAL.value):
        return {}
    return await get_dashboard_data(db, current_user.tenant_id, user_id=current_user.id)


@router.get(
    "/institutions/dashboard/recent-activity",
    summary="Recent activity log",
)
async def get_recent_activity_endpoint(
    request: Request,
    current_user: CurrentUserResponse = Depends(require_permission("recent_activity_logs:view")),
    db: AsyncSession = Depends(get_db),
):
    dashboard_limiter.check(request, key=user_id_key(current_user.id))

    return await get_recent_activity_for_dashboard(current_user.tenant_id, db)


# ── Marketing ─────────────────────────────────────────────────────────────────

@router.post(
    "/contact",
    response_model=ContactSubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a contact / enquiry form",
)
async def submit_contact_form(
    request: Request,
    data: ContactSubmissionCreate,
    db: AsyncSession = Depends(get_db),
):
    contact_limiter.check(request)
    return await institution_crud.create_contact(db=db, data=data)


@router.get(
    "/super-admin/contacts",
    response_model=PaginatedResponse[ContactSubmissionResponse],
    summary="List all contact form submissions",
)
async def get_all_contacts_endpoint(
    request: Request,
    offset: int = Query(0, ge=0),
    limit:  int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentSuperAdminResponse = Depends(get_current_super_admin),
):
    admin_read_limiter.check(request, key=user_id_key(current_user.id))
    rows, total = await institution_crud.get_all_contacts(db=db, offset=offset, limit=limit)
    return {"items": rows, "total": total, "offset": offset, "limit": limit}