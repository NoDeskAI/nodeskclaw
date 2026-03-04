"""Organization required gene -- genes that must be installed when an agent joins a workspace."""

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class OrgRequiredGene(BaseModel):
    __tablename__ = "org_required_genes"

    org_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("genes.id"), nullable=False
    )

    __table_args__ = (
        Index(
            "uq_org_required_gene_active",
            "org_id",
            "gene_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
