from sqlalchemy import Column, String, Integer,Boolean, Enum as SAEnum,DateTime,ForeignKey,Text,BigInteger
from sqlalchemy.dialects.postgresql import JSONB  ,ARRAY
from enum import Enum  # Python's enum
from .base import Base
from sqlalchemy.orm import relationship
from datetime import datetime
class AnnouncementType(str,Enum):
    ALERT = "alert"
    OFFICIAL = "official"
    EVENT = "event"
    ACADEMIC  = "academic"
class Audience(str,Enum):
    All = "all"
    STUDENTS = "students"
    ALL_STAFFS = "all_staffs"
    TEACHERS = "teachers"
    ADMINS  = "admins"
    PARENTS = "parents"
    OTHER_STAFFS = "other_staffs"
    PRINCIPAL = "principals"


from sqlalchemy import Index

class NotificationsDB(Base):
    __tablename__ = "notifications"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id      = Column(String(8), nullable=False)          # index removed here
    institution_id = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"))
    type           = Column(SAEnum(AnnouncementType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    audience       = Column(SAEnum(Audience, values_callable=lambda x: [e.value for e in x]), nullable=False)
    class_id       = Column(Integer, nullable=True)
    title          = Column(String(255), nullable=False)
    message        = Column(Text, nullable=False)
    attached_file  = Column(String(500), nullable=True)
    created_by     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    institution    = relationship("InstitutionDB", back_populates="notifications")

    __table_args__ = (
        # Replaces your single tenant_id index.
        # Covers: WHERE tenant_id = ? ORDER BY created_at DESC  (your main list query)
        Index('ix_notif_tenant_created', 'tenant_id', 'created_at'),

        # Covers: WHERE tenant_id = ? AND type = ?  (your type filter)
        Index('ix_notif_tenant_type', 'tenant_id', 'type'),

        # Covers: WHERE tenant_id = ? AND audience = ?  (your audience filter)
        Index('ix_notif_tenant_audience', 'tenant_id', 'audience'),
    )


class NotificationReadDB(Base):
    __tablename__ = "notification_reads"

    notification_id = Column(Integer, ForeignKey("notifications.id"), primary_key=True)
    tenant_id       = Column(String(8), nullable=False)          # index removed here
    user_id         = Column(Integer, ForeignKey("users.id"), primary_key=True)
    read_at         = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)

    __table_args__ = (
        # Covers: WHERE tenant_id = ? AND user_id = ? AND notification_id IN (...)
        # (your get_all_notification_reads query)
        Index('ix_notifread_tenant_user', 'tenant_id', 'user_id'),
    )


"""
notification_model.py
─────────────────────────────────────────────────────────────────────────────
Multi-channel notification models:
  - WhatsAppConfigDB     → provider credentials for WhatsApp
  - EmailConfigDB        → SMTP / provider credentials for Email
  - SmsConfigDB          → stub, not yet active
  - AutomationRuleDB     → channel-agnostic rule (channels: list of strings)
  - MessageLogDB         → every sent message across all channels
─────────────────────────────────────────────────────────────────────────────
"""


# ══════════════════════════════════════════════════════════════
#  WhatsApp Config  
# ══════════════════════════════════════════════════════════════

class WhatsAppConfigDB(Base):
    __tablename__ = "whatsapp_configs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id       = Column(String(20), nullable=False, index=True)
    institution_id  = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)

    # "twilio" | "gupshup" | "meta"
    provider        = Column(String(50), nullable=False)

    # WhatsApp Business number (E.164: +91XXXXXXXXXX)
    phone_number    = Column(String(20), nullable=False)

    # Provider credentials — NEVER expose in API responses
    # twilio:  { account_sid, auth_token }
    # gupshup: { api_key, app_name }
    # meta:    { access_token, phone_number_id, business_account_id? }
    config          = Column(JSONB, nullable=True, default=dict)

    # Delivery/incoming webhook endpoint
    webhook_url     = Column(String(500), nullable=True)

    # Only ONE config per institution should be active
    is_active       = Column(Boolean, default=True)

    # "connected" | "failed" | "expired" | "pending"
    status          = Column(String(20), default="pending")

    # Last error from verification or send attempt (for UI display)
    last_error      = Column(String(500), nullable=True)

    created_at      = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at      = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    institution     = relationship("InstitutionDB", backref="whatsapp_config")
    message_logs    = relationship("MessageLogDB", back_populates="whatsapp_config",
                                   foreign_keys="MessageLogDB.whatsapp_config_id",
                                   cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════
#  Email Config
# Supports SMTP (any provider) and hosted providers like SendGrid / Mailgun
# ══════════════════════════════════════════════════════════════

class EmailConfigDB(Base):
    __tablename__ = "email_configs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id       = Column(String(20), nullable=False, index=True)
    institution_id  = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)

    # "smtp" | "sendgrid" | "mailgun"
    provider        = Column(String(50), nullable=False, default="smtp")

    # Sender identity
    from_email      = Column(String(200), nullable=False)
    from_name       = Column(String(200), nullable=True)
    reply_to        = Column(String(200), nullable=True)

    # Provider credentials — NEVER expose in API responses
    # smtp:      { host, port, username, password, use_tls }
    # sendgrid:  { api_key }
    # mailgun:   { api_key, domain }
    config          = Column(JSONB, nullable=True, default=dict)

    # Only ONE config per institution should be active
    is_active       = Column(Boolean, default=True)

    # "connected" | "failed" | "expired" | "pending"
    status          = Column(String(20), default="pending")
    is_platform_managed = Column(Boolean, default=True)

    last_error      = Column(String(500), nullable=True)

    created_at      = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at      = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    institution     = relationship("InstitutionDB", backref="email_config")
    message_logs    = relationship("MessageLogDB", back_populates="email_config",
                                   foreign_keys="MessageLogDB.email_config_id",
                                   cascade="all, delete-orphan")


# ══════════════════════════════════════════════════════════════
#  SMS Config  — STUB, not yet active
#  Table exists so future migration is a simple ALTER, not CREATE.
#  All endpoints return 501 Not Implemented.
# ══════════════════════════════════════════════════════════════

class SmsConfigDB(Base):
    __tablename__ = "sms_configs"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id       = Column(String(20), nullable=False, index=True)
    institution_id  = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)

    # "twilio" | "textlocal" | "msg91"  (all stubs for now)
    provider        = Column(String(50), nullable=False, default="twilio")

    phone_number    = Column(String(20), nullable=True)   # Sender ID / long code
    config          = Column(JSONB, nullable=True, default=dict)

    is_active       = Column(Boolean, default=False)      # always False until enabled
    status          = Column(String(20), default="pending")
    last_error      = Column(String(500), nullable=True)

    created_at      = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at      = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    institution     = relationship("InstitutionDB", backref="sms_config")


# ══════════════════════════════════════════════════════════════
#  Automation Rules  — channel-agnostic
#
#  Each rule targets one or more channels: ["whatsapp"], ["email"],
#  or ["whatsapp", "email"].  SMS is stored in the array but
#  the scheduler will skip it until the channel is activated.
#
#  Per-channel message content is stored in `channel_templates`:
#  {
#    "whatsapp": { "body": "Dear {parent_name}..." },
#    "email":    { "subject": "Fee Reminder", "body": "<p>Dear...</p>", "is_html": true }
#    "sms":      { "body": "Fee due: {amount}" }   ← stored but not dispatched yet
#  }
# ══════════════════════════════════════════════════════════════

class AutomationRuleDB(Base):
    __tablename__ = "automation_rules"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    institution_id    = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)

    name              = Column(String(200), nullable=False)

    # "fee_reminder" | "attendance_reminder" | "custom"
    type              = Column(String(50), nullable=False)

    # Toggle without deleting
    enabled           = Column(Boolean, default=True)

    # Channels this rule fires on: ["whatsapp"], ["email"], ["whatsapp","email"]
    # SMS can be stored here but scheduler skips it (not yet active)
    channels          = Column(ARRAY(String), nullable=False, default=list)

    # "All Students with Pending Fees", "Parents of Absent Students", etc.
    audience          = Column(String(200), nullable=False)

    # Per-channel content — see docstring above
    channel_templates = Column(JSONB, nullable=False, default=dict)

    # Human-readable schedule: "1st of every month, 9:00 AM"
    schedule          = Column(String(200), nullable=False)

    # Optional cron expression for scheduler integration
    cron_expression   = Column(String(100), nullable=True)

    # Tracking
    last_run          = Column(DateTime, nullable=True)
    next_run          = Column(DateTime, nullable=True)
    sent_count        = Column(BigInteger, default=0)   # total across all channels

    created_at        = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at        = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    message_logs      = relationship("MessageLogDB", back_populates="rule")


# ══════════════════════════════════════════════════════════════
#  Message Log  — one row per recipient per channel per send
#
#  channel: "whatsapp" | "email" | "sms"
#  config FK is nullable and split per channel so a single log
#  table covers all channels without a polymorphic mess.
# ══════════════════════════════════════════════════════════════

class MessageLogDB(Base):
    __tablename__ = "message_logs"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    institution_id        = Column(Integer, ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False)

    # Which rule triggered this send (null = manual send from Notifications page)
    rule_id               = Column(Integer, ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True)

    # Channel this specific log entry belongs to
    channel               = Column(String(20), nullable=False)  # "whatsapp" | "email" | "sms"

    # FK to the channel-specific config used (only one will be set)
    whatsapp_config_id    = Column(Integer, ForeignKey("whatsapp_configs.id", ondelete="SET NULL"), nullable=True)
    email_config_id       = Column(Integer, ForeignKey("email_configs.id", ondelete="SET NULL"), nullable=True)
    # sms_config_id       = Column(Integer, ForeignKey("sms_configs.id", ondelete="SET NULL"), nullable=True)  # add when SMS active

    recipient_name        = Column(String(200), nullable=False)
    recipient_contact     = Column(String(200), nullable=False)  # phone (WA/SMS) or email address

    # For email: subject line stored separately for display in logs
    subject               = Column(String(500), nullable=True)
    message_body          = Column(Text, nullable=False)

    # "text" | "template" | "html"
    message_type          = Column(String(20), default="text")

    # "queued" | "sent" | "delivered" | "read" | "failed"
    status                = Column(String(20), default="queued")

    # ID returned by provider (used to match webhook callbacks)
    provider_message_id   = Column(String(200), nullable=True, index=True)

    error_message         = Column(String(500), nullable=True)

    sent_at               = Column(DateTime, nullable=True)
    delivered_at          = Column(DateTime, nullable=True)
    created_at            = Column(DateTime, default=lambda: datetime.utcnow())

    rule                  = relationship("AutomationRuleDB", back_populates="message_logs")
    whatsapp_config       = relationship("WhatsAppConfigDB", back_populates="message_logs",
                                         foreign_keys=[whatsapp_config_id])
    email_config          = relationship("EmailConfigDB", back_populates="message_logs",
                                         foreign_keys=[email_config_id])