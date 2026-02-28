"""OAuth provider registry and base classes."""

from app.utils.oauth_providers.base import OAuthProvider, OAuthUserInfo
from app.utils.oauth_providers.registry import get_provider, register_provider

__all__ = ["OAuthProvider", "OAuthUserInfo", "get_provider", "register_provider"]
