"""Corridor system models — CorridorHex + HexConnection + HumanHex for workspace topology."""

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

ADJACENT_OFFSETS = {(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)}


def is_adjacent(q1: int, r1: int, q2: int, r2: int) -> bool:
    return (q2 - q1, r2 - r1) in ADJACENT_OFFSETS


def ordered_pair(q1: int, r1: int, q2: int, r2: int) -> tuple[int, int, int, int]:
    """Canonical ordering for a connection pair to prevent duplicates."""
    if (q1, r1) > (q2, r2):
        return q2, r2, q1, r1
    return q1, r1, q2, r2


class CorridorHex(BaseModel):
    __tablename__ = "corridor_hexes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "hex_q", "hex_r", name="uq_corridor_hex_pos"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hex_q: Mapped[int] = mapped_column(Integer, nullable=False)
    hex_r: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    workspace = relationship("Workspace")


class HumanHex(BaseModel):
    __tablename__ = "human_hexes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "hex_q", "hex_r", name="uq_human_hex_pos"),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hex_q: Mapped[int] = mapped_column(Integer, nullable=False)
    hex_r: Mapped[int] = mapped_column(Integer, nullable=False)
    display_color: Mapped[str] = mapped_column(String(20), default="#f59e0b", nullable=False)
    channel_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    channel_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    workspace = relationship("Workspace")
    user = relationship("User")


class HexConnection(BaseModel):
    __tablename__ = "hex_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id", "hex_a_q", "hex_a_r", "hex_b_q", "hex_b_r",
            name="uq_hex_connection_pair",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hex_a_q: Mapped[int] = mapped_column(Integer, nullable=False)
    hex_a_r: Mapped[int] = mapped_column(Integer, nullable=False)
    hex_b_q: Mapped[int] = mapped_column(Integer, nullable=False)
    hex_b_r: Mapped[int] = mapped_column(Integer, nullable=False)
    # deprecated: direction is no longer used in routing; kept for DB compat
    direction: Mapped[str] = mapped_column(String(10), default="both", nullable=False)
    auto_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    workspace = relationship("Workspace")
