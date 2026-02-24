"""SSE Listener — maintains long-lived SSE connections to OpenClaw instances.

Connects to each workspace agent's SSE endpoint via its Ingress domain,
receives collaboration messages, and delegates to collaboration_service.
"""

import asyncio
import json
import logging
import time

import httpx

logger = logging.getLogger(__name__)

SSE_PATH = "/sse/events"
HEARTBEAT_TIMEOUT_S = 45
RECONNECT_BASE_S = 2
RECONNECT_MAX_S = 30
INITIAL_CONNECT_DELAY_S = 5


class SSEListenerManager:
    """Manages SSE connections to OpenClaw instance channel plugins."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._stop_events: dict[str, asyncio.Event] = {}
        self._healthy: set[str] = set()
        self._workspace_map: dict[str, str] = {}

    @property
    def connected_instances(self) -> list[str]:
        return [iid for iid, t in self._tasks.items() if not t.done()]

    @property
    def healthy_instances(self) -> set[str]:
        return set(self._healthy)

    async def connect(
        self,
        instance_id: str,
        ingress_domain: str,
        *,
        delay: float = 0,
        workspace_id: str = "",
    ) -> None:
        """Start an SSE listener for the given instance."""
        if instance_id in self._tasks and not self._tasks[instance_id].done():
            logger.debug("SSE listener already running for %s, skipping", instance_id)
            return

        if workspace_id:
            self._workspace_map[instance_id] = workspace_id

        stop_event = asyncio.Event()
        self._stop_events[instance_id] = stop_event
        self._tasks[instance_id] = asyncio.create_task(
            self._listen_loop(instance_id, ingress_domain, stop_event, delay),
            name=f"sse-listener-{instance_id[:8]}",
        )
        logger.info("SSE listener started for %s (%s)", instance_id, ingress_domain)

    async def disconnect(self, instance_id: str) -> None:
        """Stop the SSE listener for the given instance."""
        was_healthy = instance_id in self._healthy
        self._healthy.discard(instance_id)
        self._workspace_map.pop(instance_id, None)

        stop_event = self._stop_events.pop(instance_id, None)
        if stop_event:
            stop_event.set()

        task = self._tasks.pop(instance_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if was_healthy:
            logger.info("SSE listener stopped for %s (was healthy)", instance_id)
        else:
            logger.info("SSE listener stopped for %s", instance_id)

    async def disconnect_all(self) -> None:
        """Stop all SSE listeners (called on shutdown)."""
        ids = list(self._tasks.keys())
        for iid in ids:
            await self.disconnect(iid)

    def _set_healthy(self, instance_id: str, healthy: bool) -> None:
        """Update healthy state and broadcast change to workspace SSE stream."""
        was_healthy = instance_id in self._healthy
        if healthy == was_healthy:
            return

        if healthy:
            self._healthy.add(instance_id)
        else:
            self._healthy.discard(instance_id)

        ws_id = self._workspace_map.get(instance_id)
        if ws_id:
            try:
                from app.api.workspaces import broadcast_event
                event = "agent:sse_connected" if healthy else "agent:sse_disconnected"
                broadcast_event(ws_id, event, {"instance_id": instance_id})
            except Exception:
                pass

    async def _listen_loop(
        self,
        instance_id: str,
        ingress_domain: str,
        stop_event: asyncio.Event,
        initial_delay: float,
    ) -> None:
        """Reconnection loop with exponential backoff."""
        if initial_delay > 0:
            await asyncio.sleep(initial_delay)

        url = f"https://{ingress_domain}{SSE_PATH}"
        backoff = RECONNECT_BASE_S

        while not stop_event.is_set():
            try:
                await self._listen_once(instance_id, url, stop_event)
                backoff = RECONNECT_BASE_S
            except asyncio.CancelledError:
                self._set_healthy(instance_id, False)
                return
            except Exception as e:
                self._set_healthy(instance_id, False)
                logger.warning(
                    "SSE connection lost for %s: %s (reconnect in %.0fs)",
                    instance_id, e, backoff,
                )

            if stop_event.is_set():
                return

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_S)

    async def _listen_once(
        self,
        instance_id: str,
        url: str,
        stop_event: asyncio.Event,
    ) -> None:
        """Single SSE connection session."""
        last_event_time = time.monotonic()

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=HEARTBEAT_TIMEOUT_S + 10, write=10, pool=10),
            verify=False,
        ) as client:
            async with client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    raise ConnectionError(f"SSE endpoint returned {resp.status_code}")

                self._set_healthy(instance_id, True)
                logger.info("SSE connected to %s (%s)", instance_id, url)

                event_type = ""
                data_buffer = ""

                async for line in resp.aiter_lines():
                    if stop_event.is_set():
                        return

                    now = time.monotonic()
                    if now - last_event_time > HEARTBEAT_TIMEOUT_S:
                        raise ConnectionError("Heartbeat timeout")

                    if line.startswith("event: "):
                        event_type = line[7:].strip()
                        last_event_time = now
                        continue

                    if line.startswith("data: "):
                        data_buffer = line[6:]
                        last_event_time = now

                        if event_type == "heartbeat":
                            event_type = ""
                            data_buffer = ""
                            continue

                        if event_type == "message" and data_buffer:
                            await self._handle_message(instance_id, data_buffer)

                        event_type = ""
                        data_buffer = ""
                        continue

                    if line.startswith(":"):
                        last_event_time = now
                        continue

    async def _handle_message(self, instance_id: str, raw_data: str) -> None:
        """Parse and dispatch a collaboration message."""
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON from SSE (%s): %s", instance_id, raw_data[:200])
            return

        workspace_id = data.get("workspace_id", "")
        source_instance_id = data.get("source_instance_id", "")
        target = data.get("target", "")
        text = data.get("text", "")
        depth = data.get("depth", 0)

        if not workspace_id or not source_instance_id or not text:
            logger.warning("Incomplete collaboration message from %s", instance_id)
            return

        from app.services.collaboration_service import handle_collaboration_message

        try:
            await handle_collaboration_message(
                workspace_id=workspace_id,
                source_instance_id=source_instance_id,
                target=target,
                text=text,
                depth=depth,
            )
        except Exception as e:
            logger.error("Failed to handle collaboration message from %s: %s", instance_id, e)


sse_listener_manager = SSEListenerManager()
