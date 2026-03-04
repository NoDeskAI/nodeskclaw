"""Instance template schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class InstanceTemplateCreate(BaseModel):
    name: str = Field(..., max_length=128)
    slug: str = Field(..., max_length=128)
    description: str | None = None
    short_description: str | None = Field(None, max_length=256)
    icon: str | None = Field(None, max_length=32)
    gene_slugs: list[str] = Field(default_factory=list)


class InstanceTemplateFromInstance(BaseModel):
    name: str = Field(..., max_length=128)
    slug: str = Field(..., max_length=128)
    description: str | None = None
    short_description: str | None = Field(None, max_length=256)
    icon: str | None = Field(None, max_length=32)


class InstanceTemplateUpdate(BaseModel):
    name: str | None = Field(None, max_length=128)
    description: str | None = None
    short_description: str | None = Field(None, max_length=256)
    icon: str | None = Field(None, max_length=32)
    gene_slugs: list[str] | None = None


class GeneRef(BaseModel):
    slug: str
    name: str
    short_description: str | None = None
    category: str | None = None
    icon: str | None = None


class InstanceTemplateInfo(BaseModel):
    id: str
    name: str
    slug: str
    description: str | None = None
    short_description: str | None = None
    icon: str | None = None
    gene_slugs: list[str] = []
    genes: list[GeneRef] = []
    source_instance_id: str | None = None
    is_published: bool = True
    is_featured: bool = False
    use_count: int = 0
    created_by: str | None = None
    org_id: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
