"""Application settings loaded from environment variables."""

import logging
import re
import socket
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_logger = logging.getLogger(__name__)

_K8S_NS_FILE = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")


def _detect_platform_namespace() -> str:
    try:
        return _K8S_NS_FILE.read_text().strip()
    except (FileNotFoundError, PermissionError):
        return "nodeskclaw-system"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────
    APP_NAME: str = "NoDeskClaw"
    APP_VERSION: str = "dev"
    DEBUG: bool = False
    LOG_SQL: bool = False
    LOG_HEALTH_CHECK: bool = False

    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str = ""  # PostgreSQL，从 .env 读取
    DATABASE_NAME_SUFFIX: str = ""  # auto = 用本机 hostname，留空 = 使用 DATABASE_URL 原始库名
    DB_POOL_SIZE: int = 10
    DB_POOL_MAX_OVERFLOW: int = 20

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

    # ── 飞书 SSO（Portal 应用，可选） ─────────────────────
    FEISHU_APP_ID_PORTAL: str = ""
    FEISHU_APP_SECRET_PORTAL: str = ""

    # ── Portal ────────────────────────────────────────────
    PORTAL_BASE_URL: str = ""  # 用户门户基础 URL，如 https://portal.example.com

    # ── 云平台 ──────────────────────────────────────────
    VKE_SUBNET_ID: str = ""

    # ── LLM Proxy ─────────────────────────────────────────
    NODESKCLAW_WEBHOOK_BASE_URL: str = ""  # AI 员工回调后端的基础地址，如 http://nodeskclaw-backend:4510
    NODESKCLAW_HOST: str = ""  # 外部可达域名，如 https://nodeskclaw.example.com（废弃，保留兼容）
    LLM_PROXY_URL: str = ""  # 独立 LLM Proxy 服务外部地址，如 https://llm-proxy.example.com
    LLM_PROXY_INTERNAL_URL: str = ""  # K8s 集群内网地址，用于 openclaw.json 中的 baseUrl（绕过 ALB）

    # ── Agent API（AI 员工 Pod 回调后端的内网地址）────────
    AGENT_API_BASE_URL: str = "http://localhost:4510/api/v1"
    GENE_CALLBACK_SECRET: str = ""
    ALLOW_LEGACY_GENE_CALLBACKS: bool = False

    # ── Agent Tunnel（实例通过 WebSocket 主动连接后端的地址）────
    TUNNEL_BASE_URL: str = ""

    # ── 出站代理（用于访问 OpenAI/Anthropic 等外部 API）────
    HTTPS_PROXY: str = ""

    # ── Platform Namespace（AI 员工 Pod NetworkPolicy 允许访问的后端命名空间）──
    PLATFORM_NAMESPACE: str = _detect_platform_namespace()

    # ── Gene Seed ───────────────────────────────────────
    SEED_GENES: bool = True

    # ── Skill Registries ─────────────────────────────────
    # JSON array of registry configs:
    # [{"type":"genehub","id":"deskhub","url":"https://skills.deskclaw.me","api_key":"","name":"DeskHub"},
    #  {"type":"clawhub","id":"clawhub","url":"https://clawhub.ai","api_key":"","name":"ClawHub"}]
    SKILL_REGISTRIES: str = ""

    # Legacy — non-empty value auto-registers as type=genehub, id=genehub adapter
    GENEHUB_REGISTRY_URL: str = "https://skills.deskclaw.me"
    GENEHUB_API_KEY: str = ""
    GENEHUB_WEB_URL: str = "https://skills.deskclaw.me"

    # ── S3 兼容对象存储 ─────────────────────────────────
    S3_ENDPOINT: str = ""
    S3_REGION: str = ""
    S3_BUCKET: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_KEY_PREFIX: str = ""

    # ── 本地文件存储（S3 未配置时自动启用）─────────────────
    LOCAL_STORAGE_DIR: str = ""

    # ── 匿名安装遥测（CE-only）─────────────────────────────
    TELEMETRY_ENABLED: bool = True
    POSTHOG_HOST: str = "https://us.i.posthog.com"
    POSTHOG_API_KEY: str = "phc_qdVoTVCcHEzgwhZVwtPuu6BeoTJPGNQskeUBcXVxnxuF"

    # ── CORS ─────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:4517", "http://localhost:4518"]


settings = Settings()


def _strip_api_path(base_url: str) -> str:
    parsed = urlsplit(base_url.rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        return base_url.rstrip("/")
    path = parsed.path.rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def get_nodeskclaw_webhook_base_url(cfg: Settings | None = None) -> str:
    active_settings = cfg or settings
    candidates = [
        getattr(active_settings, "NODESKCLAW_WEBHOOK_BASE_URL", ""),
        getattr(active_settings, "NODESKCLAW_HOST", ""),
        _strip_api_path(getattr(active_settings, "AGENT_API_BASE_URL", "")),
    ]
    for candidate in candidates:
        normalized = candidate.rstrip("/") if candidate else ""
        if normalized:
            return normalized
    return ""
