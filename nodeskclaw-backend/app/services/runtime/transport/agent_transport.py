"""AgentTransportAdapter — delivers messages to agent nodes via RuntimeAdapter."""

from __future__ import annotations

import json
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.services.runtime.messaging.envelope import MessageEnvelope
from app.services.runtime.transport.base import DeliveryResult

logger = logging.getLogger(__name__)

NO_REPLY_BUFFER_SIZE = 30


def _get_instance_connection(inst) -> tuple[str, str]:
    env_vars = json.loads(inst.env_vars or "{}")
    token = env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")
    domain = inst.ingress_domain or ""
    base_url = f"https://{domain}" if domain else ""
    return base_url, token


def _parse_delegation(response: str) -> tuple[str, str] | None:
    """Parse delegate:/escalate: prefixes from agent responses."""
    stripped = response.strip()
    for prefix in ("delegate:", "escalate:"):
        if stripped.lower().startswith(prefix):
            target = stripped[len(prefix):].strip().split()[0] if stripped[len(prefix):].strip() else ""
            if target:
                return (prefix.rstrip(":"), target)
    return None


class AgentTransportAdapter:
    """Delivers messages to agent nodes by resolving the runtime adapter from the registry."""

    transport_id = "agent"

    def __init__(self) -> None:
        self._healthy_agents: set[str] = set()

    @property
    def healthy_instances(self) -> set[str]:
        return set(self._healthy_agents)

    async def deliver(
        self,
        envelope: MessageEnvelope,
        target_node_id: str,
        *,
        workspace_id: str = "",
        db: AsyncSession | None = None,
    ) -> DeliveryResult:
        start = time.monotonic()
        logger.debug(
            "AgentTransportAdapter.deliver: envelope=%s target=%s",
            envelope.id, target_node_id,
        )

        if db is None:
            from app.core.deps import async_session_factory
            async with async_session_factory() as db:
                return await self._do_deliver(envelope, target_node_id, workspace_id, db, start)
        return await self._do_deliver(envelope, target_node_id, workspace_id, db, start)

    async def _do_deliver(
        self,
        envelope: MessageEnvelope,
        target_node_id: str,
        workspace_id: str,
        db: AsyncSession,
        start: float,
    ) -> DeliveryResult:
        from app.models.instance import Instance
        from app.models.node_card import NodeCard
        from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY

        card_result = await db.execute(
            select(NodeCard).where(
                NodeCard.node_id == target_node_id,
                NodeCard.workspace_id == workspace_id,
                not_deleted(NodeCard),
            )
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="node_card_not_found",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        inst_result = await db.execute(
            select(Instance).where(
                Instance.id == target_node_id,
                not_deleted(Instance),
            )
        )
        inst = inst_result.scalar_one_or_none()
        if inst is None:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="instance_not_found",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        base_url, token = _get_instance_connection(inst)
        if not base_url or not token:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="missing_connection_info",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        meta = card.metadata_ or {}
        runtime_id = meta.get("runtime", "openclaw")
        adapter_spec = RUNTIME_REGISTRY.get(runtime_id)
        if adapter_spec is None:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error=f"runtime_not_found:{runtime_id}",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        adapter = adapter_spec.adapter

        agent_name = card.name or inst.name
        data = envelope.data
        if data is None:
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error="no_envelope_data",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        from app.services import workspace_message_service as msg_service

        context_prompt = msg_service.build_context_prompt(
            workspace_name="",
            agent_display_name=agent_name,
            current_instance_id=target_node_id,
            members=[],
            recent_messages=[],
            workspace_id=workspace_id,
        )

        user_content = f"[{data.sender.name}]: {data.content}"
        new_message = {"role": "user", "content": user_content}

        session = await adapter.create_session(
            instance_id=target_node_id,
            workspace_id=workspace_id,
            base_url=base_url,
            token=token,
            system_prompt=context_prompt,
        )

        from app.api.workspaces import broadcast_event

        broadcast_event(workspace_id, "agent:typing", {
            "instance_id": target_node_id,
            "agent_name": agent_name,
        })

        buffer = ""
        flushed = False
        full_response = ""
        error_msg: str | None = None

        try:
            async for chunk in adapter.send_message(session, new_message, stream=True):
                if chunk.is_error:
                    error_msg = chunk.error_message or "unknown_error"
                    break
                if chunk.is_done:
                    break
                if chunk.content:
                    full_response += chunk.content
                    if not flushed:
                        buffer += chunk.content
                        if len(buffer) > NO_REPLY_BUFFER_SIZE:
                            if msg_service.is_no_reply(buffer.strip()):
                                logger.info("Agent %s replied NO_REPLY", agent_name)
                                broadcast_event(workspace_id, "agent:done", {
                                    "instance_id": target_node_id,
                                    "agent_name": agent_name,
                                })
                                return DeliveryResult(
                                    success=True, target_node_id=target_node_id,
                                    transport=self.transport_id,
                                    latency_ms=int((time.monotonic() - start) * 1000),
                                    extra={"no_reply": True},
                                )
                            broadcast_event(workspace_id, "agent:chunk", {
                                "instance_id": target_node_id,
                                "agent_name": agent_name,
                                "content": buffer,
                                "trace_id": envelope.traceid,
                            })
                            flushed = True
                    else:
                        broadcast_event(workspace_id, "agent:chunk", {
                            "instance_id": target_node_id,
                            "agent_name": agent_name,
                            "content": chunk.content,
                            "trace_id": envelope.traceid,
                        })
        except Exception as e:
            error_msg = str(e)
            logger.error("Agent %s streaming failed: %s", agent_name, e)

        if error_msg:
            broadcast_event(workspace_id, "agent:error", {
                "instance_id": target_node_id,
                "agent_name": agent_name,
                "error": error_msg,
            })
            return DeliveryResult(
                success=False, target_node_id=target_node_id,
                transport=self.transport_id, error=error_msg,
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        if not flushed and buffer:
            if msg_service.is_no_reply(buffer.strip()):
                broadcast_event(workspace_id, "agent:done", {
                    "instance_id": target_node_id, "agent_name": agent_name,
                })
                return DeliveryResult(
                    success=True, target_node_id=target_node_id,
                    transport=self.transport_id,
                    latency_ms=int((time.monotonic() - start) * 1000),
                    extra={"no_reply": True},
                )
            broadcast_event(workspace_id, "agent:chunk", {
                "instance_id": target_node_id, "agent_name": agent_name,
                "content": buffer, "trace_id": envelope.traceid,
            })

        delegation = _parse_delegation(full_response)
        if delegation:
            action, delegate_target = delegation
            logger.info("Agent %s issued %s to %s", agent_name, action, delegate_target)
            try:
                await self._handle_delegation(
                    action, delegate_target, envelope, target_node_id, workspace_id, db,
                )
            except Exception as e:
                logger.warning("Delegation %s->%s failed: %s", action, delegate_target, e)

        if full_response and not msg_service.is_no_reply(full_response.strip()):
            broadcast_event(workspace_id, "agent:done", {
                "instance_id": target_node_id,
                "agent_name": agent_name,
                "full_content": full_response,
                "trace_id": envelope.traceid,
            })
            from app.core.deps import async_session_factory
            async with async_session_factory() as save_db:
                await msg_service.record_message(
                    save_db,
                    workspace_id=workspace_id,
                    sender_type="agent",
                    sender_id=target_node_id,
                    sender_name=agent_name,
                    content=full_response,
                )
        else:
            broadcast_event(workspace_id, "agent:done", {
                "instance_id": target_node_id, "agent_name": agent_name,
            })

        return DeliveryResult(
            success=True, target_node_id=target_node_id,
            transport=self.transport_id,
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    MAX_COLLABORATION_DEPTH = 5

    async def _handle_delegation(
        self,
        action: str,
        target_name: str,
        original_envelope: MessageEnvelope,
        source_node_id: str,
        workspace_id: str,
        db: AsyncSession,
    ) -> None:
        from app.services.runtime.messaging.envelope import (
            IntentType,
            MessageData,
            MessageSender,
            SenderType,
        )

        prev_visited = (
            original_envelope.data.routing.visited if original_envelope.data else []
        )
        if len(prev_visited) >= self.MAX_COLLABORATION_DEPTH:
            logger.warning(
                "Collaboration depth limit (%d) reached, refusing %s from %s",
                self.MAX_COLLABORATION_DEPTH, action, source_node_id,
            )
            return

        if action == "escalate":
            from app.models.node_card import NodeCard
            result = await db.execute(
                select(NodeCard).where(
                    NodeCard.workspace_id == workspace_id,
                    NodeCard.node_type == "human",
                    not_deleted(NodeCard),
                ).limit(1)
            )
            human_card = result.scalar_one_or_none()
            if human_card:
                target_name = human_card.node_id

        new_visited = list(prev_visited) + [source_node_id]

        new_envelope = MessageEnvelope(
            source=f"agent/{source_node_id}",
            type="deskclaw.msg.v1.chat",
            workspaceid=workspace_id,
            causationid=original_envelope.id,
            correlationid=original_envelope.correlationid or original_envelope.id,
            traceid=original_envelope.traceid,
            data=MessageData(
                sender=MessageSender(
                    id=source_node_id,
                    type=SenderType.AGENT,
                    name=f"agent:{source_node_id}",
                    instance_id=source_node_id,
                ),
                intent=IntentType.COLLABORATE,
                content=original_envelope.data.content if original_envelope.data else "",
                extensions={"delegation_action": action, "delegation_from": source_node_id},
            ),
        )
        new_envelope.data.routing.target = target_name
        new_envelope.data.routing.targets = [target_name]
        new_envelope.data.routing.visited = new_visited

        from app.services.runtime.messaging.bus import message_bus
        await message_bus.publish(new_envelope, db=db)

    async def health_check(self, target_node_id: str) -> bool:
        return target_node_id in self._healthy_agents

    async def on_agent_joined(self, instance_id: str) -> None:
        self._healthy_agents.add(instance_id)
        logger.info("AgentTransport: agent joined: %s", instance_id)

        try:
            await self._replay_pending_messages(instance_id)
        except Exception as e:
            logger.warning("AgentTransport: offline replay failed for %s: %s", instance_id, e)

    async def _replay_pending_messages(self, instance_id: str) -> None:
        """Dequeue and deliver all pending messages for a reconnected agent."""
        from app.core.deps import async_session_factory
        from app.services.runtime.messaging.queue import dequeue

        async with async_session_factory() as db:
            items = await dequeue(db, target_node_id=instance_id, batch_size=50)
            if not items:
                return

            logger.info(
                "AgentTransport: replaying %d offline messages for %s",
                len(items), instance_id,
            )
            for item in items:
                try:
                    envelope = MessageEnvelope.from_dict(item.envelope or {})
                    workspace_id = item.workspace_id or envelope.workspaceid
                    result = await self._do_deliver(
                        envelope, instance_id, workspace_id, db, time.monotonic(),
                    )
                    if result.success:
                        from app.services.runtime.messaging.queue import ack
                        await ack(db, str(item.id))
                    else:
                        from app.services.runtime.messaging.queue import nack
                        await nack(db, str(item.id), result.error or "replay_failed")
                except Exception as e:
                    logger.warning("Replay delivery failed for item %s: %s", item.id, e)
            await db.commit()

    async def on_agent_left(self, instance_id: str) -> None:
        self._healthy_agents.discard(instance_id)
        logger.info("AgentTransport: agent left: %s", instance_id)

    async def on_instance_destroyed(self, instance_id: str) -> None:
        self._healthy_agents.discard(instance_id)
        logger.info("AgentTransport: instance destroyed: %s", instance_id)

    async def reconnect_all(self) -> None:
        logger.info("AgentTransport: reconnect_all (placeholder)")

    def get_healthy_agents(self) -> set[str]:
        return set(self._healthy_agents)


agent_transport = AgentTransportAdapter()
