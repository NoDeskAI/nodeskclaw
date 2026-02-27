"""OpenClaw session & config file operations on NFS mounts.

Provides utilities for manipulating OpenClaw's file-system state after
an NFS mount is established (by ``nfs_mount.py``).  These helpers are
intentionally kept free of DB / ORM dependencies so any service can use
them by simply passing a ``mount_path``.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_REL = Path(".openclaw") / "openclaw.json"
SKILLS_DIR_REL = Path(".openclaw") / "skills"
SKILLS_EXTRA_DIR = "/root/.openclaw/skills"

_SESSIONS_REL = Path(".openclaw") / "agents" / "main" / "sessions" / "sessions.json"


def write_sessions_json(sessions_path: Path, store: dict) -> None:
    """Write sessions.json preserving Node.js JSON.stringify compatibility.

    OpenClaw (Node.js) reads this file; we must produce output that round-trips
    cleanly through both Python json and Node JSON.parse/stringify.
    """
    payload = json.dumps(store, indent=2, ensure_ascii=False)
    json.loads(payload)  # validate round-trip before writing
    sessions_path.write_text(payload + "\n", encoding="utf-8")


def invalidate_skill_snapshots(mount_path: Path) -> None:
    """Clear cached skillsSnapshot from all OpenClaw sessions.

    OpenClaw caches a skillsSnapshot per session in sessions.json. On NFS mounts
    chokidar file watching doesn't work (no inotify support), so the snapshot
    version counter never increments and stale sessions never refresh. We clear
    the snapshot field so the next chat message rebuilds it with the latest skills.
    """
    sessions_path = mount_path / _SESSIONS_REL
    if not sessions_path.exists():
        return
    try:
        raw = sessions_path.read_text(encoding="utf-8")
        store = json.loads(raw)
        changed = False
        for key, entry in store.items():
            if isinstance(entry, dict) and "skillsSnapshot" in entry:
                del entry["skillsSnapshot"]
                changed = True
        if changed:
            write_sessions_json(sessions_path, store)
            logger.info("Cleared stale skillsSnapshot from %d session(s)", len(store))
    except Exception as e:
        logger.warning("Failed to invalidate skill snapshots: %s", e)


def inject_evolution_notification(
    mount_path: Path,
    gene_name: str,
    action: str,
) -> None:
    """Inject evolution notification messages into all active session JSONL files.

    After a gene install/uninstall, old conversation history may contain stale
    skill listings from the agent. The LLM tends to repeat its previous answer
    instead of re-checking the system prompt. By appending a user+assistant
    message pair about the evolution, we override the stale context and ensure
    the agent acknowledges the skill change.

    Also resets ``systemSent`` to ``false`` so the next turn forces a full
    system prompt rebuild with the updated skill list.
    """
    sessions_path = mount_path / _SESSIONS_REL
    if not sessions_path.exists():
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
        store = json.loads(sessions_path.read_text(encoding="utf-8"))
        store_changed = False

        for key, entry in store.items():
            if not isinstance(entry, dict):
                continue
            session_file = entry.get("sessionFile")
            if not session_file:
                continue

            # sessionFile stores the container-internal absolute path
            # (e.g. /root/.openclaw/agents/main/sessions/xxx.jsonl).
            # Resolve to local NFS mount path via the same parent dir as sessions.json.
            local_session_path = sessions_path.parent / Path(session_file).name
            if not local_session_path.exists():
                continue

            try:
                content = local_session_path.read_text(encoding="utf-8").rstrip("\n")
                if not content:
                    continue

                last_line = content.rsplit("\n", 1)[-1]
                last_entry = json.loads(last_line)
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

                # pi-coding-agent reads usage.totalTokens from the last
                # assistant message; omitting it causes a TypeError crash.
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

                with local_session_path.open("a", encoding="utf-8") as f:
                    f.write(f"\n{user_msg}\n{assistant_msg}")

                logger.info("Injected evolution notification into session %s", key)
            except Exception as e:
                logger.warning("Failed to inject notification into %s: %s", session_file, e)

            entry["systemSent"] = False
            store_changed = True

        if store_changed:
            write_sessions_json(sessions_path, store)
            logger.info("Reset systemSent for %d session(s)", sum(
                1 for v in store.values() if isinstance(v, dict) and v.get("systemSent") is False
            ))
    except Exception as e:
        logger.warning("Failed to inject evolution notifications: %s", e)


def ensure_skills_discovery(mount_path: Path) -> None:
    """Ensure openclaw.json has skills.load.extraDirs pointing to custom skills dir.

    OpenClaw only auto-discovers native skills; custom skills in .openclaw/skills/
    require an explicit extraDirs entry. Uses absolute path to avoid OpenClaw resolving
    relative to its workspace directory.
    """
    config_path = mount_path / OPENCLAW_CONFIG_REL
    existing: dict = {}
    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}

    skills = existing.setdefault("skills", {})
    load = skills.setdefault("load", {})
    extra_dirs = load.setdefault("extraDirs", [])
    if SKILLS_EXTRA_DIR not in extra_dirs:
        extra_dirs.append(SKILLS_EXTRA_DIR)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
