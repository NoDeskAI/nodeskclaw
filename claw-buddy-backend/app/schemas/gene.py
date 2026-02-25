"""Pydantic schemas for Gene Evolution Ecosystem."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── Gene ─────────────────────────────────────────


class GeneInfo(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    short_description: str | None = None
    category: str | None = None
    tags: list[str] = []
    source: str = "official"
    source_ref: str | None = None
    icon: str | None = None
    version: str = "1.0.0"
    manifest: dict | None = None
    dependencies: list[str] = []
    synergies: list[str] = []
    parent_gene_id: str | None = None
    created_by_instance_id: str | None = None
    install_count: int = 0
    avg_rating: float = 0.0
    effectiveness_score: float = 0.0
    is_featured: bool = False
    review_status: str | None = None
    is_published: bool = True
    created_by: str | None = None
    org_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class GeneListItem(BaseModel):
    id: str
    name: str
    slug: str
    short_description: str | None = None
    category: str | None = None
    tags: list[str] = []
    source: str = "official"
    icon: str | None = None
    version: str = "1.0.0"
    install_count: int = 0
    avg_rating: float = 0.0
    effectiveness_score: float = 0.0
    is_featured: bool = False
    parent_gene_id: str | None = None
    created_by_instance_id: str | None = None

    model_config = {"from_attributes": True}


class GeneCreateRequest(BaseModel):
    name: str = Field(..., max_length=128)
    slug: str = Field(..., max_length=128)
    description: str | None = None
    short_description: str | None = Field(
        None, max_length=256,
        description="当 manifest 包含 skill 时必填，用于 OpenClaw SKILL.md YAML front matter",
    )
    category: str | None = Field(None, max_length=32)
    tags: list[str] = []
    source: str = "official"
    source_ref: str | None = None
    icon: str | None = Field(None, max_length=32)
    version: str = Field("1.0.0", max_length=16)
    manifest: dict | None = None
    dependencies: list[str] = []
    synergies: list[str] = []
    is_featured: bool = False
    is_published: bool = True


# ── Genome ───────────────────────────────────────


class GenomeInfo(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    short_description: str | None = None
    icon: str | None = None
    gene_slugs: list[str] = []
    config_override: dict | None = None
    install_count: int = 0
    avg_rating: float = 0.0
    is_featured: bool = False
    is_published: bool = True
    created_by: str | None = None
    org_id: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class GenomeListItem(BaseModel):
    id: str
    name: str
    slug: str
    short_description: str | None = None
    icon: str | None = None
    gene_slugs: list[str] = []
    install_count: int = 0
    avg_rating: float = 0.0
    is_featured: bool = False

    model_config = {"from_attributes": True}


class GenomeCreateRequest(BaseModel):
    name: str = Field(..., max_length=128)
    slug: str = Field(..., max_length=128)
    description: str | None = None
    short_description: str | None = Field(None, max_length=256)
    icon: str | None = Field(None, max_length=32)
    gene_slugs: list[str] = []
    config_override: dict | None = None
    is_featured: bool = False
    is_published: bool = True


# ── Admin Update Requests ────────────────────────


class UpdateGeneRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    short_description: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    icon: str | None = None
    version: str | None = None
    manifest: dict | None = None
    is_featured: bool | None = None
    is_published: bool | None = None


class UpdateGenomeRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    short_description: str | None = None
    icon: str | None = None
    gene_slugs: list[str] | None = None
    config_override: dict | None = None
    is_featured: bool | None = None
    is_published: bool | None = None


# ── InstanceGene ─────────────────────────────────


class InstanceGeneInfo(BaseModel):
    id: str
    instance_id: str
    gene_id: str
    genome_id: str | None = None
    status: str = "installing"
    installed_version: str | None = None
    learning_output: str | None = None
    config_snapshot: dict | None = None
    agent_self_eval: float | None = None
    usage_count: int = 0
    variant_published: bool = False
    installed_at: datetime | None = None
    created_at: datetime | None = None

    gene: GeneListItem | None = None

    model_config = {"from_attributes": True}


class InstallGeneRequest(BaseModel):
    gene_slug: str


class ApplyGenomeRequest(BaseModel):
    genome_id: str


class UninstallGeneRequest(BaseModel):
    gene_id: str


# ── Rating ───────────────────────────────────────


class RatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = None


class RatingInfo(BaseModel):
    id: str
    user_id: str
    rating: int
    comment: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Effect ───────────────────────────────────────


class EffectivenessRequest(BaseModel):
    metric_type: str
    value: float = 1.0
    context: str | None = None


class GeneEffectLogInfo(BaseModel):
    id: str
    instance_id: str
    gene_id: str
    metric_type: str
    value: float
    context: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Evolution ────────────────────────────────────


class PublishVariantRequest(BaseModel):
    variant_name: str | None = None
    variant_slug: str | None = None


class CreateGeneRequest(BaseModel):
    creation_prompt: str | None = None


# ── Learning Callback ────────────────────────────


class LearningCallbackPayload(BaseModel):
    task_id: str
    instance_id: str
    mode: str  # "learn" | "create" | "forget"
    decision: str  # "direct_install" | "learned" | "failed" | "created" | "forgotten" | "simplified" | "forget_failed"
    content: str | None = None
    self_eval: float | None = None
    meta: dict | None = None
    reason: str | None = None


# ── Evolution Log ────────────────────────────────


class EvolutionEventInfo(BaseModel):
    id: str
    instance_id: str
    event_type: str
    gene_name: str
    gene_slug: str | None = None
    gene_id: str | None = None
    genome_id: str | None = None
    details: dict | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Admin ────────────────────────────────────────


class GeneStatsResponse(BaseModel):
    total_genes: int = 0
    total_installs: int = 0
    learning_count: int = 0
    failed_count: int = 0
    agent_created_count: int = 0


class ReviewRequest(BaseModel):
    action: str  # "approve" | "reject"
    reason: str | None = None


class TagStats(BaseModel):
    tag: str
    count: int


class CoInstallPair(BaseModel):
    gene_a_slug: str
    gene_b_slug: str
    co_install_count: int
