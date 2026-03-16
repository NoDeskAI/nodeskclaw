"""Blackboard BBS — post / reply / shared-file API endpoints."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.security import get_auth_actor
from app.schemas.workspace import (
    FileWriteRequest,
    MkdirRequest,
    PostCreate,
    PostUpdate,
    ReplyCreate,
)
from app.services import workspace_service, workspace_member_service as wm_service

logger = logging.getLogger(__name__)

router = APIRouter()


def _ok(data=None, message: str = "success"):
    from app.api.workspaces import _ok as ws_ok
    return ws_ok(data, message)


def _get_current_user_or_agent_dep():
    from app.core.security import get_current_user_or_agent
    return get_current_user_or_agent


def _broadcast(workspace_id: str, event_type: str, data: dict):
    from app.api.workspaces import broadcast_event
    broadcast_event(workspace_id, event_type, data)


def _caller_info() -> tuple[str, str, str]:
    """Return (author_type, author_id, author_name) from AuthActor context."""
    actor = get_auth_actor()
    if actor is None:
        return "human", "", ""
    return actor.actor_type, actor.actor_id, actor.actor_name


async def _notify_mentions(
    workspace_id: str,
    mentions: list,
    author_name: str,
    context: str,
    db: AsyncSession,
) -> None:
    from app.services import collaboration_service
    agent_ids = [m.id for m in mentions if m.type == "agent"]
    if agent_ids:
        msg = f"{author_name} mentioned you in {context}"
        await collaboration_service.send_system_message_to_agents(
            workspace_id, agent_ids, msg, db,
        )


# ── Posts ─────────────────────────────────────────────

@router.get("/{workspace_id}/blackboard/posts")
async def list_posts(
    workspace_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    posts, total = await workspace_service.list_posts(db, workspace_id, page, size)
    return _ok({"items": [p.model_dump(mode="json") for p in posts], "total": total})


@router.post("/{workspace_id}/blackboard/posts")
async def create_post(
    workspace_id: str,
    data: PostCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    author_type, author_id, author_name = _caller_info()
    post_info, mentions = await workspace_service.create_post(
        db, workspace_id, author_type, author_id, author_name, data,
    )
    _broadcast(workspace_id, "post:created", post_info.model_dump(mode="json"))
    if mentions:
        await _notify_mentions(
            workspace_id, mentions, author_name,
            f"a post: {data.title}", db,
        )
    return _ok(post_info.model_dump(mode="json"))


@router.get("/{workspace_id}/blackboard/posts/{post_id}")
async def get_post(
    workspace_id: str,
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    post = await workspace_service.get_post(db, workspace_id, post_id)
    if post is None:
        return _ok(None, "not found")
    return _ok(post.model_dump(mode="json"))


@router.put("/{workspace_id}/blackboard/posts/{post_id}")
async def update_post(
    workspace_id: str,
    post_id: str,
    data: PostUpdate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    _, author_id, _ = _caller_info()
    post = await workspace_service.update_post(db, workspace_id, post_id, author_id, data)
    if post is None:
        return _ok(None, "not found or not author")
    _broadcast(workspace_id, "post:updated", post.model_dump(mode="json"))
    return _ok(post.model_dump(mode="json"))


@router.delete("/{workspace_id}/blackboard/posts/{post_id}")
async def delete_post(
    workspace_id: str,
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    ok = await workspace_service.delete_post(db, workspace_id, post_id)
    if ok:
        _broadcast(workspace_id, "post:deleted", {"post_id": post_id})
    return _ok({"deleted": ok})


@router.post("/{workspace_id}/blackboard/posts/{post_id}/pin")
async def pin_post(
    workspace_id: str,
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    post = await workspace_service.pin_post(db, workspace_id, post_id, True)
    if post is None:
        return _ok(None, "not found")
    _broadcast(workspace_id, "post:pinned", {"post_id": post_id, "is_pinned": True})
    return _ok(post.model_dump(mode="json"))


@router.delete("/{workspace_id}/blackboard/posts/{post_id}/pin")
async def unpin_post(
    workspace_id: str,
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    post = await workspace_service.pin_post(db, workspace_id, post_id, False)
    if post is None:
        return _ok(None, "not found")
    _broadcast(workspace_id, "post:pinned", {"post_id": post_id, "is_pinned": False})
    return _ok(post.model_dump(mode="json"))


# ── Replies ───────────────────────────────────────────

@router.post("/{workspace_id}/blackboard/posts/{post_id}/replies")
async def create_reply(
    workspace_id: str,
    post_id: str,
    data: ReplyCreate,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    author_type, author_id, author_name = _caller_info()
    result = await workspace_service.create_reply(
        db, post_id, author_type, author_id, author_name, data,
    )
    if result is None:
        return _ok(None, "post not found")
    reply_info, post, mentions = result
    _broadcast(workspace_id, "reply:created", {
        "post_id": post_id,
        "reply": reply_info.model_dump(mode="json"),
    })
    if mentions:
        await _notify_mentions(
            workspace_id, mentions, author_name,
            f"a reply on: {post.title}", db,
        )
    return _ok(reply_info.model_dump(mode="json"))


# ── Read tracking ─────────────────────────────────────

@router.post("/{workspace_id}/blackboard/posts/{post_id}/read")
async def mark_read(
    workspace_id: str,
    post_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    reader_type, reader_id, _ = _caller_info()
    await workspace_service.mark_post_read(db, post_id, reader_type, reader_id)
    return _ok()


@router.get("/{workspace_id}/blackboard/unread-count")
async def unread_count(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    reader_type, reader_id, _ = _caller_info()
    count = await workspace_service.get_unread_count(
        db, workspace_id, reader_type, reader_id,
    )
    return _ok({"count": count})


# ── Shared Files ──────────────────────────────────────

@router.get("/{workspace_id}/blackboard/files")
async def list_files(
    workspace_id: str,
    parent_path: str = Query("/"),
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    files = await workspace_service.list_shared_files(db, workspace_id, parent_path)
    return _ok([f.model_dump(mode="json") for f in files])


@router.post("/{workspace_id}/blackboard/files/mkdir")
async def mkdir(
    workspace_id: str,
    data: MkdirRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    utype, uid, uname = _caller_info()
    info = await workspace_service.create_shared_directory(
        db, workspace_id, utype, uid, uname, data,
    )
    _broadcast(workspace_id, "file:created", info.model_dump(mode="json"))
    return _ok(info.model_dump(mode="json"))


@router.post("/{workspace_id}/blackboard/files/upload")
async def upload_file(
    workspace_id: str,
    data: FileWriteRequest,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    utype, uid, uname = _caller_info()
    info = await workspace_service.upload_shared_file(
        db, workspace_id, utype, uid, uname, data,
    )
    _broadcast(workspace_id, "file:uploaded", info.model_dump(mode="json"))
    return _ok(info.model_dump(mode="json"))


@router.get("/{workspace_id}/blackboard/files/{file_id}/url")
async def get_file_url(
    workspace_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    url = await workspace_service.get_shared_file_url(db, workspace_id, file_id)
    if url is None:
        return _ok(None, "not found")
    return _ok({"url": url})


@router.get("/{workspace_id}/blackboard/files/{file_id}/content")
async def read_file_content(
    workspace_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_member(workspace_id, user, db)
    result = await workspace_service.read_shared_file(db, workspace_id, file_id)
    if result is None:
        return _ok(None, "not found")
    b64, ct = result
    return _ok({"content": b64, "content_type": ct})


@router.delete("/{workspace_id}/blackboard/files/{file_id}")
async def delete_file(
    workspace_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    user=Depends(_get_current_user_or_agent_dep()),
):
    await wm_service.check_workspace_access(workspace_id, user, "edit_blackboard", db)
    ok = await workspace_service.delete_shared_file(db, workspace_id, file_id)
    if ok:
        _broadcast(workspace_id, "file:deleted", {"file_id": file_id})
    return _ok({"deleted": ok})
