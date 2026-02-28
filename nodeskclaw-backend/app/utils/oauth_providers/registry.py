"""Provider registry: register / lookup by name."""

import logging

from app.utils.oauth_providers.base import OAuthProvider

logger = logging.getLogger(__name__)

_providers: dict[str, OAuthProvider] = {}


def register_provider(provider: OAuthProvider) -> None:
    _providers[provider.name] = provider
    logger.info("OAuth provider registered: %s", provider.name)


def get_provider(name: str) -> OAuthProvider:
    provider = _providers.get(name)
    if provider is None:
        raise ValueError(f"Unknown OAuth provider: {name}")
    return provider
