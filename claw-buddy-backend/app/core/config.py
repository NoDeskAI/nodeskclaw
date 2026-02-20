"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── App ──────────────────────────────────────────────
    APP_NAME: str = "ClawBuddy"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # ── Database ─────────────────────────────────────────
    DATABASE_URL: str = ""  # 火山云 RDS PostgreSQL，从 .env 读取

    # ── JWT ──────────────────────────────────────────────
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # ── Encryption (AES-256-GCM for KubeConfig) ─────────
    ENCRYPTION_KEY: str = "change-me-32-bytes-base64-key__="

    # ── 飞书 SSO ────────────────────────────────────────
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_REDIRECT_URI: str = ""

    # ── 火山云 ──────────────────────────────────────────
    VKE_SUBNET_ID: str = ""

    # ── LLM Proxy ─────────────────────────────────────────
    CLAWBUDDY_HOST: str = ""  # 外部可达域名，如 https://clawbuddy.example.com

    # ── 出站代理（用于访问 OpenAI/Anthropic 等外部 API）────
    HTTPS_PROXY: str = ""

    # ── CORS ─────────────────────────────────────────────
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]


settings = Settings()
