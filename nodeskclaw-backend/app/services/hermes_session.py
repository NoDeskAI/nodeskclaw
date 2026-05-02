"""Hermes session operations via RemoteFS.

Counterpart to ``openclaw_session.py`` — clears persistent Hermes sessions
so stale LLM context (accumulated tool-call history, outdated conversations)
does not pollute future interactions.

Hermes stores session state in two places:
  1. JSON files: ``~/.hermes/sessions/session_<key>.json``
  2. SQLite DB:  ``~/.hermes/state.db`` (tables: sessions, messages)

Both must be cleaned for a full reset.
"""

import json
import logging

from app.services.nfs_mount import RemoteFS

logger = logging.getLogger(__name__)

_SESSIONS_DIR = ".hermes/sessions"
_STATE_DB_REL = ".hermes/state.db"


async def clear_workspace_session(
    fs: RemoteFS,
    workspace_id: str,
) -> bool:
    """Clear Hermes session data for a specific workspace.

    Removes the workspace session JSON file and purges matching rows
    from state.db (sessions + messages tables).
    """
    session_key = f"workspace:{workspace_id}"
    session_filename = f"session_{session_key}.json"
    session_rel = f"{_SESSIONS_DIR}/{session_filename}"
    cleaned = False

    raw = await fs.read_text(session_rel)
    if raw is not None:
        await fs.write_text(session_rel, "{}")
        logger.info("Cleared Hermes session file: %s", session_filename)
        cleaned = True

    request_dumps = await _list_session_files(fs, workspace_id)
    for dump_file in request_dumps:
        try:
            await fs.write_text(f"{_SESSIONS_DIR}/{dump_file}", "{}")
            logger.info("Cleared Hermes request dump: %s", dump_file)
        except Exception:
            logger.debug("Failed to clear request dump %s", dump_file, exc_info=True)

    db_cleaned = await _clear_state_db(fs, session_key)
    if db_cleaned:
        cleaned = True

    return cleaned


async def clear_all_sessions(fs: RemoteFS) -> bool:
    """Clear ALL Hermes session data (nuclear option for full reset)."""
    cleaned = False

    listing = await _list_all_session_files(fs)
    for fname in listing:
        try:
            await fs.write_text(f"{_SESSIONS_DIR}/{fname}", "{}")
            cleaned = True
        except Exception:
            logger.debug("Failed to clear session file %s", fname, exc_info=True)

    try:
        script = (
            "import sqlite3, sys; "
            "conn = sqlite3.connect(sys.argv[1]); "
            "c = conn.cursor(); "
            "c.execute('DELETE FROM messages'); "
            "c.execute('DELETE FROM sessions'); "
            "conn.commit(); "
            "print(f'deleted {c.rowcount}')"
        )
        await fs.exec_command(["python3", "-c", script, f"/root/{_STATE_DB_REL}"])
        logger.info("Cleared all sessions from Hermes state.db")
        cleaned = True
    except Exception:
        logger.warning("Failed to clear all sessions from state.db", exc_info=True)

    return cleaned


async def _clear_state_db(fs: RemoteFS, session_key: str) -> bool:
    """Delete workspace session rows from Hermes state.db via sqlite3."""
    try:
        script = (
            "import sqlite3, sys; "
            "conn = sqlite3.connect(sys.argv[1]); "
            "c = conn.cursor(); "
            "sid = sys.argv[2]; "
            "c.execute('DELETE FROM messages WHERE session_id = ?', (sid,)); "
            "mc = c.rowcount; "
            "c.execute('DELETE FROM sessions WHERE id = ?', (sid,)); "
            "sc = c.rowcount; "
            "conn.commit(); "
            "print(f'{sc} sessions, {mc} messages deleted')"
        )
        result = await fs.exec_command([
            "python3", "-c", script,
            f"/root/{_STATE_DB_REL}", session_key,
        ])
        logger.info("Cleared Hermes state.db for %s: %s", session_key, result.strip())
        return True
    except Exception:
        logger.warning("Failed to clear state.db for session %s", session_key, exc_info=True)
        return False


async def _list_session_files(fs: RemoteFS, workspace_id: str) -> list[str]:
    """List session-related files for a specific workspace."""
    prefix = f"workspace:{workspace_id}"
    return await _find_files_with_prefix(fs, prefix)


async def _list_all_session_files(fs: RemoteFS) -> list[str]:
    """List all session files in the sessions directory."""
    try:
        result = await fs.exec_command([
            "find", f"/root/{_SESSIONS_DIR}", "-name", "*.json", "-type", "f",
            "-printf", "%f\\n",
        ])
        return [f for f in result.strip().splitlines() if f]
    except Exception:
        return []


async def _find_files_with_prefix(fs: RemoteFS, prefix: str) -> list[str]:
    """Find session/request_dump files matching a workspace prefix."""
    safe_prefix = prefix.replace(":", r"\:")
    try:
        result = await fs.exec_command([
            "find", f"/root/{_SESSIONS_DIR}",
            "-name", f"*{safe_prefix}*", "-type", "f",
            "-printf", "%f\\n",
        ])
        return [f for f in result.strip().splitlines() if f]
    except Exception:
        return []
