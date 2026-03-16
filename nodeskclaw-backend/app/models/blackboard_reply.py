"""BlackboardReply — reply to a blackboard post."""

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class BlackboardReply(BaseModel):
    __tablename__ = "blackboard_replies"

    post_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("blackboard_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_type: Mapped[str] = mapped_column(String(10), nullable=False)
    author_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_name: Mapped[str] = mapped_column(String(128), nullable=False)

    post = relationship("BlackboardPost", back_populates="replies")
