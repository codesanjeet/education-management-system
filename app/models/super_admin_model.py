from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey, event, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
from .base import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SuperAdminRole(str, Enum):
    SUPER_ADMIN = "super_admin"


super_admin_role_enum_type = SAEnum(
    SuperAdminRole,
    name="superadminrole",
    values_callable=lambda x: [e.value for e in x],
)


# ---------------------------------------------------------------------------
# SuperAdminDB
# ---------------------------------------------------------------------------

class SuperAdminDB(Base):
    __tablename__ = "super_admin"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identity
    name = Column(String(50), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    user_name = Column(String(25), unique=True, nullable=False, index=True)

    # Contact
    contact_num = Column(String(15), nullable=False)
    num_country_code = Column(String(5), nullable=False, default="91")

    # Role — hardcoded, no enum needed for a single-value column,
    # but typed for JWT claim safety and DB-level enforcement.
    role = Column(
        super_admin_role_enum_type,
        nullable=False,
        default=SuperAdminRole.SUPER_ADMIN,
    )

    # Profile
    profile_image = Column(String(255), nullable=True)
    address = Column(String(255), nullable=True)

    # Status
    is_block = Column(Boolean, default=False, nullable=False)

    # Permissions
    # Expected shape:
    # {
    #   "can_create_institution": true,
    #   "can_delete_institution": false,
    #   "can_impersonate_admin": false,
    #   "accessible_institution_ids": []   <- empty list means access to ALL
    # }
    permissions = Column(JSONB, nullable=False, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
        nullable=False,
    )

    # Relationships
    security = relationship(
        "SuperAdminSecurityDB",
        back_populates="super_admin",
        uselist=False,
        passive_deletes=True,
        lazy="joined",
    )
    sessions = relationship(
        "SuperAdminSessionDB",
        back_populates="super_admin",
        uselist=True,
        passive_deletes=True,
    )
    log = relationship(
        "SuperAdminLogDB",
        back_populates="super_admin",
        uselist=True,
        passive_deletes=True,
        lazy="select",       # was "joined" — avoids auto-JOIN on every query
    )


@event.listens_for(SuperAdminDB, "before_insert")
@event.listens_for(SuperAdminDB, "before_update")
def lowercase_super_admin_fields(mapper, connection, target):
    if target.email:
        target.email = target.email.lower()
    if target.user_name:
        target.user_name = target.user_name.lower()


# ---------------------------------------------------------------------------
# SuperAdminSecurityDB
# ---------------------------------------------------------------------------

class SuperAdminSecurityDB(Base):
    __tablename__ = "super_admin_security"

    id = Column(Integer, primary_key=True, autoincrement=True)
    super_admin_id = Column(
        Integer,
        ForeignKey("super_admin.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one-to-one
        index=True,
    )

    # Auth
    password_hash = Column(String(100), nullable=False)
    otp_secret = Column(String(255), nullable=True)   # TOTP secret for authenticator app
    is_2fa_enabled = Column(Boolean, default=False, nullable=False)

    # Login tracking
    last_password_change = Column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    last_failed_login = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)

    # Password reset
    password_reset_token = Column(String(255), nullable=True, index=True)
    password_reset_expires = Column(DateTime, nullable=True)

    # Timestamps
    updated_at = Column(
        DateTime,
        default=lambda: datetime.utcnow(),
        onupdate=lambda: datetime.utcnow(),
        nullable=False,
    )

    # Relationship
    super_admin = relationship("SuperAdminDB", back_populates="security")


# ---------------------------------------------------------------------------
# SuperAdminSessionDB
# ---------------------------------------------------------------------------

class SuperAdminSessionDB(Base):
    """
    Tracks active JWT sessions for SuperAdmins.
    Mirrors UserSessionDB — kept separate so revocation logic
    never touches the regular user sessions table.
    """
    __tablename__ = "super_admin_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    super_admin_id = Column(
        Integer,
        ForeignKey("super_admin.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # JWT identifier — used for revocation
    jti = Column(String(255), unique=True, nullable=False, index=True)

    # Expiry & revocation
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked = Column(Boolean, default=False, nullable=False)

    # Metadata
    ip_address = Column(String(45), nullable=True)    # IPv4 / IPv6
    user_agent = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )
    last_used_at = Column(DateTime, nullable=True)

    # Relationship
    super_admin = relationship("SuperAdminDB", back_populates="sessions")


# ---------------------------------------------------------------------------
# SuperAdminLogDB
# ---------------------------------------------------------------------------

class SuperAdminLogDB(Base):
    __tablename__ = "super_admin_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    super_admin_id = Column(
        Integer,
        ForeignKey("super_admin.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    login_time = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    ip_address = Column(String(45), nullable=True)    # IPv4 / IPv6
    user_agent = Column(String(500), nullable=True)
    success = Column(Boolean, default=True, nullable=False)
    # NOTE: login_time doubles as created_at — no separate column needed

    # Relationship
    super_admin = relationship("SuperAdminDB", back_populates="log")