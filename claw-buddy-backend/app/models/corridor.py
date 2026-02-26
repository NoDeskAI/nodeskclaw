"""Corridor system models — CorridorHex + HexConnection for workspace topology."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

ADJACENT_OFFSETS = {(1, 0), (-1, 0), (0, 1), (0, -1), (1, -1), (-1, 1)}


def is_adjacent(q1: int, r1: int, q2: int, r2: int) -> bool:
    return (q2 - q1, r2 - r1) in ADJACENT_OFFSETS


def ordered_pair(q1: int, r1: int, q2: int, r2: int) -> tuple[int, int, int, int]:
    """Normalize coordinate order so (a < b) to prevent duplicate connections."""
    if (q1, r1) <= (q2, r2):
        return q1, r1, q2, r2
    return q2, r2, q1, r1


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
    display_name: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)

    workspace = relationship("Workspace")


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
    direction: Mapped[str] = mapped_column(String(8), default="both", nullable=False)
    auto_created: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)

    workspace = relationship("Workspace")
