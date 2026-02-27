"""Base class for channel adapters — abstracts message delivery to Human Hex endpoints."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    """Abstract base for delivering messages from workspace to human via external channel."""

    @abstractmethod
    async def send_message(
        self,
        *,
        channel_config: dict,
        sender_name: str,
        content: str,
        workspace_name: str,
        metadata: dict | None = None,
    ) -> bool:
        """Send a message to the human via the external channel.

        Returns True if delivery succeeded.
        """
        ...

    @abstractmethod
    async def send_approval_request(
        self,
        *,
        channel_config: dict,
        agent_name: str,
        action_type: str,
        proposal: dict,
        workspace_name: str,
        callback_url: str,
    ) -> bool:
        """Send a structured approval request card to the human.

        Returns True if delivery succeeded.
        """
        ...
