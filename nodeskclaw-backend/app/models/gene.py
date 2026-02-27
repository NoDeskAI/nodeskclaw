"""Gene Evolution Ecosystem models."""

from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class GeneSource(str, Enum):
    official = "official"
    clawhub = "clawhub"
    community = "community"
    agent = "agent"


class GeneReviewStatus(str, Enum):
    pending_owner = "pending_owner"
    pending_admin = "pending_admin"
    approved = "approved"
    rejected = "rejected"


class InstanceGeneStatus(str, Enum):
    installing = "installing"
    learning = "learning"
    installed = "installed"
    learn_failed = "learn_failed"
    failed = "failed"
    uninstalling = "uninstalling"
    forgetting = "forgetting"
    forget_failed = "forget_failed"
    simplified = "simplified"


class EvolutionEventType(str, Enum):
    learned = "learned"
    forgotten = "forgotten"
    simplified = "simplified"
    learn_failed = "learn_failed"
    forget_failed = "forget_failed"
    variant_published = "variant_published"
    genome_applied = "genome_applied"


class EffectMetricType(str, Enum):
    user_positive = "user_positive"
    user_negative = "user_negative"
    task_success = "task_success"
    agent_self_eval = "agent_self_eval"


class Gene(BaseModel):
    __tablename__ = "genes"
    __table_args__ = (
        Index(
            "uq_genes_slug_active",
            "slug",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    source: Mapped[str] = mapped_column(
        String(16), default=GeneSource.official, nullable=False
    )
    source_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version: Mapped[str] = mapped_column(String(16), default="1.0.0", nullable=False)
    manifest: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    dependencies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    synergies: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array

    parent_gene_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("genes.id"), nullable=True
    )
    created_by_instance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=True
    )

    install_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    effectiveness_score: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )


class Genome(BaseModel):
    __tablename__ = "genomes"
    __table_args__ = (
        Index(
            "uq_genomes_slug_active",
            "slug",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(String(256), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gene_slugs: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    config_override: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    install_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    org_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True
    )


class InstanceGene(BaseModel):
    __tablename__ = "instance_genes"
    __table_args__ = (
        Index(
            "uq_instance_gene_active",
            "instance_id",
            "gene_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False, index=True
    )
    gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("genes.id"), nullable=False, index=True
    )
    genome_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("genomes.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=InstanceGeneStatus.installing, nullable=False
    )
    installed_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    learning_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    agent_self_eval: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    variant_published: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    installed_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )


class GeneEffectLog(BaseModel):
    __tablename__ = "gene_effect_logs"

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False, index=True
    )
    gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("genes.id"), nullable=False, index=True
    )
    metric_type: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)


class GeneRating(BaseModel):
    __tablename__ = "gene_ratings"
    __table_args__ = (
        Index(
            "uq_gene_rating_user",
            "gene_id",
            "user_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    gene_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("genes.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class GenomeRating(BaseModel):
    __tablename__ = "genome_ratings"
    __table_args__ = (
        Index(
            "uq_genome_rating_user",
            "genome_id",
            "user_id",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    genome_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("genomes.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvolutionEvent(BaseModel):
    """Records every gene-related evolution event for an instance timeline."""

    __tablename__ = "evolution_events"

    instance_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("instances.id"), nullable=False, index=True
    )
    gene_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    genome_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    gene_name: Mapped[str] = mapped_column(String(128), nullable=False)
    gene_slug: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
