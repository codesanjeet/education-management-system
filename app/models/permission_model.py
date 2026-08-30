from .base import Base
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime


class PermissionDB(Base):
    __tablename__ = "permissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(225), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow(), nullable=False)

    user_permissions = relationship(
        "UserPermissionDB",
        back_populates="permission",
        passive_deletes=True,
        
    )


class UserPermissionDB(Base):
    __tablename__ = "user_permissions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    permission_id = Column(
        Integer,
        ForeignKey("permissions.id",ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    granted_by = Column(
        Integer,
        nullable=True
    )

    granted_at = Column(DateTime, default=lambda: datetime.utcnow(), nullable=False)

    # Relationships
    user = relationship("UserDB", back_populates="permissions")
    permission = relationship("PermissionDB", back_populates="user_permissions" ,lazy="selectin")
