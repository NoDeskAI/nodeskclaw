"""PostRead — tracks which posts have been read by which user/agent."""

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PostRead(BaseModel):
    __tablename__ = "post_reads"
    __table_args__ = (
        Index(
            "uq_post_reads_post_reader",
            "post_id",
            "reader_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blackboard_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reader_type: Mapped[str] = mapped_column(String(10), nullable=False)
    reader_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
