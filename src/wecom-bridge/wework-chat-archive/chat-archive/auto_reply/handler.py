from __future__ import annotations

import json
import logging
import time

from . import service
from .agent.core import run_agent
from .agent.skill_registry import registry
from .image_util import (
    should_skip_by_metadata, describe_image,
    mark_image_pending, mark_image_done, wait_for_pending_image,
)
from .models import AutoReplyLog
from . import wework_api
from database import SessionLocal, Message, get_setting, set_setting

logger = logging.getLogger(__name__)

NOTIFY_NEW_MSG = 11010
NOTIFY_MEMBER_JOIN = 1002
TEXT_CONTENT_TYPES = {0, 2}
IMAGE_CONTENT_TYPES = {3, 14}  # 普通图片 + HD图片（不含贴纸 29）

_bot_wxid: str | None = None


def _get_bot_wxid() -> str:
    """Get the bot's wxid, auto-detecting from sent messages if needed."""
    global _bot_wxid
    if _bot_wxid:
        return _bot_wxid

    wxid = get_setting("bot_wxid", "")
    if wxid:
        _bot_wxid = wxid
        return wxid

    db = SessionLocal()
    try:
        msg = db.query(Message).filter(Message.send_flag == 1).order_by(Message.id.desc()).first()
        if msg and msg.sender:
            _bot_wxid = msg.sender
            set_setting("bot_wxid", msg.sender)
            logger.info("[auto_reply] bot wxid auto-detected: %s", msg.sender)
            return msg.sender
    finally:
        db.close()

    return ""


def _is_at_me(at_list_raw) -> bool:
    bot_wxid = _get_bot_wxid()
    if not bot_wxid:
        return False
    at_list = at_list_raw
    if isinstance(at_list, str):
        try:
            at_list = json.loads(at_list)
        except (json.JSONDecodeError, TypeError):
            return False
    if not isinstance(at_list, list):
        return False
    return bot_wxid in at_list


import re

_AT_PATTERN = re.compile(r'@\S+\s*')


def _strip_at_bot(content: str) -> str:
    """Remove the first @mention from the message content."""
    cleaned = _AT_PATTERN.sub('', content, count=1).strip()
    return cleaned


async def process(payload: dict) -> bool:
    """Process a webhook payload for auto-reply.

    Returns True if handled (caller should skip forwarding).
    """
    notify_type = payload.get("notify_type")

    if notify_type == NOTIFY_MEMBER_JOIN:
        return await _handle_member_join(payload)
    elif notify_type == NOTIFY_NEW_MSG:
        return await _handle_new_message(payload)
    return False


async def _handle_member_join(payload: dict) -> bool:
    data = payload.get("data", {})
    room_id = str(data.get("room_id", ""))
    members = str(data.get("members", ""))

    if not room_id or not members:
        return False

    config = service.get_config(room_id)
    if not config or not config.welcome_enabled:
        return False

    member_list = [m.strip() for m in members.split(",") if m.strip()]
    welcome_msg = config.welcome_message or "欢迎 {name} 加入群聊！"
    content = welcome_msg.replace("{name}", "{$@}")
    conversation_id = f"R:{room_id}"

    try:
        await wework_api.send_room_at(conversation_id, content, member_list)
        logger.info("[auto_reply] welcome sent [%s] @%s", room_id, member_list)
        _log_reply(room_id, "", "", welcome_msg, content, "welcome", "", 0)
        return True
    except Exception as e:
        logger.error("[auto_reply] welcome failed: %s", e, exc_info=True)
        return False


async def _handle_new_message(payload: dict) -> bool:
    data = payload.get("data", {})
    sender = str(data.get("sender", ""))
    room_id = str(data.get("roomid", "0"))
    content = str(data.get("content", ""))
    content_type = data.get("content_type", 0)
    referid = str(data.get("referid", "0"))
    sender_name = data.get("sender_name", "")
    send_flag = data.get("send_flag", 0)
    at_list = data.get("at_list", [])

    is_dm = (room_id == "0")

    if is_dm:
        global_config = service.get_config("")
        if not global_config or not getattr(global_config, "dm_enabled", False):
            return False

    is_image = content_type in IMAGE_CONTENT_TYPES
    if content_type not in TEXT_CONTENT_TYPES and not is_image:
        return False
    # Image replies (referid != "0") are allowed — users often reply with screenshots
    if referid != "0" and not is_image:
        return False
    if send_flag == 1:
        return False
    if not is_image and not content.strip():
        return False

    if is_dm:
        config = service.get_config("")
    else:
        config = service.get_config(room_id)
    if not config or not config.reply_enabled:
        return False

    conversation_id = f"DM:{sender}" if is_dm else f"R:{room_id}"

    # ── Image processing path (before require_at / cooldown) ──────────
    if is_image:
        if should_skip_by_metadata(data):
            return False

        mark_image_pending(room_id, sender)
        try:
            description = await describe_image(data)
        finally:
            mark_image_done(room_id, sender)

        if not description:
            return False

        image_text = f"[截图] {description}"
        tagged_image = f"[{sender_name}] {image_text}" if sender_name else image_text

        if is_dm:
            # DM: fall through to agent reply below
            content = f"[用户发送了截图] {description}"
        elif config and config.require_at:
            # Group + require_at: silently add to context, don't reply
            from .agent.context import context_store
            context_store.add(conversation_id, "user", tagged_image)
            logger.info("[auto_reply] image description stored in context [%s]", room_id)
            return True
        else:
            # Group + no require_at: "analyzing" hint then agent reply
            # Hint is sent AFTER SKIP check — no false promises
            try:
                await wework_api.send_room_at(
                    conversation_id, "{$@} 正在分析截图，请稍候...", [sender],
                )
            except Exception:
                pass
            content = f"[用户发送了截图] {description}"
        # fall through to keyword / AI reply logic
    # ── End image path ──────────────────────────────────────────────────

    clean_content = content.strip() if is_dm else _strip_at_bot(content)
    tagged = f"[{sender_name}] {clean_content}" if sender_name else clean_content

    should_reply = True
    if not is_dm and not is_image and config.require_at and not _is_at_me(at_list):
        from .agent.context import context_store
        if tagged.strip():
            context_store.add(conversation_id, "user", tagged)
        should_reply = False

    if not should_reply:
        return False

    # @bot text: wait for any pending image from the same sender before proceeding
    if not is_dm and not is_image:
        waited = await wait_for_pending_image(room_id, sender)
        if waited:
            logger.info("[auto_reply] waited for pending image [%s/%s]", room_id, sender)

    cooldown_key = sender if is_dm else room_id
    if not service.check_cooldown(cooldown_key, sender, config.cooldown_seconds):
        logger.debug("[auto_reply] cooldown active %s/%s", cooldown_key, sender)
        return False

    start_time = time.time()
    reply_text = ""
    reply_type = ""
    skill_used = ""

    try:
        if config.reply_mode in ("keyword", "ai"):
            rules = service.get_rules("" if is_dm else room_id)
            matched = service.match_keyword(content, rules)
            if matched:
                reply_text = matched.reply_content
                reply_type = "keyword"

        if not reply_text and config.reply_mode == "ai":
            enabled_skills = service.get_enabled_skill_names("" if is_dm else room_id)
            skills = registry.get_enabled(enabled_skills)
            system_prompt = config.ai_system_prompt or ""
            model = config.ai_model or ""

            reply_text, skill_used = await run_agent(
                conversation_id, clean_content, system_prompt, skills, model,
                sender_name=sender_name if not is_dm else "",
            )
            reply_type = "ai"

        if not reply_text:
            return False

        if is_dm:
            await wework_api.send_text(f"S:{sender}", reply_text)
        else:
            await wework_api.send_room_at(
                conversation_id, f"{{$@}} {reply_text}", [sender],
            )

        latency = int((time.time() - start_time) * 1000)
        log_room = "DM" if is_dm else room_id
        logger.info(
            "[auto_reply] replied [%s] %s -> %s (%dms)",
            log_room, content[:50], reply_text[:50], latency,
        )
        _log_reply(
            log_room, sender, sender_name,
            content, reply_text,
            reply_type, skill_used, latency,
        )
        return True

    except Exception as e:
        logger.error("[auto_reply] message handling failed: %s", e, exc_info=True)
        return False


def _log_reply(
    room_id: str,
    sender: str,
    sender_name: str,
    trigger: str,
    reply: str,
    reply_type: str,
    skill_used: str,
    latency_ms: int,
):
    try:
        db = SessionLocal()
        db.add(AutoReplyLog(
            room_id=room_id,
            sender=sender,
            sender_name=sender_name,
            trigger_message=trigger,
            reply_content=reply,
            reply_type=reply_type,
            skill_used=skill_used,
            latency_ms=latency_ms,
        ))
        db.commit()
        db.close()
    except Exception as e:
        logger.error("[auto_reply] log write failed: %s", e)
