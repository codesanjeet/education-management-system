from __future__ import annotations

import re
import unicodedata
from enum import Enum
from datetime import datetime
from typing import Optional, List, Dict, Any

from pydantic import BaseModel, EmailStr, Field, field_validator


# ─── Slug helper ──────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """
    Convert a free-text institution name (+ optional city) into a URL slug.
    'St. Xavier\'s Academy, Patna' → 'st-xaviers-academy-patna'
    """
    # Normalise unicode → ASCII
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = text.replace("'", "")
    # Replace non-alphanumeric with hyphen
    text = re.sub(r"[^a-z0-9]+", "-", text)
    # Strip leading/trailing hyphens and collapse multiples
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


# ─── Enum mirrors ─────────────────────────────────────────────────────────────

class AdmissionStatus(str, Enum):
    PENDING    = "pending"
    REVIEWED   = "reviewed"
    ACCEPTED   = "accepted"
    REJECTED   = "rejected"
    WAITLISTED = "waitlisted"


class GenderEnum(str, Enum):
    MALE   = "male"
    FEMALE = "female"
    OTHER  = "other"


class ContactType(str, Enum):
    EMAIL   = "email"
    PHONE   = "phone"
    ADDRESS = "address"
    WEBSITE = "website"
    WHATSAPP = "whatsapp"


# ══════════════════════════════════════════════════════════════════════════════
# IMAGE SPEC  (returned to the frontend so it can show the correct hints)
# ══════════════════════════════════════════════════════════════════════════════

class ImageSpec(BaseModel):
    """
    Metadata about what an image field expects, shown in the upload UI.
    All dimensions are in pixels.
    """
    label:        str             # e.g. "Hero Slide"
    aspect_ratio: str             # e.g. "16:9"
    min_width:    int             # e.g. 1280
    min_height:   int             # e.g. 720
    max_size_mb:  int    = 10
    hint:         str             # human-readable usage hint


# Specs referenced by the frontend upload widget
IMAGE_SPECS: dict[str, ImageSpec] = {
    "slider-desktop": ImageSpec(
        label="Hero Slide — Desktop",
        aspect_ratio="16:9",
        min_width=1280,
        min_height=720,
        hint="Full-width banner shown on tablets and desktops. Landscape, high-quality photo (min 1280×720 px).",
    ),
    "slider-mobile": ImageSpec(
        label="Hero Slide — Mobile",
        aspect_ratio="9:16",
        min_width=640,
        min_height=1136,
        hint="Portrait crop shown on phones. Centre the key subject so it isn't clipped (min 640×1136 px).",
    ),
    "about": ImageSpec(
        label="About Section Image",
        aspect_ratio="4:3",
        min_width=800,
        min_height=600,
        hint="Shown beside the About text. Works best as a campus/classroom photo (800×600 px minimum).",
    ),
    "logo": ImageSpec(
        label="Institution Logo",
        aspect_ratio="1:1",
        min_width=256,
        min_height=256,
        hint="Square logo. Use PNG with transparent background (256×256 px minimum).",
    ),
    # Backward-compat alias kept so old clients sending spec_key="slider" still resolve
    "slider": ImageSpec(
        label="Hero Slide — Desktop (legacy)",
        aspect_ratio="16:9",
        min_width=1280,
        min_height=720,
        hint="Use 'slider-desktop' for new uploads. Full-width banner (min 1280×720 px).",
    ),
}


# ══════════════════════════════════════════════════════════════════════════════
# INSTITUTION PAGE SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

# ─── Sub-objects ──────────────────────────────────────────────────────────────

class SliderItem(BaseModel):

    # Desktop image (required — 16:9)
    image_key:        Optional[str] = Field(None, description="R2 key for desktop image (16:9)")
    image_url:        Optional[str] = Field(None, description="Resolved desktop URL (read-only)")
    # Mobile image (optional — 9:16; fallback to desktop if absent)
    image_key_mobile: Optional[str] = Field(None, description="R2 key for mobile portrait image (3:4)")
    image_url_mobile: Optional[str] = Field(None, description="Resolved mobile URL (read-only)")

    title:    str           = Field(..., max_length=200)
    subtitle: Optional[str] = Field(None, max_length=300)

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Slide title cannot be empty.")
        return v.strip()


class StatItem(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    value: str = Field(..., min_length=1, max_length=50,
                       description='e.g. "2000+", "95%"')


class FeatureItem(BaseModel):
    emoji: str           = Field("🏫", max_length=8,
                                  description="Single emoji used as the feature icon")
    title: str           = Field(..., min_length=1, max_length=100)
    desc:  Optional[str] = Field(None, max_length=300)


class ContactItem(BaseModel):
    type:  ContactType = Field(..., description="email | phone | address | website | whatsapp")
    value: str         = Field(..., min_length=1, max_length=500)
    label: Optional[str] = Field(None, max_length=80,
                                  description='e.g. "Admissions Office", "Main Campus"')


class SocialLinks(BaseModel):
    facebook:  Optional[str] = None
    instagram: Optional[str] = None
    twitter:   Optional[str] = None
    youtube:   Optional[str] = None
    linkedin:  Optional[str] = None
    website:   Optional[str] = None


# ─── Page name (slug) ─────────────────────────────────────────────────────────

class PageNameCheckRequest(BaseModel):
    """POST /institutions/admission/page/check-slug"""
    raw_name: str = Field(..., min_length=3, max_length=200,
                           description="Institution name (+ optional city) to slugify and check")

class PageNameCheckResponse(BaseModel):
    slug:      str
    available: bool
    message:   str


# ─── Create / Update ──────────────────────────────────────────────────────────

class InstitutionPageCreate(BaseModel):
    # ── Slug (required on create) ─────────────────────────────────────────
    page_name:   str = Field(
        ...,
        min_length=3,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9\-]{1,118}[a-z0-9]$",
        description=(
            "Unique URL slug for this institution. "
            "Must be lowercase, hyphens only (e.g. 'my-academy-patna'). "
            "⚠️ Cannot be changed after publishing without breaking SEO."
        ),
    )

    # ── Slider (min 1 slide required) ─────────────────────────────────────
    slider_items:   List[SliderItem]  = Field(..., min_length=1, max_length=5)

    # ── About ─────────────────────────────────────────────────────────────
    about_title:     str            = Field(..., min_length=3, max_length=200)
    about_body:      str            = Field(..., min_length=20)
    about_image_key: Optional[str]  = None       # R2 key set by upload endpoint

    # ── Stats (min 3 required) ────────────────────────────────────────────
    stats_items:    List[StatItem]    = Field(..., min_length=3, max_length=8)

    # ── Features (min 3 required) ─────────────────────────────────────────
    features_items: List[FeatureItem] = Field(..., min_length=3, max_length=9)

    # ── Contacts (min 1 required) ─────────────────────────────────────────
    contact_items:  List[ContactItem] = Field(..., min_length=1, max_length=10)

    # ── Map ───────────────────────────────────────────────────────────────
    map_embed_url:   Optional[str]  = None

    # ── Social ────────────────────────────────────────────────────────────
    social_links:    SocialLinks    = Field(default_factory=SocialLinks)

    # ── Admission ─────────────────────────────────────────────────────────
    admission_open:  bool           = True
    admission_note:  Optional[str]  = None

    # ── Chatbot ───────────────────────────────────────────────────────────
    chatbot_enabled: bool           = True
    chatbot_label:   str            = Field("Chat with us", max_length=100)

    # ── Logo (R2 key) ─────────────────────────────────────────────────────
    logo_key:        Optional[str]  = None

    is_published:    bool           = False

    @field_validator("page_name")
    @classmethod
    def normalise_slug(cls, v: str) -> str:
        slug = slugify(v)
        if len(slug) < 3:
            raise ValueError("Slug is too short after normalisation.")
        return slug


class InstitutionPageUpdate(BaseModel):
    """All fields optional — partial updates supported."""

    # page_name updates are allowed but the router must warn the admin.
    page_name:       Optional[str]              = Field(
        None,
        min_length=3,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9\-]{1,118}[a-z0-9]$",
        description="⚠️ Changing the slug after publishing will break existing links and damage SEO.",
    )

    slider_items:    Optional[List[SliderItem]]   = Field(None, min_length=1, max_length=5)
    about_title:     Optional[str]                = Field(None, min_length=3, max_length=200)
    about_body:      Optional[str]                = Field(None, min_length=20)
    about_image_key: Optional[str]                = None
    stats_items:     Optional[List[StatItem]]     = Field(None, min_length=3, max_length=8)
    features_items:  Optional[List[FeatureItem]]  = Field(None, min_length=3, max_length=9)
    contact_items:   Optional[List[ContactItem]]  = Field(None, min_length=1, max_length=10)
    map_embed_url:   Optional[str]                = None
    social_links:    Optional[SocialLinks]        = None
    admission_open:  Optional[bool]               = None
    admission_note:  Optional[str]                = None
    chatbot_enabled: Optional[bool]               = None
    chatbot_label:   Optional[str]                = Field(None, max_length=100)
    logo_key:        Optional[str]                = None
    is_published:    Optional[bool]               = None

    @field_validator("page_name")
    @classmethod
    def normalise_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        slug = slugify(v)
        if len(slug) < 3:
            raise ValueError("Slug is too short after normalisation.")
        return slug


class InstitutionPageResponse(BaseModel):
    # ── Slug ──────────────────────────────────────────────────────────────
    page_name:      Optional[str] = None

    # ── Pulled from InstitutionDB at query time ────────────────────────────
    institute_name: str
    logo_url:       Optional[str] = None  

    # ── Page config ────────────────────────────────────────────────────────
    slider_items:    List[Dict[str, Any]]
    about_title:     Optional[str]
    about_body:      Optional[str]
    about_image_url: Optional[str]         # fully-resolved URL
    stats_items:     List[Dict[str, Any]]
    features_items:  List[Dict[str, Any]]
    contact_items:   List[Dict[str, Any]]
    map_embed_url:   Optional[str]
    social_links:    Dict[str, Any]
    admission_open:  bool
    admission_note:  Optional[str]
    chatbot_enabled: bool
    chatbot_label:   str

    # ── Chat / page URLs (from InstitutionInfoDB) ─────────────────────────
    chat_url:        Optional[str] = None
    page_url:        Optional[str] = None

    is_published:    bool
    created_at:      datetime
    updated_at:      datetime

    # Slug change warning (populated by router when page_name is updated)
    seo_warning:     Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Image upload response ────────────────────────────────────────────────────

class ImageUploadResponse(BaseModel):
    key:  str   # R2 object key — store this in your page config
    url:  str   # Public URL — use this for preview only
    spec: Optional[ImageSpec] = None  # echoed back so the UI can show hints


# ══════════════════════════════════════════════════════════════════════════════
# ADMISSION FORM SCHEMAS
# ══════════════════════════════════════════════════════════════════════════════

class AdmissionFormCreate(BaseModel):
    """Submitted from the public page — no auth."""
    first_name:          str              = Field(..., min_length=1, max_length=100)
    last_name:           Optional[str]              = Field(None, min_length=1, max_length=100)
    date_of_birth:       Optional[str]    = None
    gender:              Optional[GenderEnum] = None
    email:               Optional[EmailStr]   = None
    phone:               str              = Field(..., min_length=6, max_length=30)
    applying_for_class:  Optional[str]    = Field(None, max_length=100)
    previous_school:     Optional[str]    = Field(None, max_length=200)
    previous_percentage: Optional[str]    = Field(None, max_length=20)
    guardian_name:       Optional[str]    = Field(None, max_length=200)
    guardian_phone:      Optional[str]    = Field(None, max_length=30)
    guardian_relation:   Optional[str]    = Field(None, max_length=50)
    address:             Optional[str]    = None
    city:                Optional[str]    = Field(None, max_length=100)
    state:               Optional[str]    = Field(None, max_length=100)
    pincode:             Optional[str]    = Field(None, max_length=20)
    message:             Optional[str]    = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) < 10:
            raise ValueError("Phone number must have at least 10 digits.")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return v.strip()


class AdmissionFormStatusUpdate(BaseModel):
    """Admin-only: update status + notes."""
    status:      AdmissionStatus
    admin_notes: Optional[str] = None


class AdmissionFormResponse(BaseModel):
    id:                  int
    first_name:          str
    last_name:           Optional[str]
    date_of_birth:       Optional[str]
    gender:              Optional[str]
    email:               Optional[str]
    phone:               str
    applying_for_class:  Optional[str]
    previous_school:     Optional[str]
    previous_percentage: Optional[str]
    guardian_name:       Optional[str]
    guardian_phone:      Optional[str]
    guardian_relation:   Optional[str]
    address:             Optional[str]
    city:                Optional[str]
    state:               Optional[str]
    pincode:             Optional[str]
    message:             Optional[str]
    status:              str
    admin_notes:         Optional[str]
    reviewed_at:         Optional[datetime]
    created_at:          datetime
    updated_at:          datetime

    model_config = {"from_attributes": True}


# ─── List + Stats ─────────────────────────────────────────────────────────────

class AdmissionGrowthPoint(BaseModel):
    date:  str   # "YYYY-MM-DD"
    count: int

class AdmissionStatsResponse(BaseModel):
    total:      int
    pending:    int
    reviewed:   int
    accepted:   int
    rejected:   int
    waitlisted: int
    this_month: int
    growth:     List[AdmissionGrowthPoint]

class AdmissionListResponse(BaseModel):
    items: List[AdmissionFormResponse]
    total: int
    page:  int
    limit: int