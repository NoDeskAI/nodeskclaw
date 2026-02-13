"""SSE EventBus: broadcast real-time events to connected frontend clients."""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import AsyncIterator

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """Server-Sent Event."""

    event: str  # event type: deploy_progress, pod_status, instance_status, etc.
    data: dict
    id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def format(self) -> str:
        """Format as SSE text."""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        lines.append(f"event: {self.event}")
        lines.append(f"data: {json.dumps(self.data, default=str)}")
        lines.append("")
        return "\n".join(lines) + "\n"


class EventBus:
    """Pub-sub event bus for SSE broadcasting.

    Usage:
        # Publisher
        event_bus.publish("deploy_progress", {"instance_id": "...", "step": 3})

        # Subscriber (SSE endpoint)
        async for event in event_bus.subscribe("deploy_progress"):
            yield event.format()
    """

    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def publish(self, event_type: str, data: dict, event_id: str | None = None):
        """Publish event to all subscribers of the channel."""
        event = SSEEvent(event=event_type, data=data, id=event_id)
        queues = self._channels.get(event_type, [])
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for %s, dropping event", event_type)

    async def subscribe(self, *event_types: str) -> AsyncIterator[SSEEvent]:
        """Subscribe to one or more event types."""
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=100)
        for et in event_types:
            self._channels[et].append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            for et in event_types:
                try:
                    self._channels[et].remove(queue)
                except ValueError:
                    pass

    def subscriber_count(self, event_type: str) -> int:
        return len(self._channels.get(event_type, []))


# Singleton
event_bus = EventBus()
