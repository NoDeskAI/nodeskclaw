"""Pydantic schemas for LLM key management APIs."""

from pydantic import BaseModel, Field


# ── Org LLM Key ──────────────────────────────────────────

class OrgLlmKeyCreate(BaseModel):
    provider: str = Field(..., max_length=32)
    label: str = Field(..., max_length=128)
    api_key: str
    base_url: str | None = None
    org_token_limit: int | None = None
    system_token_limit: int | None = None


class OrgLlmKeyUpdate(BaseModel):
    label: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    org_token_limit: int | None = None
    system_token_limit: int | None = None
    is_active: bool | None = None


class OrgLlmKeyInfo(BaseModel):
    id: str
    org_id: str
    provider: str
    label: str
    api_key_masked: str
    base_url: str | None
    org_token_limit: int | None
    system_token_limit: int | None
    is_active: bool
    usage_total_tokens: int = 0
    created_by: str

    model_config = {"from_attributes": True}


# ── User LLM Key ────────────────────────────────────────

class UserLlmKeyCreate(BaseModel):
    provider: str = Field(..., max_length=32)
    api_key: str
    base_url: str | None = None


class UserLlmKeyInfo(BaseModel):
    id: str
    provider: str
    api_key_masked: str
    base_url: str | None
    is_active: bool

    model_config = {"from_attributes": True}


# ── User LLM Config ─────────────────────────────────────

class LlmConfigItem(BaseModel):
    provider: str
    key_source: str = Field(..., pattern=r"^(org|personal)$")
    org_llm_key_id: str | None = None


class UserLlmConfigUpdate(BaseModel):
    org_id: str
    configs: list[LlmConfigItem]


class UserLlmConfigInfo(BaseModel):
    provider: str
    key_source: str
    org_llm_key_id: str | None = None
    org_llm_key_label: str | None = None

    model_config = {"from_attributes": True}


class LlmConfigUpdateResult(BaseModel):
    needs_restart: bool = False
    affected_instances: list[dict] = []


# ── Instance LLM Config (read-only) ─────────────────────

class InstanceLlmConfigInfo(BaseModel):
    provider: str
    key_source: str
    key_label: str | None = None
    api_key_masked: str | None = None


# ── Available Key (for selector) ────────────────────────

class AvailableLlmKey(BaseModel):
    id: str
    provider: str
    label: str
    api_key_masked: str
    is_active: bool
