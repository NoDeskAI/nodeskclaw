"""Schemas for Kubernetes runtime image builds."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ImageBuildCreate(BaseModel):
    runtime: Literal["openclaw", "hermes"]
    version: str = Field(min_length=1, max_length=64)
    cluster_id: str
    source_ref: str | None = Field(default=None, max_length=128)
    release_notes: str | None = Field(default=None, max_length=10000)

    @field_validator("version")
    @classmethod
    def normalize_version(cls, value: str) -> str:
        return value.strip().removeprefix("v")

    @field_validator("source_ref")
    @classmethod
    def normalize_source_ref(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class ImageBuildSummary(BaseModel):
    id: str
    org_id: str
    cluster_id: str
    requested_by: str
    engine_version_id: str | None = None
    runtime: str
    version: str
    image_repository: str
    image_tag: str
    image_reference: str
    source_repository: str
    source_ref: str
    namespace: str
    job_name: str
    status: str
    error_message: str | None = None
    release_notes: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImageBuildInfo(ImageBuildSummary):
    log_text: str | None = None
