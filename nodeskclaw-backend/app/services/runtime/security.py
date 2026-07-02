"""Security model for the runtime messaging platform.

Enforces:
  - Workspace isolation: messages, blackboard, topology, members never cross workspaces
  - Agent sandbox integration hooks for ComputeProvider (NetworkPolicy)

Topology-based message permission is enforced in corridor_router and RoutingMiddleware.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class SecurityContext:
    user_id: str | None = None
    workspace_id: str = ""
    source_node_id: str = ""
    is_system: bool = False
    roles: list[str] = field(default_factory=list)


async def check_workspace_isolation(
    db: AsyncSession,
    workspace_id: str,
    node_ids: list[str],
) -> tuple[bool, str]:
    """Verify all node_ids belong to the same workspace."""
    if not node_ids:
        return True, "empty"

    from app.models.node_card import NodeCard
    from app.models.base import not_deleted
    from sqlalchemy import select, func

    count_q = await db.execute(
        select(func.count()).select_from(NodeCard).where(
            NodeCard.node_id.in_(node_ids),
            NodeCard.workspace_id == workspace_id,
            not_deleted(NodeCard),
        )
    )
    found = count_q.scalar() or 0
    if found != len(node_ids):
        return False, f"workspace_isolation_violation: expected {len(node_ids)} nodes, found {found}"
    return True, "ok"


@dataclass
class SandboxPolicy:
    """Describes network sandbox rules for agent compute."""
    allow_egress_to: list[str] = field(default_factory=list)
    deny_egress_to: list[str] = field(default_factory=list)
    allow_ingress_from: list[str] = field(default_factory=list)
    max_bandwidth_mbps: int = 100
    dns_policy: str = "ClusterFirst"


def build_k8s_network_policy(
    namespace: str,
    instance_id: str,
    policy: SandboxPolicy,
) -> dict:
    """Build a K8s NetworkPolicy manifest for agent sandboxing."""
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": f"sandbox-{instance_id}",
            "namespace": namespace,
        },
        "spec": {
            "podSelector": {
                "matchLabels": {"app": f"deskclaw-{instance_id}"},
            },
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [
                {
                    "from": [
                        {"podSelector": {"matchLabels": {"app": src}}}
                        for src in policy.allow_ingress_from
                    ],
                }
            ] if policy.allow_ingress_from else [],
            "egress": [
                {"to": [{"podSelector": {}}], "ports": [{"port": 53, "protocol": "UDP"}]},
            ],
        },
    }


