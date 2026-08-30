from fastapi import APIRouter, Depends, status, UploadFile, File, Query, BackgroundTasks, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
import os
import re
import httpx
from ..core.database import get_db
from app.rate_limiter import RateLimiter
from ..schemas.institution_schema import (
    CreateNotificationData,
    UpdateNotificationData,
    NotificationResponse,
    DeleteNotificationResponse,
    NotificationListResponse,
    FileUploadResponse,
    AnnouncementType,
    Audience,
    NotificationReadResponse,
)
from ..crud.notification_crud import (
    create_notification,
    update_notification,
    delete_notification,
    get_notification_by_id,
    get_all_notifications,
    get_notifications_by_audience,
    save_uploaded_file,
    get_file_upload_info,
    get_file_url_for_download,
    get_all_notification_reads,
    mark_notification_as_read,
    get_usage_info,
    stream_notification_file,
    verify_email_download_token,
    generate_email_download_token,
)
from ..schemas.user_schema import CurrentUserResponse
from ..models.institution_model import InstitutionDB
from ..deps import (
    require_permission,
    require_any_permission,
    get_current_user,
    require_permission_or_owner,
)
from ..core.exceptions import (
    InsufficientPermissionError,
    UserNotFoundException,
)
from pydantic import BaseModel

router = APIRouter(prefix="/institutions")

PORTAL_BASE_URL   = os.getenv("BACKEND_BASE_URL",  "http://localhost:8000")
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

# ── Safe filename chars: letters, digits, dot, hyphen, underscore, space ─────
_SAFE_FILENAME_RE = re.compile(r'[^\w.\- ]')


def _sanitise_filename(raw: str) -> str:
    """
    Strip characters that are unsafe in a Content-Disposition header value.
    Prevents header injection if a malicious filename like:
      evil.pdf\r\nX-Injected: header
    is stored in the DB.
    """
    name = _SAFE_FILENAME_RE.sub("_", raw)
    # Collapse any path separators that slipped through
    name = name.replace("/", "_").replace("\\", "_")
    return name or "download"


# ── Rate limiter instances ────────────────────────────────────────────────────
file_upload_limiter         = RateLimiter(max_calls=20, window_seconds=60)
notification_create_limiter = RateLimiter(max_calls=10, window_seconds=60)
notification_update_limiter = RateLimiter(max_calls=20, window_seconds=60)
whatapp_config_limiter      = RateLimiter(max_calls=10, window_seconds=60)
# ─────────────────────────────────────────────────────────────────────────────


# ── Permission helpers ────────────────────────────────────────────────────────

ROLE_AUDIENCE_PERMISSIONS = {
    "admin": {
        Audience.ALL, Audience.ADMIN, Audience.ALL_STAFF,
        Audience.TEACHER, Audience.OTHER_STAFF, Audience.STUDENT, Audience.PRINCIPAL,
    },
    "principal": {
        Audience.ALL, Audience.ALL_STAFF, Audience.PRINCIPAL,
        Audience.TEACHER, Audience.OTHER_STAFF, Audience.STUDENT,
    },
    "teacher":     {Audience.ALL, Audience.ALL_STAFF, Audience.TEACHER},
    "other_staff": {Audience.ALL, Audience.ALL_STAFF, Audience.OTHER_STAFF},
    "student":     {Audience.ALL, Audience.STUDENT},
}


def can_access_audience(user_role: str, audience: Audience) -> bool:
    return audience in ROLE_AUDIENCE_PERMISSIONS.get(user_role, set())


def get_required_permission_for_audience(audience: Audience) -> str:
    return {
        Audience.ALL:         "notification:admin_level",
        Audience.ADMIN:       "notification:admin_level",
        Audience.PRINCIPAL:   "notification:admin_level",
        Audience.ALL_STAFF:   "notification:all_staff_level",
        Audience.TEACHER:     "notification:all_staff_level",
        Audience.OTHER_STAFF: "notification:all_staff_level",
        Audience.STUDENT:     "notification:student_level",
    }.get(audience, "notification:admin_level")


# ── Request bodies ────────────────────────────────────────────────────────────

class UpdateNotificationRequest(BaseModel):
    notif_type:      Optional[str] = None          # FIX 4: was `type`, shadowed Python builtin
    audience:        Optional[str] = None
    class_id:        Optional[int] = None
    title:           Optional[str] = None
    message:         Optional[str] = None
    attached_file:   Optional[str] = None
    send_email:      bool = False
    send_whatsapp:   bool = False
    include_parents: bool = False
    whatsapp_target: str  = "both"


# ── Usage ─────────────────────────────────────────────────────────────────────

@router.get("/notifications/usage", status_code=status.HTTP_200_OK)
async def get_notification_usage_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission("notification:admin_level", "notification:all_staff_level")
    ),
):
    """Email credits remaining + storage used for this institution."""
    inst_id = (await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not inst_id:
        return {"email_balance": 0, "storage_used_mb": 0.0, "ai_credits_balance": 0}
    return await get_usage_info(db, inst_id)


# ── File upload ───────────────────────────────────────────────────────────────

@router.post(
    "/notifications/files",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_notification_file_endpoint(
    request: Request,
    file: UploadFile = File(...),
    notification_type: str = Query(
        default="official",
        description=(
            "Notification type — determines which R2 bucket the file goes into. "
            "'academic' and 'alert' → private bucket (signed URL). "
            "All others → public CDN bucket (permanent URL)."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission(
            "notification:admin_level",
            "notification:all_staff_level",
            "notification:student_level",
        )
    ),
):
    file_upload_limiter.check(request, key=f"tenant:{current_user.tenant_id}")

    inst_id = (await db.execute(
        select(InstitutionDB.id).where(InstitutionDB.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()

    content = await file.read()
    r2_key, mime, size = await save_uploaded_file(
        filename=file.filename,
        file_content=content,
        tenant_id=current_user.tenant_id,
        institution_id=inst_id,
        db=db,
        notification_type=notification_type,
    )
    return FileUploadResponse(
        filename=file.filename, file_path=r2_key, mime_type=mime, size=size
    )


# ── File download (auth-gated portal) ────────────────────────────────────────

@router.get("/notifications/{notification_id}/file", status_code=200)
async def download_notification_file_endpoint(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    """Returns a short-lived URL (signed for private, CDN for public)."""
    if "notification:admin_level" not in current_user.permissions:
        notif = await get_notification_by_id(
            notification_id=notification_id,
            tenant_id=current_user.tenant_id,
            db=db,
        )
        if not notif:
            raise UserNotFoundException("Notification not found")
        if not can_access_audience(current_user.role, notif.audience):
            raise InsufficientPermissionError("Cannot access this file")

    url = await get_file_url_for_download(
        tenant_id=current_user.tenant_id,
        notification_id=notification_id,
        db=db,
    )
    return {"url": url}


# ── Notification CRUD ─────────────────────────────────────────────────────────

@router.post(
    "/notifications",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_notification_endpoint(
    request: Request,
    notification_data: CreateNotificationData,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_any_permission(
            "notification:admin_level",
            "notification:all_staff_level",
            "notification:student_level",
        )
    ),
):
    notification_create_limiter.check(request, key=f"tenant:{current_user.tenant_id}")

    perm = get_required_permission_for_audience(notification_data.audience)
    if perm not in current_user.permissions:
        raise InsufficientPermissionError("You don't have permission for this audience")

    return await create_notification(
        db=db,
        notification_data=notification_data,
        tenant_id=current_user.tenant_id,
        current_user_id=current_user.id,
        portal_base_url=PORTAL_BASE_URL,
        background_tasks=background_tasks,
    )


@router.post("/notifications/mark-read", status_code=status.HTTP_201_CREATED)
async def mark_notification_as_read_endpoint(
    db: AsyncSession = Depends(get_db),
    notification_ids: list[int] = Query(...),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    return await mark_notification_as_read(
        db=db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        notification_ids=notification_ids,
    )


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_all_notifications_endpoint(
    page:       int = Query(1, ge=1),
    page_size:  int = Query(10, ge=1, le=100),
    audience:   Optional[Audience]         = None,
    notif_type: Optional[AnnouncementType] = Query(None, alias="type"),  # FIX 4: renamed
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission("notification:admin_level")),
):
    skip  = (page - 1) * page_size
    nlist = await get_all_notifications(
        tenant_id=current_user.tenant_id, db=db, skip=skip, limit=page_size,
        audience_filter=audience.value if audience else None,
        type_filter    =notif_type.value if notif_type else None,
    )
    ids   = [n.id for n in nlist.notifications]
    reads = await get_all_notification_reads(
        tenant_id=current_user.tenant_id, db=db,
        user_id=current_user.id, notification_ids=ids,
    )
    rmap = {r.notification_id: r.read_at for r in reads}
    for n in nlist.notifications:
        n.read_at = rmap.get(n.id)

    total       = nlist.total
    total_pages = (total + page_size - 1) // page_size
    return NotificationListResponse(
        notifications=nlist.notifications, total=total,
        page=page, page_size=page_size, total_pages=total_pages,
    )


# FIX 1: /file-info MUST be declared before /{notification_id} routes.
# FastAPI matches routes in registration order. Without this, a request to
# GET /notifications/file-info would match /{notification_id} first and
# attempt int("file-info") → 422 Unprocessable Entity every time.
@router.get("/notifications/file-info", status_code=status.HTTP_200_OK)
async def get_file_info_endpoint():
    return get_file_upload_info()


@router.get(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
)
async def get_notification_endpoint(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    notif = await get_notification_by_id(
        notification_id=notification_id,
        tenant_id=current_user.tenant_id,
        db=db,
    )
    if not notif:
        raise UserNotFoundException(f"Notification {notification_id} not found")
    if "notification:admin_level" not in current_user.permissions:
        if not can_access_audience(current_user.role, notif.audience):
            raise InsufficientPermissionError("Cannot access this notification")
    return notif


@router.patch(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
)
async def update_notification_endpoint(
    request: Request,
    user_id: int,
    notification_id: int,
    body: UpdateNotificationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("notification:admin_level")),
):
    notification_update_limiter.check(
        request, key=f"tenant:{access['current_user'].tenant_id}"
    )

    if not (access["is_owner"] or access["has_permission"]):
        raise InsufficientPermissionError("Cannot update this notification")

    nd = UpdateNotificationData(
        type=body.notif_type,          # FIX 4: use renamed field
        audience=body.audience,
        class_id=body.class_id,
        title=body.title,
        message=body.message,
        attached_file=body.attached_file,
    )
    return await update_notification(
        tenant_id=access["current_user"].tenant_id,
        db=db,
        notification_data=nd,
        notification_id=notification_id,
        send_email=body.send_email,
        send_whatsapp=body.send_whatsapp,
        include_parents=body.include_parents,
        whatsapp_target=body.whatsapp_target,
        portal_base_url=PORTAL_BASE_URL,
        background_tasks=background_tasks,
    )


@router.delete(
    "/notifications/{notification_id}",
    response_model=DeleteNotificationResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_notification_endpoint(
    user_id: int,
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    access: dict = Depends(require_permission_or_owner("notification:admin_level")),
):
    if not (access["is_owner"] or access["has_permission"]):
        raise InsufficientPermissionError("Cannot delete this notification")

    return await delete_notification(
        tenant_id=access["current_user"].tenant_id,
        notification_id=notification_id,
        db=db,
    )


@router.get(
    "/notifications/audience/{audience}",
    response_model=list[NotificationResponse],
    status_code=status.HTTP_200_OK,
)
async def get_notifications_by_audience_endpoint(
    audience: Audience,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    if "notification:admin_level" not in current_user.permissions:
        if not can_access_audience(current_user.role, audience):
            raise InsufficientPermissionError("Cannot access this audience")

    notifications = await get_notifications_by_audience(
        tenant_id=current_user.tenant_id, audience=audience.value, db=db, limit=limit,
    )
    ids   = [n.id for n in notifications]
    reads = await get_all_notification_reads(
        tenant_id=current_user.tenant_id, db=db,
        user_id=current_user.id, notification_ids=ids,
    )
    rmap = {r.notification_id: r.read_at for r in reads}
    for n in notifications:
        n.read_at = rmap.get(n.id)
    return notifications


# ── File download — auth-gated stream ────────────────────────────────────────

@router.get("/notifications/{notification_id}/file/download")
async def download_notification_file_stream_endpoint(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    if "notification:admin_level" not in current_user.permissions:
        notif = await get_notification_by_id(
            notification_id=notification_id,
            tenant_id=current_user.tenant_id,
            db=db,
        )
        if not notif:
            raise UserNotFoundException("Notification not found")
        if not can_access_audience(current_user.role, notif.audience):
            raise InsufficientPermissionError("Cannot access this file")

    url, content_type, filename, file_size = await stream_notification_file(
        tenant_id=current_user.tenant_id,
        notification_id=notification_id,
        db=db,
    )

    safe_filename = _sanitise_filename(filename)          # FIX 3: sanitise before header

    async def _stream():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as resp:
                async for chunk in resp.aiter_bytes(65536):
                    yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"',
        "Cache-Control": "private, no-cache",
    }
    if file_size:
        headers["Content-Length"] = str(file_size)

    return StreamingResponse(_stream(), media_type=content_type, headers=headers)


# ── File download — email JWT link (no login required) ───────────────────────

@router.get("/notifications/{notification_id}/file/email-download")
async def email_download_endpoint(
    notification_id: int,
    token: str = Query(..., description="PyJWT-signed download token from the notification email"),
    db: AsyncSession = Depends(get_db),
):
    """
    No login required — link is signed with PyJWT (HS256, 7-day TTL).
    Expired/invalid token → 302 redirect to the /file-expired page.
    Valid token → streaming file download with Content-Disposition: attachment.
    """
    payload = verify_email_download_token(token)

    if not payload:
        return RedirectResponse(
            url=f"{FRONTEND_BASE_URL}/file-expired",
            status_code=302,
        )

    if payload.get("nid") != notification_id:
        raise UserNotFoundException("Token does not match notification")

    tenant_id = payload.get("tid")
    if not tenant_id:
        raise UserNotFoundException("Invalid token payload")

    url, content_type, filename, file_size = await stream_notification_file(
        tenant_id=tenant_id,
        notification_id=notification_id,
        db=db,
    )

    safe_filename = _sanitise_filename(filename)         

    async def _stream():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url) as resp:
                async for chunk in resp.aiter_bytes(65536):
                    yield chunk

    headers = {
        "Content-Disposition": f'attachment; filename="{safe_filename}"',
        "Cache-Control": "private, no-cache",
    }
    if file_size:
        headers["Content-Length"] = str(file_size)

    return StreamingResponse(_stream(), media_type=content_type, headers=headers)


# ══════════════════════════════════════════════════════════════════════════════
# AUTOMATION / WHATSAPP CONFIG ROUTER
# ══════════════════════════════════════════════════════════════════════════════

import logging
import math
from typing import List

from fastapi import HTTPException

from ..routers.fee_router import get_institution_id
from ..schemas.institution_schema import (
    WhatsAppConfigCreate,
    WhatsAppConfigResponse,
)
from ..crud.notification_crud import (
    create_whatsapp_config,
    DatabaseError,
)

logger = logging.getLogger(__name__)

automation_router = APIRouter(prefix="/institutions/notifications")


def _not_found(detail: str):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

def _bad_request(detail: str):
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

def _server_error(detail: str):
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)

def _not_implemented(detail: str):
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=detail)


# FIX 2: WhatsApp config creation requires system:settings permission.
# Previously used get_current_user — any authenticated user (student, teacher)
# could POST /whatsapp/config and overwrite the institution's WA credentials.
@automation_router.post(
    "/whatsapp/config",
    status_code=status.HTTP_201_CREATED,
    response_model=WhatsAppConfigResponse,
    summary="Create/replace WhatsApp provider config",
)
async def create_wa_config_endpoint(
    request: Request,
    data: WhatsAppConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(
        require_permission("system:settings")   # FIX 2: was get_current_user
    ),
):
    whatapp_config_limiter.check(request, key=f"tenant:{current_user.tenant_id}")
    institution_id = await get_institution_id(db, current_user.tenant_id)
    try:
        config = await create_whatsapp_config(db, institution_id, current_user.tenant_id, data)
        return WhatsAppConfigResponse.model_validate(config)
    except DatabaseError as e:
        _server_error(str(e))


# @automation_router.get(
#     "/whatsapp/config",
#     response_model=Optional[WhatsAppConfigResponse],
#     summary="Get active WhatsApp config (credentials excluded)",
# )
# async def get_wa_config_endpoint(
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     config = await get_active_wa_config(db, institution_id)
#     return WhatsAppConfigResponse.model_validate(config) if config else None


# @automation_router.patch(
#     "/whatsapp/config/{config_id}",
#     response_model=WhatsAppConfigResponse,
#     summary="Update WhatsApp config",
# )
# async def update_wa_config_endpoint(
#     config_id: int,
#     data: WhatsAppConfigUpdate,
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     try:
#         config = await update_whatsapp_config(db, config_id, institution_id, data)
#         return WhatsAppConfigResponse.model_validate(config)
#     except WhatsAppConfigNotFound:
#         _not_found("WhatsApp config not found")
#     except DatabaseError as e:
#         _server_error(str(e))


# @automation_router.delete(
#     "/whatsapp/config/{config_id}",
#     status_code=status.HTTP_204_NO_CONTENT,
#     summary="Delete WhatsApp config",
# )
# async def delete_wa_config_endpoint(
#     config_id: int,
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     try:
#         await delete_whatsapp_config(db, config_id, institution_id)
#     except WhatsAppConfigNotFound:
#         _not_found("WhatsApp config not found")
#     except DatabaseError as e:
#         _server_error(str(e))


# @automation_router.post(
#     "/whatsapp/config/{config_id}/verify",
#     response_model=WhatsAppConfigVerifyResponse,
#     summary="Test WhatsApp provider credentials",
# )
# async def verify_wa_config_endpoint(
#     config_id: int,
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     try:
#         config = await get_wa_config_by_id(db, config_id, institution_id)
#     except WhatsAppConfigNotFound:
#         _not_found("WhatsApp config not found")

#     # ── Implement per-provider verification here ──────────────────────────────
#     # Twilio example:
#     # from twilio.rest import Client
#     # try:
#     #     Client(config.config["account_sid"], config.config["auth_token"])
#     #         .api.accounts(config.config["account_sid"]).fetch()
#     #     await set_wa_config_status(db, config_id, "connected")
#     # except Exception as e:
#     #     await set_wa_config_status(db, config_id, "failed", str(e))
#     # ─────────────────────────────────────────────────────────────────────────

#     await set_wa_config_status(db, config_id, "connected")
#     return WhatsAppConfigVerifyResponse(
#         status=ConfigStatusEnum.CONNECTED,
#         message="Configuration saved. Implement provider verification here.",
#         provider=config.provider,
#     )


# # ══════════════════════════════════════════════════════════════
# # SMS CONFIG ENDPOINTS  — Stub (501 Not Implemented)
# # ══════════════════════════════════════════════════════════════

# @automation_router.get(
#     "/sms/config",
#     summary="[COMING SOON] SMS config — not yet available",
#     include_in_schema=True,
# )
# async def get_sms_config_stub():
#     _not_implemented("SMS channel is not yet available. Coming soon.")


# @automation_router.post(
#     "/sms/config",
#     summary="[COMING SOON] SMS config — not yet available",
#     include_in_schema=True,
# )
# async def create_sms_config_stub():
#     _not_implemented("SMS channel is not yet available. Coming soon.")


# # ══════════════════════════════════════════════════════════════
# # AUTOMATION RULE ENDPOINTS  — channel-agnostic
# #
# # CRON SETUP (Linux crontab):
# # Each rule stores a cron_expression field. To run automation,
# # set up a cron job that calls the dispatch endpoint or a
# # management command at the desired interval.
# #
# # Example crontab entry (runs the dispatcher every minute,
# # which then checks which rules are due based on cron_expression):
# #
# #   * * * * * /path/to/venv/bin/python /path/to/manage.py dispatch_automation_rules
# #
# # Or call an internal endpoint from a cron script:
# #   * * * * * curl -s -X POST http://localhost:8000/internal/automation/dispatch \
# #               -H "X-Internal-Token: $INTERNAL_TOKEN"
# #
# # The dispatch logic should:
# #   1. Fetch all enabled rules
# #   2. For each rule, check if now matches its cron_expression
# #   3. Fetch the audience (students/parents) based on rule.audience
# #   4. Call _dispatch_notification_emails() for email channel
# #   5. Call WhatsApp send for whatsapp channel (using active WA config)
# #   6. Log each send via create_message_log()
# #   7. Call increment_rule_sent_count() with the total sent
# # ══════════════════════════════════════════════════════════════

# @automation_router.post(
#     "/rules",
#     status_code=status.HTTP_201_CREATED,
#     response_model=AutomationRuleResponse,
#     summary="Create a multi-channel automation rule",
# )
# async def create_rule_endpoint(
#     data: AutomationRuleCreate,
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)

#     # WhatsApp requires an active config; email uses system email (no config check needed)
#     if "whatsapp" in [ch.value for ch in data.channels]:
#         wa_config = await get_active_wa_config(db, institution_id)
#         if not wa_config:
#             _bad_request(
#                 "No active WhatsApp config. "
#                 "Configure WhatsApp under Settings before adding a WhatsApp rule."
#             )

#     try:
#         rule = await create_rule(db, institution_id, data)
#         return AutomationRuleResponse.model_validate(rule)
#     except DatabaseError as e:
#         _server_error(str(e))


# @automation_router.get(
#     "/rules",
#     response_model=List[AutomationRuleResponse],
#     summary="List all automation rules (optionally filter by channel)",
# )
# async def list_rules_endpoint(
#     channel: Optional[str] = Query(None, description="Filter by channel: whatsapp | email | sms"),
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     rules = await get_rules(db, institution_id, channel=channel)
#     return [AutomationRuleResponse.model_validate(r) for r in rules]


# @automation_router.patch(
#     "/rules/{rule_id}",
#     response_model=AutomationRuleResponse,
#     summary="Update a rule (partial update)",
# )
# async def update_rule_endpoint(
#     rule_id: int,
#     data: AutomationRuleUpdate,
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     try:
#         rule = await update_rule(db, rule_id, institution_id, data)
#         return AutomationRuleResponse.model_validate(rule)
#     except AutomationRuleNotFound:
#         _not_found("Automation rule not found")
#     except DatabaseError as e:
#         _server_error(str(e))


# @automation_router.post(
#     "/rules/{rule_id}/toggle",
#     response_model=AutomationRuleResponse,
#     summary="Toggle rule enabled/disabled",
# )
# async def toggle_rule_endpoint(
#     rule_id: int,
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     try:
#         rule = await toggle_rule(db, rule_id, institution_id)
#         return AutomationRuleResponse.model_validate(rule)
#     except AutomationRuleNotFound:
#         _not_found("Automation rule not found")
#     except DatabaseError as e:
#         _server_error(str(e))


# @automation_router.delete(
#     "/rules/{rule_id}",
#     status_code=status.HTTP_204_NO_CONTENT,
#     summary="Delete a rule",
# )
# async def delete_rule_endpoint(
#     rule_id: int,
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     try:
#         await delete_rule(db, rule_id, institution_id)
#     except AutomationRuleNotFound:
#         _not_found("Automation rule not found")
#     except DatabaseError as e:
#         _server_error(str(e))


# # ══════════════════════════════════════════════════════════════
# # MESSAGE LOG ENDPOINTS
# # ══════════════════════════════════════════════════════════════

# @automation_router.get(
#     "/logs",
#     response_model=MessageLogListResponse,
#     summary="Get paginated message send logs (all channels)",
# )
# async def list_logs_endpoint(
#     page:      int            = Query(1, ge=1),
#     page_size: int            = Query(20, ge=1, le=100),
#     rule_id:   Optional[int]  = Query(None, description="Filter by rule. Use 0 for manual sends only."),
#     channel:   Optional[str]  = Query(None, description="Filter by channel: whatsapp | email | sms"),
#     db: AsyncSession = Depends(get_db),
#     current_user: CurrentUserResponse = Depends(get_current_user),
# ):
#     institution_id = await get_institution_id(db, current_user.tenant_id)
#     items, total = await get_message_logs(
#         db, institution_id, page, page_size, rule_id, channel
#     )
#     return MessageLogListResponse(
#         items=[MessageLogResponse.model_validate(i) for i in items],
#         pagination=PaginationMeta(
#             total=total,
#             page=page,
#             page_size=page_size,
#             total_pages=math.ceil(total / page_size) if total else 0,
#         ),
#     )


# # ══════════════════════════════════════════════════════════════
# # WEBHOOK ENDPOINTS
# # ══════════════════════════════════════════════════════════════

# @automation_router.post(
#     "/webhook/twilio",
#     status_code=status.HTTP_200_OK,
#     include_in_schema=False,
#     summary="Receive Twilio delivery status webhooks (WhatsApp + SMS)",
# )
# async def twilio_webhook(request: Request, db: AsyncSession = Depends(get_db)):
#     form           = await request.form()
#     message_sid    = form.get("MessageSid")
#     message_status = form.get("MessageStatus")
#     error_code     = form.get("ErrorCode")
#     error_message  = form.get("ErrorMessage")

#     if not message_sid or not message_status:
#         return {"ok": False, "reason": "missing fields"}

#     status_map = {
#         "sent":      MessageStatusEnum.SENT,
#         "delivered": MessageStatusEnum.DELIVERED,
#         "failed":    MessageStatusEnum.FAILED,
#         "read":      MessageStatusEnum.READ,
#         "queued":    MessageStatusEnum.QUEUED,
#     }
#     await update_message_status_by_provider_id(
#         db=db,
#         provider_message_id=message_sid,
#         status=status_map.get(message_status, MessageStatusEnum.SENT),
#         error_message=f"[{error_code}] {error_message}" if error_code else None,
#     )
#     return {"ok": True}


# @automation_router.post(
#     "/webhook/meta",
#     status_code=status.HTTP_200_OK,
#     include_in_schema=False,
# )
# async def meta_webhook(request: Request, db: AsyncSession = Depends(get_db)):
#     body = await request.json()
#     try:
#         for entry in body.get("entry", []):
#             for change in entry.get("changes", []):
#                 value = change.get("value", {})
#                 for upd in value.get("statuses", []):
#                     message_id   = upd.get("id")
#                     meta_status  = upd.get("status")
#                     error_info   = upd.get("errors", [{}])[0]
#                     status_map   = {
#                         "sent":      MessageStatusEnum.SENT,
#                         "delivered": MessageStatusEnum.DELIVERED,
#                         "read":      MessageStatusEnum.READ,
#                         "failed":    MessageStatusEnum.FAILED,
#                     }
#                     if message_id:
#                         await update_message_status_by_provider_id(
#                             db=db,
#                             provider_message_id=message_id,
#                             status=status_map.get(meta_status, MessageStatusEnum.SENT),
#                             error_message=error_info.get("message") if error_info else None,
#                         )
#     except Exception as e:
#         logger.error(f"meta_webhook parse error: {e}", exc_info=True)
#     return {"ok": True}


# @automation_router.get(
#     "/webhook/meta",
#     include_in_schema=False,
# )
# async def meta_webhook_verify(
#     hub_mode:         str = Query(alias="hub.mode"),
#     hub_challenge:    str = Query(alias="hub.challenge"),
#     hub_verify_token: str = Query(alias="hub.verify_token"),
# ):
#     import os
#     verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "")
#     if hub_mode == "subscribe" and hub_verify_token == verify_token:
#         return int(hub_challenge)
#     raise HTTPException(status_code=403, detail="Verification failed")


# @automation_router.post(
#     "/webhook/gupshup",
#     status_code=status.HTTP_200_OK,
#     include_in_schema=False,
# )
# async def gupshup_webhook(request: Request, db: AsyncSession = Depends(get_db)):
#     body = await request.json()
#     try:
#         message_id     = body.get("messageId")
#         gupshup_status = body.get("type")
#         error          = body.get("payload", {}).get("reason")
#         status_map     = {
#             "message-delivered": MessageStatusEnum.DELIVERED,
#             "message-failed":    MessageStatusEnum.FAILED,
#             "message-sent":      MessageStatusEnum.SENT,
#             "message-read":      MessageStatusEnum.READ,
#         }
#         if message_id:
#             await update_message_status_by_provider_id(
#                 db=db,
#                 provider_message_id=message_id,
#                 status=status_map.get(gupshup_status, MessageStatusEnum.SENT),
#                 error_message=error,
#             )
#     except Exception as e:
#         logger.error(f"gupshup_webhook parse error: {e}", exc_info=True)
#     return {"ok": True}