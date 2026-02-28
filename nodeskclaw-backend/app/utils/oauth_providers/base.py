"""Abstract base for OAuth providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OAuthUserInfo:
    """Provider-agnostic user info returned after OAuth code exchange."""

    provider: str
    provider_user_id: str
    provider_tenant_id: str | None
    name: str
    email: str | None
    avatar_url: str | None


class OAuthProvider(ABC):
    """Each OAuth provider (Feishu, DingTalk, WeCom ...) implements this interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier, e.g. 'feishu', 'dingtalk'."""
        ...

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str | None = None) -> OAuthUserInfo:
        """Exchange an authorization code for user info."""
        ...
