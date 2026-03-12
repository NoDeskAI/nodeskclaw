"""Invitation model for email-based member invitations."""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class InvitationStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    expired = "expired"


class Invitation(BaseModel):
    __tablename__ = "invitations"
    __table_args__ = (
        Index(
            "uq_invitation_pending", "org_id", "email",
            unique=True,
            postgresql_where=text("status = 'pending' AND deleted_at IS NULL"),
        ),
    )

    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False,
    )
    email: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="member", nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=InvitationStatus.pending, nullable=False,
    )
    invited_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    accepted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
