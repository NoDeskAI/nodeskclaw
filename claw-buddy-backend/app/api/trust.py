"""Trust Policy API — graduated autonomy for agent actions."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_db
from app.models.base import not_deleted
from app.models.trust_policy import TrustPolicy

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


class TrustPolicyCreate(BaseModel):
    workspace_id: str
    agent_instance_id: str
    action_type: str
    grant_type: str


class ApprovalRequest(BaseModel):
    workspace_id: str
    agent_instance_id: str
    action_type: str
    proposal: dict


class ApprovalResponse(BaseModel):
    decision: str  # "allow_once" | "allow_always" | "deny"


@router.get("/trust-policies")
async def list_trust_policies(
    workspace_id: str,
    agent_instance_id: str | None = None,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    query = select(TrustPolicy).where(
        TrustPolicy.workspace_id == workspace_id,
        not_deleted(TrustPolicy),
    )
    if agent_instance_id:
        query = query.where(TrustPolicy.agent_instance_id == agent_instance_id)
    result = await db.execute(query)
    items = [
        {
            "id": p.id, "workspace_id": p.workspace_id,
            "agent_instance_id": p.agent_instance_id,
            "action_type": p.action_type,
            "granted_by": p.granted_by,
            "grant_type": p.grant_type,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in result.scalars().all()
    ]
    return _ok(items)


@router.post("/trust-policies")
async def create_trust_policy(
    body: TrustPolicyCreate,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    policy = TrustPolicy(
        id=str(uuid.uuid4()),
        workspace_id=body.workspace_id,
        agent_instance_id=body.agent_instance_id,
        action_type=body.action_type,
        granted_by=org.get("user_id", ""),
        grant_type=body.grant_type,
    )
    db.add(policy)
    await db.commit()
    return _ok({"id": policy.id, "grant_type": policy.grant_type})


@router.get("/trust-policies/check")
async def check_trust(
    workspace_id: str,
    agent_instance_id: str,
    action_type: str,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    """Check if an agent has an 'always' trust policy for a given action."""
    result = await db.execute(
        select(TrustPolicy).where(
            TrustPolicy.workspace_id == workspace_id,
            TrustPolicy.agent_instance_id == agent_instance_id,
            TrustPolicy.action_type == action_type,
            TrustPolicy.grant_type == "always",
            not_deleted(TrustPolicy),
        ).limit(1)
    )
    policy = result.scalar_one_or_none()
    return _ok({"trusted": policy is not None})


@router.post("/approval-requests")
async def submit_approval_request(
    body: ApprovalRequest,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    """Submit an approval request that routes to Human Hex via channel adapter."""
    from app.models.workspace_member import WorkspaceMember
    from app.services import corridor_router

    has_topo = await corridor_router.has_any_connections(body.workspace_id, db)
    if not has_topo:
        return _ok({"status": "no_topology", "message": "No corridor topology configured"})

    from app.models.instance import Instance
    inst_q = await db.execute(
        select(Instance).where(Instance.id == body.agent_instance_id, not_deleted(Instance))
    )
    inst = inst_q.scalar_one_or_none()
    if not inst or inst.hex_position_q is None:
        return _ok({"status": "agent_not_placed"})

    endpoints = await corridor_router.get_reachable_endpoints(
        body.workspace_id, inst.hex_position_q, inst.hex_position_r, db,
    )
    human_endpoints = [ep for ep in endpoints if ep.endpoint_type == "human"]
    if not human_endpoints:
        return _ok({"status": "no_human_reachable"})

    from app.models.decision_record import DecisionRecord
    record = DecisionRecord(
        id=str(uuid.uuid4()),
        workspace_id=body.workspace_id,
        agent_instance_id=body.agent_instance_id,
        decision_type=body.action_type,
        context_summary=f"Agent requested approval for {body.action_type}",
        proposal=body.proposal,
        outcome="pending",
    )
    db.add(record)
    await db.commit()

    return _ok({
        "status": "routed",
        "human_targets": len(human_endpoints),
        "decision_record_id": record.id,
    })


@router.post("/approval-requests/{record_id}/resolve")
async def resolve_approval(
    record_id: str,
    body: ApprovalResponse,
    org: dict = Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    """Human resolves an approval request."""
    from datetime import datetime, timezone
    from app.models.decision_record import DecisionRecord

    result = await db.execute(
        select(DecisionRecord).where(DecisionRecord.id == record_id, not_deleted(DecisionRecord))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(404, "decision record not found")

    record.reviewer_id = org.get("user_id")
    record.review_type = "human"
    record.resolved_at = datetime.now(timezone.utc)

    if body.decision == "allow_once":
        record.outcome = "success"
        record.review_comment = "Allowed once"
    elif body.decision == "allow_always":
        record.outcome = "success"
        record.review_comment = "Allowed always"
        policy = TrustPolicy(
            id=str(uuid.uuid4()),
            workspace_id=record.workspace_id,
            agent_instance_id=record.agent_instance_id,
            action_type=record.decision_type,
            granted_by=org.get("user_id", ""),
            grant_type="always",
        )
        db.add(policy)
    elif body.decision == "deny":
        record.outcome = "rejected"
        record.review_comment = "Denied"

    await db.commit()
    return _ok({"decision": body.decision, "record_id": record.id})
