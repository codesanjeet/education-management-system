from datetime import datetime
import enum

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, Text, Float,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from .base import Base


# ── Enums ──────────────────────────────────────────────────────────────────────

class AgentChannel(str, enum.Enum):
    CHAT = "chat"   
    CALL = "call"   

class QuestionStatus(str, enum.Enum):
    PENDING  = "pending"
    RESOLVED = "resolved"
    IGNORED  = "ignored"


class EmbeddingProvider(str, enum.Enum):
    OPENAI = "openai"   # text-embedding-3-small → 1536 dims  [ACTIVE]
    GEMINI = "gemini"   # text-embedding-004     → 768  dims  [STANDBY]


# ── AI Agent Configuration ─────────────────────────────────────────────────────

class AIAgentDB(Base):
    __tablename__ = "ai_agents"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    agent_name = Column(String(100), nullable=False, default="EduAssist")
    is_active  = Column(Boolean, default=True, nullable=False)

    # { "chat": { "greeting": "Hi!", "response_style": "detailed" },
    #   "call": { "greeting": "Hello!", "response_style": "concise" } }
    # Note: only "chat" and "call" keys are valid — "class" is no longer used.
    channel_config = Column(JSONB, nullable=False, default=dict)


    # ── Retrieval settings — internal/ops only, NOT exposed in admin UI ────────
    # These are kept as DB columns so ops can tune via DB or a future internal
    # tool. The admin UI no longer shows or modifies them.
    # Sensible defaults for OpenAI text-embedding-3-small:
    #   temperature          0.20  (factual, low creativity)
    #   max_tokens           2048
    #   top_k_chunks         8     (retrieve top 8 chunks per query)
    #   similarity_threshold 0.25  (cosine similarity floor — works well for 3-small)
    temperature          = Column(Float,   default=0.20, nullable=False)
    max_tokens           = Column(Integer, default=2048, nullable=False)
    top_k_chunks         = Column(Integer, default=8,    nullable=False)
    similarity_threshold = Column(Float,   default=0.25, nullable=False)

    # Do NOT change manually — only after completing the 5-step column migration.
    embedding_provider = Column(
        Enum(EmbeddingProvider),
        nullable=False,
        default=EmbeddingProvider.OPENAI,
    )

    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    knowledge_chunks     = relationship("KnowledgeBaseDB",        back_populates="agent", cascade="all, delete-orphan", passive_deletes=True)
    unanswered_questions = relationship("AIUnansweredQuestionDB", back_populates="agent", cascade="all, delete-orphan", passive_deletes=True)
    conversations        = relationship("AIConversationDB",       back_populates="agent", cascade="all, delete-orphan", passive_deletes=True)
    channel_sessions     = relationship("AIChannelSessionDB",     back_populates="agent", cascade="all, delete-orphan", passive_deletes=True)


# ── Knowledge Base ─────────────────────────────────────────────────────────────

class KnowledgeBaseDB(Base):
    """
    Vector store. Each row is one semantic text chunk.
    Dims = 1536 → OpenAI text-embedding-3-small (active provider).

    Index (run once after first migration):
        CREATE INDEX kb_hnsw_idx ON knowledge_base
          USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64);
    """
    __tablename__ = "knowledge_base"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    agent_id       = Column(Integer, ForeignKey("ai_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(Integer, nullable=False, index=True)

    title   = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    source  = Column(String(255), nullable=True)

    embedding = Column(Vector(1536), nullable=True)   # OpenAI text-embedding-3-small

    meta = Column(JSONB, nullable=False, default=dict)

    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    agent = relationship("AIAgentDB", back_populates="knowledge_chunks")


# ── Unanswered Questions ───────────────────────────────────────────────────────

class AIUnansweredQuestionDB(Base):
    """
    Questions the AI genuinely could not answer from the knowledge base.
    Admin answers them in the config panel → auto-embedded back into KB.
    """
    __tablename__ = "ai_unanswered_questions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    agent_id       = Column(Integer, ForeignKey("ai_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(Integer, nullable=False, index=True)

    question   = Column(Text, nullable=False)
    session_id = Column(String(128), nullable=True)
    channel    = Column(Enum(AgentChannel), nullable=False, default=AgentChannel.CHAT)

    admin_answer = Column(Text, nullable=True)
    status       = Column(Enum(QuestionStatus), default=QuestionStatus.PENDING, nullable=False, index=True)
    kb_chunk_id  = Column(Integer, ForeignKey("knowledge_base.id", ondelete="SET NULL"), nullable=True)

    asked_at    = Column(DateTime, default=lambda: datetime.utcnow())
    resolved_at = Column(DateTime, nullable=True)

    agent = relationship("AIAgentDB", back_populates="unanswered_questions")


# ── Conversation History ───────────────────────────────────────────────────────

class AIConversationDB(Base):
    """Last N turns per session, injected into each LLM call for context."""
    __tablename__ = "ai_conversations"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    agent_id   = Column(Integer, ForeignKey("ai_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(String(128), nullable=False, index=True)
    role       = Column(String(20),  nullable=False)   # "user" | "assistant"
    content    = Column(Text, nullable=False)
    channel    = Column(Enum(AgentChannel), nullable=False, default=AgentChannel.CHAT)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    agent = relationship("AIAgentDB", back_populates="conversations")


# ── Channel Session ────────────────────────────────────────────────────────────

class AIChannelSessionDB(Base):
    """Active session context used by the WebSocket handler."""
    __tablename__ = "ai_channel_sessions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    agent_id       = Column(Integer, ForeignKey("ai_agents.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id = Column(Integer, nullable=False, index=True)

    session_id     = Column(String(128), nullable=False, unique=True, index=True)
    channel        = Column(Enum(AgentChannel), nullable=False)
    user_label     = Column(String(255), nullable=True)

    started_at     = Column(DateTime, default=lambda: datetime.utcnow())
    last_active_at = Column(DateTime, default=lambda: datetime.utcnow())
    ended_at       = Column(DateTime, nullable=True)
    is_active      = Column(Boolean, default=True)

    agent = relationship("AIAgentDB", back_populates="channel_sessions")