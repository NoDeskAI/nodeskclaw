"""Invitation API routes — org-scoped (authenticated) + public (unauthenticated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel as PydanticModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_admin, require_org_member
from app.services.member_hooks import get_role_provider


# ── Schemas ───────────────────────────────────────────────


class InviteRequest(PydanticModel):
    emails: list[str]
    role: str = "member"


class AcceptInviteRequest(PydanticModel):
    token: str
    name: str
    password: str


# ── Org-scoped routes (require authentication) ───────────

invite_router = APIRouter()


@invite_router.post("/{org_id}/members/invite")
async def create_invitations(
    org_id: str,
    body: InviteRequest,
    user_org=Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.invitation_service import create_invitations as svc_create

    user, _org = user_org
    results = await svc_create(
        org_id=org_id,
        emails=body.emails,
        role=body.role,
        invited_by=user.id,
        db=db,
    )
    return {"code": 0, "data": results}


@invite_router.get("/{org_id}/invitations")
async def list_invitations(
    org_id: str,
    _user_org=Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.invitation_service import list_pending_invitations

    items = await list_pending_invitations(org_id, db)
    return {"code": 0, "data": items}


@invite_router.delete("/{org_id}/invitations/{invitation_id}")
async def cancel_invitation(
    org_id: str,
    invitation_id: str,
    _user_org=Depends(require_org_admin),
    db: AsyncSession = Depends(get_db),
):
    from app.services.invitation_service import cancel_invitation as svc_cancel

    await svc_cancel(org_id, invitation_id, db)
    return {"code": 0, "message": "ok"}


@invite_router.get("/{org_id}/roles")
async def get_roles(
    org_id: str,
    _user_org=Depends(require_org_member),
):
    provider = get_role_provider()
    roles = provider.get_roles(org_id)
    return {"code": 0, "data": roles}


# ── Public routes (no authentication required) ───────────

invite_public_router = APIRouter()


@invite_public_router.get("/{token}")
async def verify_invite_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    from app.services.invitation_service import validate_invite_token

    info = await validate_invite_token(token, db)
    return {"code": 0, "data": info}


@invite_public_router.post("/accept")
async def accept_invite(
    body: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.services.invitation_service import accept_invitation

    result = await accept_invitation(
        token=body.token,
        name=body.name,
        password=body.password,
        db=db,
    )
    return {"code": 0, "data": result}
