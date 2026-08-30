from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean,
    ForeignKey, Text, Enum
)
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime
import enum

from .base import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class AdmissionStatus(str, enum.Enum):
    PENDING    = "pending"
    REVIEWED   = "reviewed"
    ACCEPTED   = "accepted"
    REJECTED   = "rejected"
    WAITLISTED = "waitlisted"


class GenderEnum(str, enum.Enum):
    MALE   = "male"
    FEMALE = "female"
    OTHER  = "other"


# ─── Institution Landing Page ─────────────────────────────────────────────────

class InstitutionPageDB(Base):
    __tablename__ = "institution_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Unique public slug ─────────────────────────────────────────────────
    page_name      = Column(String(120), nullable=True, unique=True, index=True)

    # ── Hero / Slider ──────────────────────────────────────────────────────
    # JSON array: [{ "image_key": "images/uuid.jpg", "image_url": "https://...",
    #               "title": "...", "subtitle": "..." }, ...]
    slider_items   = Column(JSONB, nullable=False, default=list)

    # ── About Section ─────────────────────────────────────────────────────
    about_title    = Column(String(200), nullable=True)
    about_body     = Column(Text,        nullable=True)
    about_image_key = Column(String(500), nullable=True)

    # ── Stats Bar (shown on landing page) ─────────────────────────────────
    # JSON: [{ "label": "Students", "value": "2000+" }, ...]
    # Minimum 3 stats enforced at API layer.
    stats_items    = Column(JSONB, nullable=False, default=list)

    # ── Features / Why Us ─────────────────────────────────────────────────
    # JSON: [{ "emoji": "🏆", "title": "...", "desc": "..." }, ...]
    # Minimum 3 features enforced at API layer.
    features_items = Column(JSONB, nullable=False, default=list)

    # ── Contact Info ─────────────────────────────────────────────────────
    # JSON array: [
    #   { "type": "email",   "value": "info@school.edu", "label": "Admissions" },
    #   { "type": "phone",   "value": "+91 98765 43210", "label": "Main Office" },
    #   { "type": "address", "value": "123 School Rd...", "label": "Campus" },
    #   { "type": "website", "value": "https://...",      "label": "Website" },
    # ]
    contact_items  = Column(JSONB, nullable=False, default=list)

    # Legacy single-contact fields — kept nullable for backward compat / migration
    contact_email   = Column(String(254), nullable=True)
    contact_phone   = Column(String(30),  nullable=True)
    contact_address = Column(Text,        nullable=True)

    map_embed_url   = Column(Text, nullable=True)

    # ── Social Links ──────────────────────────────────────────────────────
    # JSON: { "facebook": "url", "instagram": "url", ... }
    social_links   = Column(JSONB, nullable=False, default=dict)

    # ── Admission Toggle ──────────────────────────────────────────────────
    admission_open = Column(Boolean, default=True)
    admission_note = Column(Text,    nullable=True)

    # ── Chatbot ───────────────────────────────────────────────────────────
    chatbot_enabled = Column(Boolean, default=True)
    chatbot_label   = Column(String(100), default="Chat with us")


    # Stored separately from InstitutionDB.logo so the page can have its own logo.
    logo_key        = Column(String(500), nullable=True)

    # ── Meta ──────────────────────────────────────────────────────────────
    is_published   = Column(Boolean,  default=False)
    created_at     = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at     = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())



# ─── Admission Form Submission ────────────────────────────────────────────────

class AdmissionFormDB(Base):
    __tablename__ = "admission_forms"

    id = Column(Integer, primary_key=True, autoincrement=True)
    institution_id = Column(
        Integer,
        ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Applicant ─────────────────────────────────────────────────────────
    first_name     = Column(String(100), nullable=False)
    last_name      = Column(String(100), nullable=True)
    date_of_birth  = Column(String(20),  nullable=True)
    gender         = Column(
        Enum(GenderEnum, name="gender_enum"),
        nullable=True,
    )
    email          = Column(String(254), nullable=True)
    phone          = Column(String(30),  nullable=False)

    # ── Academic ──────────────────────────────────────────────────────────
    applying_for_class  = Column(String(100), nullable=True)
    previous_school     = Column(String(200), nullable=True)
    previous_percentage = Column(String(20),  nullable=True)

    # ── Guardian ──────────────────────────────────────────────────────────
    guardian_name     = Column(String(200), nullable=True)
    guardian_phone    = Column(String(30),  nullable=True)
    guardian_relation = Column(String(50),  nullable=True)

    # ── Address ───────────────────────────────────────────────────────────
    address = Column(Text,        nullable=True)
    city    = Column(String(100), nullable=True)
    state   = Column(String(100), nullable=True)
    pincode = Column(String(20),  nullable=True)

    # ── Extra ─────────────────────────────────────────────────────────────
    message = Column(Text, nullable=True)

    # ── Admin fields ──────────────────────────────────────────────────────
    status = Column(
        Enum(AdmissionStatus, name="admission_status"),
        default=AdmissionStatus.PENDING,
        nullable=False,
    )
    admin_notes  = Column(Text,    nullable=True)
    reviewed_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at  = Column(DateTime, nullable=True)

    created_at   = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at   = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())