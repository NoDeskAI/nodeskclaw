"""Pydantic schemas for LLM key management APIs."""

from pydantic import BaseModel, Field, field_validator


def _normalize_base_url(v: str | None) -> str | None:
    if not v or not v.strip():
        return v
    v = v.strip()
    if not v.startswith(("http://", "https://")):
        v = f"https://{v}"
    return v


# ── Model Info ───────────────────────────────────────────

class ModelInfo(BaseModel):
    id: str
    name: str
    context_window: int | None = None
    max_tokens: int | None = None


class ProviderModelsResponse(BaseModel):
    provider: str
    models: list[ModelInfo]


# ── Org Model Provider (was OrgLlmKey) ──────────────────

class OrgModelProviderCreate(BaseModel):
    provider: str = Field(..., max_length=32)
    label: str | None = Field(None, max_length=128)
    api_key: str
    base_url: str | None = None
    api_type: str | None = None
    org_token_limit: int | None = None
    system_token_limit: int | None = None
    skip_ssl_verify: bool = False

    _normalize_base_url_field = field_validator("base_url", mode="before")(_normalize_base_url)


class OrgModelProviderUpdate(BaseModel):
    label: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    api_type: str | None = None
    org_token_limit: int | None = None
    system_token_limit: int | None = None
    is_active: bool | None = None
    allowed_models: list[str] | None = None
    skip_ssl_verify: bool | None = None

    _normalize_base_url_field = field_validator("base_url", mode="before")(_normalize_base_url)


class OrgModelProviderInfo(BaseModel):
    id: str
    org_id: str
    provider: str
    label: str | None
    api_key_masked: str
    base_url: str | None
    api_type: str | None = None
    org_token_limit: int | None
    system_token_limit: int | None
    is_active: bool
    skip_ssl_verify: bool = False
    allowed_models: list[str] | None = None
    usage_total_tokens: int = 0
    created_by: str

    model_config = {"from_attributes": True}


# backward-compat aliases
OrgLlmKeyCreate = OrgModelProviderCreate
OrgLlmKeyUpdate = OrgModelProviderUpdate
OrgLlmKeyInfo = OrgModelProviderInfo


# ── User LLM Key ────────────────────────────────────────

class UserLlmKeyCreate(BaseModel):
    provider: str = Field(..., max_length=32)
    api_key: str | None = None
    base_url: str | None = None
    api_type: str | None = None
    skip_ssl_verify: bool = False

    _normalize_base_url_field = field_validator("base_url", mode="before")(_normalize_base_url)


class UserLlmKeyInfo(BaseModel):
    id: str
    provider: str
    api_key_masked: str
    base_url: str | None
    api_type: str | None
    is_active: bool
    skip_ssl_verify: bool = False

    model_config = {"from_attributes": True}


# ── LLM Config Item (deploy request) ────────────────────

class LlmConfigItem(BaseModel):
    provider: str
    key_source: str = Field(default="org", pattern=r"^(org|personal)$")
    selected_models: list[dict] | None = None
    base_url: str | None = None
    api_type: str | None = None

    _normalize_base_url_field = field_validator("base_url", mode="before")(_normalize_base_url)


# ── Instance Provider Config ────────────────────────────

class InstanceProviderConfigEntry(BaseModel):
    provider: str
    key_source: str
    selected_models: list[dict] | None = None
    personal_key_masked: str | None = None
    base_url: str | None = None
    api_type: str | None = None


class InstanceProviderConfigItem(BaseModel):
    provider: str
    key_source: str = Field(..., pattern=r"^(org|personal)$")
    selected_models: list[dict] | None = None
    base_url: str | None = None
    api_type: str | None = None

    _normalize_base_url_field = field_validator("base_url", mode="before")(_normalize_base_url)


class InstanceProviderConfigUpdate(BaseModel):
    configs: list[InstanceProviderConfigItem]


class LlmConfigUpdateResult(BaseModel):
    needs_restart: bool = False
    affected_instances: list[dict] = []


# ── Instance LLM Config (admin read-only) ────────────────

class InstanceLlmConfigInfo(BaseModel):
    provider: str
    key_source: str
    api_key_masked: str | None = None


# ── Available Model Provider (for selector) ──────────────

class AvailableModelProvider(BaseModel):
    id: str
    provider: str
    label: str | None
    api_key_masked: str
    is_active: bool
    allowed_models: list[str] | None = None
    api_type: str | None = None
    base_url: str | None = None
    skip_ssl_verify: bool = False


AvailableLlmKey = AvailableModelProvider


# ── OpenClaw Pod Provider Config (live read) ─────────────

class OpenClawProviderEntry(BaseModel):
    provider: str
    base_url: str
    is_proxy: bool
    key_source: str | None = None
    api_key_masked: str | None = None


class OpenClawConfigResponse(BaseModel):
    data_source: str
    providers: list[OpenClawProviderEntry]


# ── Test Connection ──────────────────────────────────────

class LlmTestConnectionRequest(BaseModel):
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    api_type: str | None = None
    org_id: str | None = None
    skip_ssl_verify: bool = False
    model: str | None = None

    _normalize_base_url_field = field_validator("base_url", mode="before")(_normalize_base_url)


class LlmTestConnectionResult(BaseModel):
    ok: bool
    message: str
    tested_model: str | None = None
    latency_ms: int | None = None
    error_detail: str | None = None


# ── Deprecated (kept for import compat) ──────────────────

class UserLlmConfigInfo(BaseModel):
    provider: str
    key_source: str
    selected_models: list[dict] | None = None
    model_config = {"from_attributes": True}


class UserLlmConfigUpdate(BaseModel):
    org_id: str
    configs: list[LlmConfigItem]
    instance_id: str | None = None
