from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import List, Optional, Set
import uuid
from fastapi import (
    APIRouter, Depends, HTTPException,
    Query, Request, WebSocket, WebSocketDisconnect, status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..deps import get_current_user, require_permission
from ..schemas.user_schema import CurrentUserResponse

from ..crud.ai_agent_crud import (
    DEFAULT_SIMILARITY_THRESHOLD,
    ServiceUnavailableError,
    LLMConfigError,
    InProcessRateLimiter,
    _chat_rate_limiter,
    _bulk_rate_limiter,
    add_knowledge_chunk,
    create_agent,
    delete_knowledge_chunk,
    end_session,
    get_agent,
    get_agent_stats,
    get_conversation_history,
    handle_chat,
    ignore_unanswered_question,
    list_knowledge_chunks,
    list_unanswered_questions,
    process_chat_turn,
    resolve_unanswered_question,
    start_session,
    update_agent,
    update_knowledge_chunk,
    append_conversation,
    UNANSWERED_SENTINEL,
    bulk_add_knowledge_chunks,
    preview_chunks,
)
from ..schemas.ai_agent_schema import (
    AgentCreate,
    AgentResponse,        
    AgentStatsResponse,
    AgentUpdate,
    AgentChannel,
    ChatRequest,
    ChatResponse,
    KnowledgeChunkCreate,
    KnowledgeChunkListResponse,
    KnowledgeChunkResponse,
    KnowledgeChunkUpdate,
    QuestionStatus,
    ResolveQuestionRequest,
    SessionEndRequest,
    SessionStartRequest,
    UnansweredQuestionResponse,
    UnansweredQuestionsListResponse,
)
from ..routers.fee_router import get_institution_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Agent"])

_AI_MANAGE = "voice_agent:ai_voice_agent_manage"

AGENT_REFRESH_EVERY_N_TURNS: int = 5

_TRUSTED_PROXY_IPS: Set[str] = {
    ip.strip()
    for ip in os.environ.get("TRUSTED_PROXY_IPS", "").split(",")
    if ip.strip()
}


# ─────────────────────────────────────────────────────────────────────────────
# Bulk import schemas
# ─────────────────────────────────────────────────────────────────────────────

class BulkKnowledgePreviewRequest(BaseModel):
    raw_text: str = Field(..., min_length=10, max_length=80_000)
    max_chars_per_chunk: int = Field(800, ge=400, le=2000)


class ChunkPreview(BaseModel):
    index: int
    char_count: int
    token_estimate: int
    preview: str


class BulkPreviewResponse(BaseModel):
    chunk_count: int
    total_chars: int
    total_tokens_estimate: int
    estimated_cost_usd: float
    will_be_capped: bool
    chunks: List[ChunkPreview]


class BulkKnowledgeImportRequest(BaseModel):
    raw_text: str = Field(..., min_length=10, max_length=80_000)
    title_prefix: Optional[str] = Field(None, max_length=100)
    source: str = Field("bulk_import", max_length=100)
    meta: Optional[dict] = None
    max_chars_per_chunk: int = Field(800, ge=400, le=2000)

    @field_validator("raw_text")
    @classmethod
    def no_empty_text(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("raw_text must not be blank.")
        return v


class BulkImportResponse(BaseModel):
    total_chunks: int
    stored: int
    skipped: int
    errors: List[str]
    chunk_ids: List[int]
    batch_id: str
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# IP extraction
# ─────────────────────────────────────────────────────────────────────────────

def _get_client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    if direct_ip in _TRUSTED_PROXY_IPS:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_ip


def _get_ws_client_ip(websocket: WebSocket) -> str:
    direct_ip = websocket.client.host if websocket.client else "unknown"
    if direct_ip in _TRUSTED_PROXY_IPS:
        forwarded = websocket.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return direct_ip


# ─────────────────────────────────────────────────────────────────────────────
# Institution lookup
# ─────────────────────────────────────────────────────────────────────────────

async def _get_institution_by_page_name(db: AsyncSession, page_name: str):
    from sqlalchemy import select as sa_select
    from ..models.institution_model import InstitutionDB, InstitutionInfoDB

    result = await db.execute(
        sa_select(InstitutionDB)
        .join(InstitutionInfoDB, InstitutionInfoDB.institution_id == InstitutionDB.id)
        .where(
            (InstitutionInfoDB.institution_page_url == page_name) |
            (InstitutionInfoDB.institution_page_url.like(f"%/{page_name}")) |
            (InstitutionInfoDB.institution_page_url.like(f"%/{page_name}/"))
        )
    )
    return result.scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_agent_or_404(db: AsyncSession, institution_id: int):
    agent = await get_agent(db, institution_id)
    if not agent:
        raise HTTPException(status_code=404, detail="No AI agent configured for this institution.")
    return agent


def _llm_exception_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, ServiceUnavailableError):
        return HTTPException(
            status_code=503,
            detail="AI service temporarily unavailable. Please try again shortly.",
            headers={"Retry-After": "30"},
        )
    if isinstance(exc, LLMConfigError):
        logger.critical("LLM configuration error — ops action required: %s", exc)
        return HTTPException(
            status_code=500,
            detail="AI service configuration error. The team has been notified.",
        )
    return HTTPException(status_code=500, detail="Unexpected error.")


# ─────────────────────────────────────────────────────────────────────────────
# Shared WebSocket handler
# ─────────────────────────────────────────────────────────────────────────────

async def _websocket_handler(websocket: WebSocket, page_name: str, db: AsyncSession) -> None:
    await websocket.accept()

    client_ip = _get_ws_client_ip(websocket)
    logger.info("WS accepted: page_name=%s ip=%s", page_name, client_ip)

    try:
        institution = await _get_institution_by_page_name(db, page_name)
    except Exception as exc:
        logger.error("WS institution lookup error: %s", exc, exc_info=True)
        institution = None

    if not institution:
        await websocket.send_text(json.dumps({"type": "error", "data": "Page not found."}))
        await websocket.close(code=4004)
        return

    agent = await get_agent(db, institution.id)
    if not agent:
        await websocket.send_text(json.dumps({"type": "error", "data": "AI assistant not configured."}))
        await websocket.close(code=4004)
        return
    if not agent.is_active:
        await websocket.send_text(json.dumps({"type": "error", "data": "AI assistant is disabled."}))
        await websocket.close(code=4004)
        return

    await websocket.send_text(json.dumps({"type": "ready", "data": "connected"}))

    turn_count = 0

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > 8_192:
                await websocket.send_text(json.dumps({"type": "error", "data": "Message too large."}))
                continue

            rl_key = f"{page_name}:{client_ip}"
            if not await _chat_rate_limiter.is_allowed(rl_key):
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": "Rate limit exceeded. Please slow down.",
                }))
                continue

            turn_count += 1
            if turn_count % AGENT_REFRESH_EVERY_N_TURNS == 0:
                refreshed = await get_agent(db, institution.id)
                if not refreshed or not refreshed.is_active:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "data": "AI assistant has been disabled.",
                    }))
                    await websocket.close(code=4003)
                    return
                agent = refreshed

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "data": "Invalid JSON."}))
                continue

            question    = payload.get("question", "").strip()
            session_id  = (payload.get("session_id") or "ws-default")[:128]
            if len(session_id) < 4:
                session_id = "ws-default"
            channel_str = payload.get("channel", "chat")

            if not question:
                await websocket.send_text(json.dumps({"type": "error", "data": "Empty question."}))
                continue

            try:
                channel = AgentChannel(channel_str)
                if channel not in (AgentChannel.CHAT, AgentChannel.CALL):
                    channel = AgentChannel.CHAT
            except ValueError:
                channel = AgentChannel.CHAT

            try:
                response = await process_chat_turn(db, agent, question, session_id, channel)
            except (ServiceUnavailableError, LLMConfigError) as exc:
                http_exc = _llm_exception_to_http(exc)
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": http_exc.detail,
                }))
                continue
            except Exception as exc:
                logger.error(
                    "WS process_chat_turn error: page=%s session=%s err=%s",
                    page_name, session_id, exc, exc_info=True,
                )
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": "Internal server error.",
                }))
                continue

            if response.action:
                await websocket.send_text(json.dumps(response.action))

            for word in response.answer.split(" "):
                await websocket.send_text(json.dumps({"type": "token", "data": word + " "}))
                await asyncio.sleep(0.025)

            await websocket.send_text(json.dumps({
                "type":     "done",
                "data":     response.answer,
                "answered": response.answered,
                "sources":  response.sources or [],
            }))

    except WebSocketDisconnect:
        logger.info("WS disconnect: page_name=%s", page_name)
    except Exception as exc:
        logger.error("WS unhandled error: page=%s err=%s", page_name, exc, exc_info=True)
        try:
            await websocket.send_text(json.dumps({"type": "error", "data": "Internal server error."}))
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Public REST chat
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/public/{page_name}/chat",
    response_model=ChatResponse,
    summary="Public single-turn chat (no auth — for embedded widget)",
)
async def public_chat(
    page_name: str,
    body: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rl_key = f"{page_name}:{_get_client_ip(request)}"
    if not await _chat_rate_limiter.is_allowed(rl_key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please slow down.",
            headers={"Retry-After": "60"},
        )

    institution = await _get_institution_by_page_name(db, page_name)
    if not institution:
        raise HTTPException(status_code=404, detail="Page not found.")
    agent = await get_agent(db, institution.id)
    if not agent or not agent.is_active:
        raise HTTPException(status_code=503, detail="AI assistant not available.")

    try:
        return await handle_chat(db, agent, body)
    except (ServiceUnavailableError, LLMConfigError) as exc:
        raise _llm_exception_to_http(exc)


# ─────────────────────────────────────────────────────────────────────────────
# Public WebSocket routes
# ─────────────────────────────────────────────────────────────────────────────

@router.websocket("/public/{page_name}/ws")
async def public_websocket_chat(
    websocket: WebSocket,
    page_name: str,
    db: AsyncSession = Depends(get_db),
):
    await _websocket_handler(websocket, page_name, db)


@router.websocket("/ws/{page_name}")
async def legacy_websocket_chat(
    websocket: WebSocket,
    page_name: str,
    db: AsyncSession = Depends(get_db),
):
    await _websocket_handler(websocket, page_name, db)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Config  (authenticated)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/agent",
    response_model=AgentResponse,
    status_code=201,
    summary="Create AI agent",
)
async def create_ai_agent(
    body: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    existing = await get_agent(db, inst_id)
    if existing:
        raise HTTPException(status_code=409, detail="Agent already exists. Use PATCH to update.")

    agent = await create_agent(db, inst_id, body)
    return AgentResponse.model_validate(agent)


@router.get(
    "/agent",
    response_model=AgentResponse,
    summary="Get agent config",
)
async def get_ai_agent(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    return AgentResponse.model_validate(agent)


@router.patch(
    "/agent",
    response_model=AgentResponse,
    summary="Update agent config",
)
async def update_ai_agent(
    body: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    return AgentResponse.model_validate(await update_agent(db, agent, body))


@router.get(
    "/agent/stats",
    response_model=AgentStatsResponse,
    summary="Agent usage statistics",
)
async def get_ai_stats(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    return await get_agent_stats(db, agent)


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Base
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/knowledge/preview",
    response_model=BulkPreviewResponse,
    summary="Preview how raw text will be chunked (no embedding — free)",
)
async def preview_knowledge_chunks(
    body: BulkKnowledgePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    await _get_agent_or_404(db, inst_id)
    result = preview_chunks(body.raw_text, max_chars=body.max_chars_per_chunk)
    return BulkPreviewResponse(**result)


@router.post(
    "/knowledge/bulk",
    response_model=BulkImportResponse,
    status_code=201,
    summary="Bulk import — splits text into chunks and embeds each one (atomic)",
)
async def bulk_import_knowledge(
    body: BulkKnowledgeImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)

    rl_key = f"bulk:{inst_id}"
    if not await _bulk_rate_limiter.is_allowed(rl_key):
        raise HTTPException(
            status_code=429,
            detail="Bulk import rate limit exceeded (5 per minute). Please wait.",
            headers={"Retry-After": "60"},
        )

    agent = await _get_agent_or_404(db, inst_id)

    try:
        result = await bulk_add_knowledge_chunks(
            db=db,
            agent=agent,
            raw_text=body.raw_text,
            title_prefix=body.title_prefix or "",
            source=body.source,
            meta=body.meta or {},
            max_chars=body.max_chars_per_chunk,
        )
    except (ServiceUnavailableError, LLMConfigError) as exc:
        raise _llm_exception_to_http(exc)

    message = (
        f"Imported {result['stored']} of {result['total_chunks']} chunks successfully."
        if result["skipped"] == 0
        else "Import failed — 0 chunks stored. See errors for details."
    )
    return BulkImportResponse(**result, message=message)


@router.post(
    "/knowledge",
    response_model=KnowledgeChunkResponse,
    status_code=201,
    summary="Add a single knowledge chunk — text is auto-embedded",
)
async def add_chunk(
    body: KnowledgeChunkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    try:
        return KnowledgeChunkResponse.model_validate(await add_knowledge_chunk(db, agent, body))
    except (ServiceUnavailableError, LLMConfigError) as exc:
        raise _llm_exception_to_http(exc)


@router.get(
    "/knowledge",
    response_model=KnowledgeChunkListResponse,
    summary="List knowledge chunks",
)
async def list_chunks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    return await list_knowledge_chunks(db, agent.id, page, page_size, search)


@router.patch(
    "/knowledge/{chunk_id}",
    response_model=KnowledgeChunkResponse,
    summary="Update a knowledge chunk — content change triggers re-embedding",
)
async def update_chunk(
    chunk_id: int,
    body: KnowledgeChunkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    try:
        chunk = await update_knowledge_chunk(db, chunk_id, agent.id, body)
    except (ServiceUnavailableError, LLMConfigError) as exc:
        raise _llm_exception_to_http(exc)
    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    return KnowledgeChunkResponse.model_validate(chunk)


@router.delete("/knowledge/{chunk_id}", status_code=204, summary="Delete a knowledge chunk")
async def delete_chunk(
    chunk_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    if not await delete_knowledge_chunk(db, chunk_id, agent.id):
        raise HTTPException(status_code=404, detail="Chunk not found.")


# ─────────────────────────────────────────────────────────────────────────────
# Authenticated REST chat
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Single-turn REST chat (JWT auth)",
)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    if not agent.is_active:
        raise HTTPException(status_code=503, detail="AI agent is currently disabled.")
    try:
        return await handle_chat(db, agent, body)
    except (ServiceUnavailableError, LLMConfigError) as exc:
        raise _llm_exception_to_http(exc)



@router.post("/chat/session/start", status_code=201, summary="Start / resume a session")
async def start_chat_session(
    body: SessionStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent   = await _get_agent_or_404(db, inst_id)
    
    body.session_id = str(uuid.uuid4())  # always server-generated, ignore client value
    
    session = await start_session(db, agent, body)
    return {
        "session_id": session.session_id,
        "channel": session.channel,
        "started_at": session.started_at,
    }


@router.post("/chat/session/end", summary="End a session")
async def end_chat_session(
    body: SessionEndRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(get_current_user),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    return {"ended": await end_session(db, agent.id, body)}


# ─────────────────────────────────────────────────────────────────────────────
# Unanswered Questions (admin)
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/questions",
    response_model=UnansweredQuestionsListResponse,
    summary="List questions the AI could not answer",
)
async def list_questions(
    status_filter: Optional[QuestionStatus] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    return await list_unanswered_questions(db, agent.id, status_filter)


@router.patch(
    "/questions/{question_id}/resolve",
    response_model=UnansweredQuestionResponse,
    summary="Resolve — answer auto-embedded into KB when add_to_kb=true",
)
async def resolve_question(
    question_id: int,
    body: ResolveQuestionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    try:
        resolved = await resolve_unanswered_question(db, question_id, agent, body)
    except (ServiceUnavailableError, LLMConfigError) as exc:
        raise _llm_exception_to_http(exc)
    if not resolved:
        raise HTTPException(status_code=404, detail="Question not found.")
    return resolved


@router.patch("/questions/{question_id}/ignore", summary="Mark a question as ignored")
async def ignore_question(
    question_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUserResponse = Depends(require_permission(_AI_MANAGE)),
):
    inst_id = await get_institution_id(db, current_user.tenant_id)
    agent = await _get_agent_or_404(db, inst_id)
    if not await ignore_unanswered_question(db, question_id, agent.id):
        raise HTTPException(status_code=404, detail="Question not found.")
    return {"ignored": True}