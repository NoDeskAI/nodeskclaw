"""Invitation service — create, validate, accept invitations."""

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.base import not_deleted
from app.models.invitation import Invitation, InvitationStatus
from app.models.org_membership import OrgMembership
from app.models.organization import Organization
from app.models.user import User
from app.services.member_hooks import get_member_hook, get_role_provider

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

INVITE_EXPIRE_DAYS = 7


def _validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


def _build_invite_url(token: str) -> str:
    base = settings.PORTAL_BASE_URL.rstrip("/") if settings.PORTAL_BASE_URL else ""
    return f"{base}/invite/{token}"


async def create_invitations(
    org_id: str,
    emails: list[str],
    role: str,
    invited_by: str,
    db: AsyncSession,
) -> list[dict]:
    """Create invitation records for each email. Returns per-email results."""
    provider = get_role_provider()
    valid_role_ids = {r["id"] for r in provider.get_roles(org_id)}
    if role not in valid_role_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40030,
                "message_key": "errors.invite.invalid_role",
                "message": f"Invalid role: {role}",
            },
        )

    invalid_emails = [e for e in emails if not _validate_email(e)]
    if invalid_emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40031,
                "message_key": "errors.invite.invalid_email",
                "message": f"Invalid emails: {', '.join(invalid_emails)}",
            },
        )

    hook = get_member_hook()
    await hook.before_invite(org_id, emails, role)

    results: list[dict] = []
    for email in emails:
        email_lower = email.strip().lower()

        existing_user = (await db.execute(
            select(User).where(User.email == email_lower, not_deleted(User))
        )).scalar_one_or_none()

        if existing_user:
            existing_membership = (await db.execute(
                select(OrgMembership).where(
                    OrgMembership.user_id == existing_user.id,
                    OrgMembership.org_id == org_id,
                    not_deleted(OrgMembership),
                )
            )).scalar_one_or_none()
            if existing_membership:
                results.append({"email": email_lower, "status": "already_member"})
                continue

        existing_invite = (await db.execute(
            select(Invitation).where(
                Invitation.org_id == org_id,
                Invitation.email == email_lower,
                Invitation.status == InvitationStatus.pending,
                not_deleted(Invitation),
            )
        )).scalar_one_or_none()
        if existing_invite:
            results.append({
                "email": email_lower,
                "status": "already_invited",
                "invite_url": _build_invite_url(existing_invite.token),
            })
            continue

        token = secrets.token_urlsafe(32)
        invitation = Invitation(
            org_id=org_id,
            email=email_lower,
            role=role,
            token=token,
            status=InvitationStatus.pending,
            invited_by=invited_by,
            expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_EXPIRE_DAYS),
        )
        db.add(invitation)

        invite_url = _build_invite_url(token)

        email_sent = False
        try:
            from app.services.email_service import send_invitation_email
            await send_invitation_email(
                to_email=email_lower,
                org_name="",
                inviter_name="",
                invite_url=invite_url,
                role=role,
                db=db,
                org_id=org_id,
                inviter_id=invited_by,
            )
            email_sent = True
        except Exception:
            logger.debug("SMTP not configured or send failed, invite link still returned")

        results.append({
            "email": email_lower,
            "status": "invited",
            "invite_url": invite_url,
            "email_sent": email_sent,
        })

    await db.commit()
    return results


async def list_pending_invitations(
    org_id: str,
    db: AsyncSession,
) -> list[dict]:
    """List all pending invitations for an organization."""
    result = await db.execute(
        select(Invitation).where(
            Invitation.org_id == org_id,
            Invitation.status == InvitationStatus.pending,
            not_deleted(Invitation),
        ).order_by(Invitation.created_at.desc())
    )
    invitations = result.scalars().all()

    now = datetime.now(timezone.utc)
    items = []
    for inv in invitations:
        is_expired = inv.expires_at.replace(tzinfo=timezone.utc) < now if inv.expires_at.tzinfo is None else inv.expires_at < now
        items.append({
            "id": inv.id,
            "email": inv.email,
            "role": inv.role,
            "status": "expired" if is_expired else inv.status,
            "invited_by": inv.invited_by,
            "created_at": inv.created_at.isoformat(),
            "expires_at": inv.expires_at.isoformat(),
            "invite_url": _build_invite_url(inv.token),
        })
    return items


async def cancel_invitation(
    org_id: str,
    invitation_id: str,
    db: AsyncSession,
) -> None:
    """Soft-delete a pending invitation."""
    result = await db.execute(
        select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.org_id == org_id,
            not_deleted(Invitation),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": 40410,
                "message_key": "errors.invite.not_found",
                "message": "Invitation not found",
            },
        )
    invitation.soft_delete()
    await db.commit()


async def validate_invite_token(
    token: str,
    db: AsyncSession,
) -> dict:
    """Validate an invitation token and return its info."""
    result = await db.execute(
        select(Invitation).where(
            Invitation.token == token,
            not_deleted(Invitation),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": 40411,
                "message_key": "errors.invite.invalid_token",
                "message": "Invalid or expired invitation link",
            },
        )

    now = datetime.now(timezone.utc)
    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    is_expired = expires < now or invitation.status != InvitationStatus.pending

    org = (await db.execute(
        select(Organization).where(Organization.id == invitation.org_id)
    )).scalar_one_or_none()

    existing_user = (await db.execute(
        select(User).where(User.email == invitation.email, not_deleted(User))
    )).scalar_one_or_none()

    return {
        "org_name": org.name if org else "",
        "org_id": invitation.org_id,
        "email": invitation.email,
        "role": invitation.role,
        "expired": is_expired,
        "already_registered": existing_user is not None,
    }


async def accept_invitation(
    token: str,
    name: str,
    password: str,
    db: AsyncSession,
) -> dict:
    """Accept an invitation: create user if needed, add to org, return JWT."""
    from app.core.security import create_access_token, create_refresh_token
    from app.services.auth_service import _hash_password

    result = await db.execute(
        select(Invitation).where(
            Invitation.token == token,
            Invitation.status == InvitationStatus.pending,
            not_deleted(Invitation),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40032,
                "message_key": "errors.invite.invalid_token",
                "message": "Invalid or already accepted invitation",
            },
        )

    now = datetime.now(timezone.utc)
    expires = invitation.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        invitation.status = InvitationStatus.expired
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": 40033,
                "message_key": "errors.invite.expired",
                "message": "Invitation has expired",
            },
        )

    existing_user = (await db.execute(
        select(User).where(User.email == invitation.email, not_deleted(User))
    )).scalar_one_or_none()

    if existing_user:
        user = existing_user
    else:
        user = User(
            name=name,
            email=invitation.email,
            password_hash=_hash_password(password),
            current_org_id=invitation.org_id,
        )
        db.add(user)
        await db.flush()

    existing_membership = (await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id,
            OrgMembership.org_id == invitation.org_id,
            not_deleted(OrgMembership),
        )
    )).scalar_one_or_none()

    if existing_membership is None:
        db.add(OrgMembership(
            user_id=user.id,
            org_id=invitation.org_id,
            role=invitation.role,
        ))

    if not user.current_org_id:
        user.current_org_id = invitation.org_id

    invitation.status = InvitationStatus.accepted
    invitation.accepted_by = user.id
    await db.commit()

    hook = get_member_hook()
    try:
        await hook.on_member_joined(invitation.org_id, user.id, invitation.role)
    except Exception:
        logger.exception("on_member_joined hook failed")

    access_token = create_access_token(user_id=user.id)
    refresh_token = create_refresh_token(user_id=user.id)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_id": user.id,
    }
