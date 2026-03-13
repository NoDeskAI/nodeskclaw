"""Application settings loaded from environment variables."""

import logging
import re
import socket

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────
    APP_NAME: str = "NoDeskClaw"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    LOG_SQL: bool = False

    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str = ""  # PostgreSQL，从 .env 读取
    DATABASE_NAME_SUFFIX: str = ""  # auto = 用本机 hostname，留空 = 使用 DATABASE_URL 原始库名

    @model_validator(mode="after")
    def _resolve_database_url(self) -> "Settings":
        if not self.DATABASE_NAME_SUFFIX:
            return self
        suffix = self.DATABASE_NAME_SUFFIX
        if suffix == "auto":
            raw = socket.gethostname()
            suffix = re.sub(r"[^a-z0-9]", "_", raw.lower()).strip("_")
            suffix = re.sub(r"_local$", "", suffix)
            suffix = re.sub(r"_+", "_", suffix)
            suffix = suffix[:40]
        base_url, sep, db_name = self.DATABASE_URL.rpartition("/")
        if sep:
            self.DATABASE_URL = f"{base_url}/{db_name}_{suffix}"
        return self

    _INSECURE_DEFAULTS = frozenset({
        "change-me-in-production",
        "change-me-32-bytes-base64-key__=",
    })

    @model_validator(mode="after")
    def _check_insecure_defaults(self) -> "Settings":
        if self.DEBUG:
            return self
        issues: list[str] = []
        if self.JWT_SECRET in self._INSECURE_DEFAULTS:
            issues.append("JWT_SECRET")
        if self.ENCRYPTION_KEY in self._INSECURE_DEFAULTS:
            issues.append("ENCRYPTION_KEY")
        if issues:
            msg = (
                f"{', '.join(issues)} 仍为默认值，生产环境存在严重安全风险。"
                " 请在 .env 中设置安全的随机值。"
            )
            raise ValueError(msg)
        return self

    # ── JWT ──────────────────────────────────────────────
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # ── 登录安全 ─────────────────────────────────────────
    LOGIN_EMAIL_WHITELIST: str = ""  # 逗号分隔的域名列表，为空则不限制

    # ── CE 超管 ──────────────────────────────────────────
    INIT_ADMIN_ACCOUNT: str = "admin"  # 默认超管 username，留空则跳过自动创建
    RESET_ADMIN_PASSWORD: bool = False  # 设为 True 后重启强制重置超管密码

    # ── EE 平台管理员 ─────────────────────────────────────
    INIT_EE_ADMIN_ACCOUNT: str = "deskclaw-admin"  # EE Admin 后台管理员 username，留空则跳过
    RESET_EE_ADMIN_PASSWORD: bool = False  # 设为 True 后重启强制重置 EE 管理员密码

    # ── Encryption (AES-256-GCM for KubeConfig) ─────────
    ENCRYPTION_KEY: str = "change-me-32-bytes-base64-key__="

    # ── 飞书 SSO（Admin 应用） ────────────────────────────
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_REDIRECT_URI: str = ""

    # ── 飞书 SSO（Portal 应用，可选） ─────────────────────
    FEISHU_APP_ID_PORTAL: str = ""
    FEISHU_APP_SECRET_PORTAL: str = ""

    # ── Portal ────────────────────────────────────────────
    PORTAL_BASE_URL: str = ""  # 用户门户基础 URL，如 https://portal.example.com

    # ── 云平台 ──────────────────────────────────────────
    VKE_SUBNET_ID: str = ""

    # ── LLM Proxy ─────────────────────────────────────────
    NODESKCLAW_HOST: str = ""  # 外部可达域名，如 https://nodeskclaw.example.com（废弃，保留兼容）
    LLM_PROXY_URL: str = ""  # 独立 LLM Proxy 服务外部地址，如 https://llm-proxy.example.com
    LLM_PROXY_INTERNAL_URL: str = ""  # K8s 集群内网地址，用于 openclaw.json 中的 baseUrl（绕过 ALB）

    # ── Agent API（AI 员工 Pod 回调后端的内网地址）────────
    AGENT_API_BASE_URL: str = "http://localhost:8000/api/v1"

    # ── 出站代理（用于访问 OpenAI/Anthropic 等外部 API）────
    HTTPS_PROXY: str = ""

    # ── Egress NetworkPolicy（AI 员工 Pod 出站流量控制）────
    EGRESS_DENY_CIDRS: str = "10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    EGRESS_ALLOW_PORTS: str = "80,443"

    # ── GeneHub Registry ────────────────────────────────
    GENEHUB_REGISTRY_URL: str = ""  # e.g. https://genehub.example.com
    GENEHUB_API_KEY: str = ""       # publisher-level API Key
    GENEHUB_WEB_URL: str = ""       # GeneHub Web UI, e.g. https://genehub.example.com

    # ── TOS 对象存储 ─────────────────────────────────────
    TOS_ENDPOINT: str = ""
    TOS_REGION: str = ""
    TOS_BUCKET: str = ""
    TOS_ACCESS_KEY_ID: str = ""
    TOS_SECRET_ACCESS_KEY: str = ""
    TOS_KEY_PREFIX: str = ""

    # ── CORS ─────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:4517", "http://localhost:4518"]


settings = Settings()
