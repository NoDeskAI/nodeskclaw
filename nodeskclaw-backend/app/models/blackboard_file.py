"""BlackboardFile — shared file metadata for workspace blackboard, backed by TOS."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BlackboardFile(BaseModel):
    __tablename__ = "blackboard_files"
    __table_args__ = (
        Index(
            "uq_blackboard_files_ws_path_name",
            "workspace_id",
            "parent_path",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="/")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_directory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    tos_key: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    uploader_type: Mapped[str] = mapped_column(String(10), nullable=False)
    uploader_id: Mapped[str] = mapped_column(String(36), nullable=False)
    uploader_name: Mapped[str] = mapped_column(String(128), nullable=False)
