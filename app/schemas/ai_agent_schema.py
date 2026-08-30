from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums — must mirror ai_agent_model.py exactly ────────────────────────────

class AgentChannel(str, Enum):
    CHAT = "chat"
    CALL = "call"
    # CLASS was removed — do NOT re-add without a matching DB enum migration


class QuestionStatus(str, Enum):
    PENDING  = "pending"
    RESOLVED = "resolved"
    IGNORED  = "ignored"


# ─────────────────────────────────────────────────────────────────────────────
# Agent Config
# ─────────────────────────────────────────────────────────────────────────────

class ChannelBehaviourConfig(BaseModel):
    """Per-channel behaviour knobs (all optional; defaults applied server-side)."""
    greeting: Optional[str] = None
    # "detailed" | "concise"  (educational removed along with CLASS channel)
    response_style: Optional[str] = None
    farewell: Optional[str] = None


class AgentChannelConfig(BaseModel):
    """
    Channel-specific config. Only 'chat' and 'call' are valid keys.
    The old 'class' / klass alias has been removed — sending it is now a
    validation error rather than silent data corruption.
    """
    chat: Optional[ChannelBehaviourConfig] = None
    call: Optional[ChannelBehaviourConfig] = None

    model_config = {"populate_by_name": True}


class AgentCreate(BaseModel):
    agent_name: str = Field(..., min_length=2, max_length=100)
    channel_config: Optional[AgentChannelConfig] = None
    temperature: float = Field(0.3, ge=0.0, le=1.0)
    max_tokens: int = Field(1024, ge=64, le=8192)
    top_k_chunks: int = Field(5, ge=1, le=20)
    similarity_threshold: float = Field(0.75, ge=0.0, le=1.0)


class AgentUpdate(BaseModel):
    agent_name: Optional[str] = Field(None, min_length=2, max_length=100)
    is_active: Optional[bool] = None
    channel_config: Optional[AgentChannelConfig] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=64, le=8192)
    top_k_chunks: Optional[int] = Field(None, ge=1, le=20)
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)


class AgentResponse(BaseModel):
    id: int
    agent_name: str
    is_active: bool
    channel_config: Dict[str, Any]
    temperature: float
    max_tokens: int
    top_k_chunks: int
    similarity_threshold: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Knowledge Base
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeChunkCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    content: str = Field(..., min_length=10)
    source: Optional[str] = Field(None, max_length=255)
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict)


class KnowledgeChunkUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = Field(None, min_length=10)
    source: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class KnowledgeChunkResponse(BaseModel):
    id: int
    agent_id: int
    title: Optional[str]
    content: str
    source: Optional[str]
    meta: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeChunkListResponse(BaseModel):
    items: List[KnowledgeChunkResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ─────────────────────────────────────────────────────────────────────────────
# Chat / Query
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=4, max_length=128)
    channel: AgentChannel = AgentChannel.CHAT
    user_label: Optional[str] = Field(None, max_length=255)


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    channel: AgentChannel
    sources: List[str] = []       # chunk titles / source labels used
    answered: bool = True         # False if AI could not answer
    action: Optional[dict] = None


class SessionStartRequest(BaseModel):
    session_id: str = Field(..., min_length=4, max_length=128)
    channel: AgentChannel
    user_label: Optional[str] = None


class SessionEndRequest(BaseModel):
    session_id: str


# ─────────────────────────────────────────────────────────────────────────────
# Unanswered Questions
# ─────────────────────────────────────────────────────────────────────────────

class UnansweredQuestionResponse(BaseModel):
    id: int
    agent_id: int
    question: str
    session_id: Optional[str]
    channel: AgentChannel
    admin_answer: Optional[str]
    status: QuestionStatus
    kb_chunk_id: Optional[int]
    asked_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


class UnansweredQuestionsListResponse(BaseModel):
    items: List[UnansweredQuestionResponse]
    total: int
    pending_count: int


class ResolveQuestionRequest(BaseModel):
    admin_answer: str = Field(..., min_length=5)
    add_to_kb: bool = True   # if True, auto-embed answer into knowledge base
    status: QuestionStatus = QuestionStatus.RESOLVED


class IgnoreQuestionRequest(BaseModel):
    status: QuestionStatus = QuestionStatus.IGNORED


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

class AgentStatsResponse(BaseModel):
    total_chunks: int
    active_chunks: int
    pending_questions: int
    resolved_questions: int
    total_conversations: int
    active_sessions: int