"""OpenClaw session & config file operations via kubectl exec.

Provides utilities for manipulating OpenClaw's file-system state on the
running Pod.  These helpers accept a ``PodFS`` instance — all I/O is
a single exec call per operation.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from app.services.nfs_mount import PodFS

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_REL = ".openclaw/openclaw.json"
SKILLS_EXTRA_DIR = "/root/.openclaw/skills"

_SESSIONS_REL = ".openclaw/agents/main/sessions/sessions.json"


async def _write_sessions_json(fs: PodFS, path: str, store: dict) -> None:
    payload = json.dumps(store, indent=2, ensure_ascii=False)
    json.loads(payload)
    await fs.write_text(path, payload + "\n")


async def invalidate_skill_snapshots(fs: PodFS) -> None:
    """Clear cached skillsSnapshot from all OpenClaw sessions."""
    raw = await fs.read_text(_SESSIONS_REL)
    if raw is None:
        return
    try:
        store = json.loads(raw)
        changed = False
        for key, entry in store.items():
            if isinstance(entry, dict) and "skillsSnapshot" in entry:
                del entry["skillsSnapshot"]
                changed = True
        if changed:
            await _write_sessions_json(fs, _SESSIONS_REL, store)
            logger.info("Cleared stale skillsSnapshot from %d session(s)", len(store))
    except Exception as e:
        logger.warning("Failed to invalidate skill snapshots: %s", e)


async def inject_evolution_notification(
    fs: PodFS,
    gene_name: str,
    action: str,
) -> None:
    """Inject evolution notification messages into all active session JSONL files."""
    raw = await fs.read_text(_SESSIONS_REL)
    if raw is None:
        return

    if action == "installed":
        user_text = (
            f"[System] 基因系统通知: 你刚刚获取了新的基因「{gene_name}」，"
            f"完成了一轮进化。你的技能列表已更新，请以 system prompt 中 <available_skills> 为准。"
        )
        assistant_text = f"收到，我已获取新基因「{gene_name}」并完成进化。我的技能列表已更新。"
    else:
        user_text = (
            f"[System] 基因系统通知: 基因「{gene_name}」已遗忘。"
            f"你的技能列表已更新，请以 system prompt 中 <available_skills> 为准。"
        )
        assistant_text = f"收到，基因「{gene_name}」已遗忘。我的技能列表已更新。"

    try:
        store = json.loads(raw)
        store_changed = False

        for key, entry in store.items():
            if not isinstance(entry, dict):
                continue
            session_file = entry.get("sessionFile")
            if not session_file:
                continue

            # sessionFile = container absolute path e.g. /root/.openclaw/.../xxx.jsonl
            # Strip /root/ prefix for PodFS (which prepends /root/)
            if session_file.startswith("/root/"):
                rel_path = session_file[len("/root/"):]
            else:
                rel_path = session_file.lstrip("/")

            last_line = await fs.read_last_line(rel_path)
            if not last_line or not last_line.strip():
                continue

            try:
                last_entry = json.loads(last_line.strip())
                parent_id = last_entry.get("id", uuid.uuid4().hex[:8])

                now = datetime.now(timezone.utc)
                ts_iso = now.isoformat().replace("+00:00", "Z")
                ts_ms = int(now.timestamp() * 1000)

                user_id = uuid.uuid4().hex[:8]
                assistant_id = uuid.uuid4().hex[:8]

                user_msg = json.dumps({
                    "type": "message",
                    "id": user_id,
                    "parentId": parent_id,
                    "timestamp": ts_iso,
                    "message": {
                        "role": "user",
                        "content": [{"type": "text", "text": user_text}],
                        "timestamp": ts_ms,
                    },
                }, ensure_ascii=False)

                model_provider = entry.get("modelProvider", "system")
                model_name = entry.get("model", "system")
                assistant_msg = json.dumps({
                    "type": "message",
                    "id": assistant_id,
                    "parentId": user_id,
                    "timestamp": ts_iso,
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": assistant_text}],
                        "api": "openai-completions",
                        "provider": model_provider,
                        "model": model_name,
                        "usage": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                            "totalTokens": 0,
                            "cost": {
                                "input": 0, "output": 0,
                                "cacheRead": 0, "cacheWrite": 0,
                                "total": 0,
                            },
                        },
                        "stopReason": "stop",
                        "timestamp": ts_ms,
                    },
                }, ensure_ascii=False)

                await fs.append_text(rel_path, f"\n{user_msg}\n{assistant_msg}")
                logger.info("Injected evolution notification into session %s", key)
            except Exception as e:
                logger.warning("Failed to inject notification into %s: %s", session_file, e)

            entry["systemSent"] = False
            store_changed = True

        if store_changed:
            await _write_sessions_json(fs, _SESSIONS_REL, store)
            logger.info("Reset systemSent for %d session(s)", sum(
                1 for v in store.values() if isinstance(v, dict) and v.get("systemSent") is False
            ))
    except Exception as e:
        logger.warning("Failed to inject evolution notifications: %s", e)


async def ensure_skills_discovery(fs: PodFS) -> None:
    """Ensure openclaw.json has skills.load.extraDirs pointing to custom skills dir."""
    raw = await fs.read_text(OPENCLAW_CONFIG_REL)
    existing: dict = {}
    if raw is not None:
        try:
            existing = json.loads(raw)
        except json.JSONDecodeError:
            existing = {}

    skills = existing.setdefault("skills", {})
    load = skills.setdefault("load", {})
    extra_dirs = load.setdefault("extraDirs", [])
    if SKILLS_EXTRA_DIR not in extra_dirs:
        extra_dirs.append(SKILLS_EXTRA_DIR)
        await fs.write_text(
            OPENCLAW_CONFIG_REL,
            json.dumps(existing, indent=2, ensure_ascii=False),
        )
