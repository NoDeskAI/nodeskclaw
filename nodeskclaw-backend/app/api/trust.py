"""Trust Policy API — graduated autonomy for agent actions."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_org, get_current_org_or_agent, get_db
from app.models.base import not_deleted
from app.models.decision_record import DecisionRecord
from app.models.trust_policy import TrustPolicy
from app.models.workspace import Workspace
from app.services.workspace_actor_access import get_current_agent_id, require_agent_in_workspace

logger = logging.getLogger(__name__)
router = APIRouter()


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _org_id(org) -> str:
    return org.id if hasattr(org, "id") else org.get("org_id", "")


def _user_id(user) -> str:
    return str(user.id) if user is not None and hasattr(user, "id") else ""


def _trust_http_error(status_code: int, error_code: int, message_key: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message_key": message_key,
            "message": message,
        },
    )


async def _get_workspace(workspace_id: str, org, db: AsyncSession) -> Workspace:
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.org_id == _org_id(org),
            not_deleted(Workspace),
        )
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise _trust_http_error(404, 40490, "errors.workspace.not_found", "办公室不存在")
    return workspace


async def _resolve_agent_scope(
    workspace_id: str,
    requested_agent_id: str | None,
    db: AsyncSession,
) -> str | None:
    current_agent_id = get_current_agent_id()
    if current_agent_id is None:
        return requested_agent_id

    await require_agent_in_workspace(workspace_id, current_agent_id, db)
    if requested_agent_id and requested_agent_id != current_agent_id:
        raise _trust_http_error(
            403,
            40307,
            "errors.collaboration.agent_scope_forbidden",
            "AI 员工只能访问自己的决策记录",
        )
    return current_agent_id


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
    context_summary: str | None = None


class ApprovalResponse(BaseModel):
    decision: str  # "allow_once" | "allow_always" | "deny"


@router.get("/trust-policies")
async def list_trust_policies(
    workspace_id: str,
    agent_instance_id: str | None = None,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _get_workspace(workspace_id, org, db)
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
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _get_workspace(body.workspace_id, org, db)
    policy = TrustPolicy(
        id=str(uuid.uuid4()),
        workspace_id=body.workspace_id,
        agent_instance_id=body.agent_instance_id,
        action_type=body.action_type,
        granted_by=_user_id(user),
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
    org_ctx=Depends(get_current_org_or_agent), db: AsyncSession = Depends(get_db),
):
    """Check if an agent has an 'always' trust policy for a given action."""
    _, org = org_ctx
    await _get_workspace(workspace_id, org, db)
    effective_agent_id = await _resolve_agent_scope(workspace_id, agent_instance_id, db)
    result = await db.execute(
        select(TrustPolicy).where(
            TrustPolicy.workspace_id == workspace_id,
            TrustPolicy.agent_instance_id == effective_agent_id,
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
    org_ctx=Depends(get_current_org_or_agent), db: AsyncSession = Depends(get_db),
):
    """Submit an approval request that routes to Human Hex via channel adapter."""
    from app.models.corridor import HumanHex
    from app.services import corridor_router

    _, org = org_ctx
    ws = await _get_workspace(body.workspace_id, org, db)
    effective_agent_id = await _resolve_agent_scope(body.workspace_id, body.agent_instance_id, db)
    has_topo = await corridor_router.has_any_connections(body.workspace_id, db)
    if not has_topo:
        return _ok({"status": "no_topology", "message": "No corridor topology configured"})

    hex_pos = await corridor_router.get_agent_hex_in_workspace(
        effective_agent_id, body.workspace_id, db,
    )
    if hex_pos is None:
        return _ok({"status": "agent_not_placed"})

    endpoints, _hooks = await corridor_router.get_reachable_endpoints(
        body.workspace_id, hex_pos[0], hex_pos[1], db,
    )
    human_endpoints = [ep for ep in endpoints if ep.endpoint_type == "human"]
    if not human_endpoints:
        return _ok({"status": "no_human_reachable"})

    record = DecisionRecord(
        id=str(uuid.uuid4()),
        workspace_id=body.workspace_id,
        agent_instance_id=effective_agent_id,
        decision_type=body.action_type,
        context_summary=body.context_summary or f"AI Employee requested approval for {body.action_type}",
        proposal=body.proposal,
        outcome="pending",
    )
    db.add(record)
    await db.commit()

    from app.core.config import get_nodeskclaw_webhook_base_url, settings

    workspace_name = ws.name if ws else body.workspace_id

    callback_base = get_nodeskclaw_webhook_base_url()
    callback_url = f"{callback_base}/api/v1/workspaces/approval-requests/{record.id}/resolve"

    for ep in human_endpoints:
        hh_q = await db.execute(
            select(HumanHex).where(
                HumanHex.id == ep.entity_id,
                not_deleted(HumanHex),
            )
        )
        hh = hh_q.scalar_one_or_none()
        if hh and hh.channel_type == "feishu" and hh.channel_config:
            try:
                from app.services.channel_adapters.feishu import FeishuChannelAdapter

                adapter = FeishuChannelAdapter(
                    app_id=settings.FEISHU_APP_ID_PORTAL,
                    app_secret=settings.FEISHU_APP_SECRET_PORTAL,
                )
                await adapter.send_approval_request(
                    channel_config=hh.channel_config,
                    agent_name=effective_agent_id,
                    action_type=body.action_type,
                    proposal=body.proposal or {},
                    workspace_name=workspace_name,
                    callback_url=callback_url,
                )
            except Exception as e:
                logger.warning("Failed to send approval to human hex %s: %s", ep.entity_id, e)

    return _ok({
        "status": "routed",
        "human_targets": len(human_endpoints),
        "decision_record_id": record.id,
    })


@router.post("/approval-requests/{record_id}/resolve")
async def resolve_approval(
    record_id: str,
    body: ApprovalResponse,
    org_ctx=Depends(get_current_org), db: AsyncSession = Depends(get_db),
):
    """Human resolves an approval request."""
    from datetime import datetime, timezone

    user, org = org_ctx
    result = await db.execute(
        select(DecisionRecord).where(DecisionRecord.id == record_id, not_deleted(DecisionRecord))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise _trust_http_error(404, 40491, "errors.trust.decision_record_not_found", "审批记录不存在")
    await _get_workspace(record.workspace_id, org, db)

    record.reviewer_id = _user_id(user)
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
            granted_by=_user_id(user),
            grant_type="always",
        )
        db.add(policy)
    elif body.decision == "deny":
        record.outcome = "rejected"
        record.review_comment = "Denied"

    await db.commit()
    return _ok({"decision": body.decision, "record_id": record.id})


@router.get("/{workspace_id}/decision-records")
async def list_decision_records(
    workspace_id: str,
    agent_id: str | None = None,
    decision_type: str | None = None,
    org_ctx=Depends(get_current_org_or_agent),
    db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _get_workspace(workspace_id, org, db)
    effective_agent_id = await _resolve_agent_scope(workspace_id, agent_id, db)
    query = select(DecisionRecord).where(
        DecisionRecord.workspace_id == workspace_id,
        not_deleted(DecisionRecord),
    )
    if effective_agent_id:
        query = query.where(DecisionRecord.agent_instance_id == effective_agent_id)
    if decision_type:
        query = query.where(DecisionRecord.decision_type == decision_type)
    result = await db.execute(query)
    items = [
        {
            "id": r.id,
            "workspace_id": r.workspace_id,
            "agent_instance_id": r.agent_instance_id,
            "decision_type": r.decision_type,
            "context_summary": r.context_summary,
            "proposal": r.proposal,
            "outcome": r.outcome,
            "reviewer_id": r.reviewer_id,
            "review_type": r.review_type,
            "review_comment": r.review_comment,
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.scalars().all()
    ]
    return _ok(items)


@router.get("/{workspace_id}/decision-records/{record_id}")
async def get_decision_record(
    workspace_id: str,
    record_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    _, org = org_ctx
    await _get_workspace(workspace_id, org, db)
    result = await db.execute(
        select(DecisionRecord).where(
            DecisionRecord.id == record_id,
            DecisionRecord.workspace_id == workspace_id,
            not_deleted(DecisionRecord),
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise _trust_http_error(404, 40491, "errors.trust.decision_record_not_found", "审批记录不存在")
    return _ok(
        {
            "id": record.id,
            "workspace_id": record.workspace_id,
            "agent_instance_id": record.agent_instance_id,
            "decision_type": record.decision_type,
            "context_summary": record.context_summary,
            "proposal": record.proposal,
            "outcome": record.outcome,
            "reviewer_id": record.reviewer_id,
            "review_type": record.review_type,
            "review_comment": record.review_comment,
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }
    )
