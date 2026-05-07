"""Hermes plugin that exposes NoDeskClaw workspace tools."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TOOLSET = "nodeskclaw"
_DEFAULT_API_URL = "http://localhost:4510/api/v1"
_WORKSPACE_SESSION_PREFIX = "workspace:"
_thread_state = threading.local()


@dataclass(slots=True)
class ToolConfig:
    api_url: str
    token: str
    workspace_id: str
    instance_id: str
    workspace_root: Path


def register(ctx) -> None:
    """Register NoDeskClaw tools into Hermes."""
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    for name, schema, handler in (
        ("nodeskclaw_blackboard", _BLACKBOARD_SCHEMA, blackboard_tool),
        ("nodeskclaw_topology", _TOPOLOGY_SCHEMA, topology_tool),
        ("nodeskclaw_collaboration", _COLLABORATION_SCHEMA, collaboration_tool),
        ("nodeskclaw_shared_files", _SHARED_FILES_SCHEMA, shared_files_tool),
        ("nodeskclaw_performance", _PERFORMANCE_SCHEMA, performance_tool),
        ("nodeskclaw_proposals", _PROPOSALS_SCHEMA, proposals_tool),
        ("nodeskclaw_gene_discovery", _GENE_DISCOVERY_SCHEMA, gene_discovery_tool),
        ("nodeskclaw_file_download", _FILE_DOWNLOAD_SCHEMA, file_download_tool),
        ("nodeskclaw_chat_history", _CHAT_HISTORY_SCHEMA, chat_history_tool),
    ):
        ctx.register_tool(
            name=name,
            toolset=_TOOLSET,
            schema=schema,
            handler=handler,
            description=schema.get("description", ""),
        )


def blackboard_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())

    action = str(args.get("action") or "")
    ws = cfg.workspace_id
    if action == "get_blackboard":
        return _json_result(_bb_api_fetch(cfg, f"/workspaces/{ws}/blackboard"))
    if action == "update_blackboard":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard",
                method="PUT",
                body={"content": args.get("content")},
            )
        )
    if action == "patch_section":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/sections",
                method="PATCH",
                body={"section": args.get("section"), "content": args.get("content")},
            )
        )
    if action == "list_tasks":
        suffix = ""
        if args.get("filter_status"):
            suffix = "?" + urllib.parse.urlencode({"status": str(args["filter_status"])})
        return _json_result(_bb_api_fetch(cfg, f"/workspaces/{ws}/blackboard/tasks{suffix}"))
    if action == "create_task":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/tasks",
                method="POST",
                body={
                    "title": args.get("title"),
                    "description": args.get("description"),
                    "priority": args.get("priority"),
                    "assignee_id": args.get("assignee_id"),
                    "estimated_value": args.get("estimated_value"),
                },
            )
        )
    if action == "update_task":
        body = _filtered_body(
            args,
            "status",
            "description",
            "title",
            "priority",
            "assignee_id",
            "actual_value",
            "token_cost",
            "blocker_reason",
            "estimated_value",
        )
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/tasks/{args.get('task_id')}",
                method="PUT",
                body=body,
            )
        )
    if action == "list_objectives":
        return _json_result(_bb_api_fetch(cfg, f"/workspaces/{ws}/blackboard/objectives"))
    if action == "create_objective":
        body = {"title": args.get("title")}
        body.update(_filtered_body(args, "description", "obj_type", "parent_id"))
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/objectives",
                method="POST",
                body=body,
            )
        )
    if action == "update_objective":
        body = _filtered_body(args, "title", "description", "progress", "obj_type", "parent_id")
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/objectives/{args.get('objective_id')}",
                method="PUT",
                body=body,
            )
        )
    if action == "list_posts":
        suffix = ""
        if args.get("page") is not None:
            suffix = "?" + urllib.parse.urlencode({"page": str(args["page"])})
        return _json_result(_bb_api_fetch(cfg, f"/workspaces/{ws}/blackboard/posts{suffix}"))
    if action == "create_post":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/posts",
                method="POST",
                body={"title": args.get("title"), "content": args.get("content")},
            )
        )
    if action == "get_post":
        return _json_result(
            _bb_api_fetch(cfg, f"/workspaces/{ws}/blackboard/posts/{args.get('post_id')}")
        )
    if action == "reply_post":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/posts/{args.get('post_id')}/replies",
                method="POST",
                body={"content": args.get("content")},
            )
        )
    if action == "update_post":
        body = _filtered_body(args, "title", "content")
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/posts/{args.get('post_id')}",
                method="PUT",
                body=body,
            )
        )
    if action == "delete_post":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/posts/{args.get('post_id')}",
                method="DELETE",
            )
        )
    if action == "pin_post":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/posts/{args.get('post_id')}/pin",
                method="POST",
            )
        )
    if action == "unpin_post":
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/posts/{args.get('post_id')}/pin",
                method="DELETE",
            )
        )
    return _json_result({"error": f"Unknown action: {action}"})


def topology_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())

    action = str(args.get("action") or "")
    ws = cfg.workspace_id
    if action == "get_topology":
        return _json_result(_api_fetch(cfg, f"/workspaces/{ws}/topology"))
    if action == "get_members":
        return _json_result(_api_fetch(cfg, f"/workspaces/{ws}/members"))
    if action == "get_my_neighbors":
        topo = _api_fetch(cfg, f"/workspaces/{ws}/topology")
        if isinstance(topo, dict) and topo.get("error"):
            return _json_result(topo)

        data = topo.get("data") if isinstance(topo, dict) else None
        nodes = data.get("nodes", []) if isinstance(data, dict) else []
        edges = data.get("edges", []) if isinstance(data, dict) else []
        my_id = str(args.get("my_instance_id") or cfg.instance_id or "")
        if not my_id:
            return _json_result(_missing_instance_payload())

        my_node = next((node for node in nodes if isinstance(node, dict) and node.get("entity_id") == my_id), None)
        if not my_node:
            return _json_result({"error": "Node not found for this instance"})

        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            a = f"{edge.get('a_q')},{edge.get('a_r')}"
            b = f"{edge.get('b_q')},{edge.get('b_r')}"
            adjacency.setdefault(a, []).append(b)
            adjacency.setdefault(b, []).append(a)

        node_map = {
            f"{node.get('hex_q')},{node.get('hex_r')}": node
            for node in nodes
            if isinstance(node, dict)
        }
        start = f"{my_node.get('hex_q')},{my_node.get('hex_r')}"
        visited = {start}
        queue = [start]
        reachable: list[dict[str, Any]] = []
        while queue:
            cur = queue.pop(0)
            for neighbor in adjacency.get(cur, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                node = node_map.get(neighbor)
                if not isinstance(node, dict):
                    continue
                node_type = node.get("node_type")
                if node_type in {"agent", "human"}:
                    reachable.append(node)
                elif node_type == "corridor":
                    queue.append(neighbor)
                elif node_type == "blackboard":
                    reachable.append(node)
                    queue.append(neighbor)
        return _json_result(reachable)
    return _json_result({"error": f"Unknown action: {action}"})


def collaboration_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())
    if not cfg.instance_id:
        return _json_result(_missing_instance_payload())

    action = str(args.get("action") or "")
    ws = cfg.workspace_id
    if action == "send_message":
        target = str(args.get("target") or "")
        text = str(args.get("text") or "")
        if not target or not text:
            return _json_result({"error": "Both 'target' and 'text' are required."})
        if not target.startswith("agent:") and not target.startswith("human:"):
            target = f"agent:{target}"
        return _json_result(
            _api_fetch(
                cfg,
                f"/workspaces/{ws}/collaboration/send",
                method="POST",
                body={
                    "target": target,
                    "text": text,
                    "depth": int(args.get("depth") or 0),
                    "conversation_id": args.get("conversation_id"),
                },
            )
        )
    if action == "get_timeline":
        params: dict[str, str] = {"limit": str(min(int(args.get("limit") or 50), 200))}
        since = args.get("since")
        if since:
            params["since"] = str(since)
        query = urllib.parse.urlencode(params)
        return _json_result(_api_fetch(cfg, f"/workspaces/{ws}/collaboration-timeline?{query}"))
    if action == "get_my_messages":
        limit = str(min(int(args.get("limit") or 50), 200))
        return _json_result(
            _api_fetch(
                cfg,
                f"/workspaces/{ws}/agents/{cfg.instance_id}/collaboration-messages?limit={limit}",
            )
        )
    return _json_result({"error": f"Unknown action: {action}"})


def shared_files_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())

    action = str(args.get("action") or "")
    ws = cfg.workspace_id
    if action == "list":
        parent_path = str(args.get("parent_path") or "/")
        query = urllib.parse.urlencode({"parent_path": parent_path})
        return _json_result(
            _bb_api_fetch(cfg, f"/workspaces/{ws}/blackboard/files?{query}")
        )
    if action == "upload":
        filename = str(args.get("filename") or "untitled.txt")
        content = str(args.get("content") or "")
        parent_path = str(args.get("parent_path") or "/")
        content_type = str(args.get("content_type") or "text/plain")
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/files/upload",
                method="POST",
                body={
                    "filename": filename,
                    "content": content,
                    "parent_path": parent_path,
                    "content_type": content_type,
                },
            )
        )
    if action == "mkdir":
        path = str(args.get("path") or "")
        if not path:
            return _json_result({"error": "'path' is required for mkdir."})
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/files/mkdir",
                method="POST",
                body={"path": path},
            )
        )
    if action == "read":
        file_id = str(args.get("file_id") or "")
        if not file_id:
            return _json_result({"error": "'file_id' is required for read."})
        return _json_result(
            _bb_api_fetch(cfg, f"/workspaces/{ws}/blackboard/files/{file_id}/content")
        )
    if action == "delete":
        file_id = str(args.get("file_id") or "")
        if not file_id:
            return _json_result({"error": "'file_id' is required for delete."})
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/files/{file_id}",
                method="DELETE",
            )
        )
    if action == "copy":
        file_id = str(args.get("file_id") or "")
        if not file_id:
            return _json_result({"error": "'file_id' is required for copy."})
        body = _filtered_body(args, "target_parent_path", "target_filename")
        return _json_result(
            _bb_api_fetch(
                cfg,
                f"/workspaces/{ws}/blackboard/files/{file_id}/copy",
                method="POST",
                body=body,
            )
        )
    return _json_result({"error": f"Unknown action: {action}"})


def performance_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())

    action = str(args.get("action") or "")
    ws = cfg.workspace_id
    instance_id = str(args.get("my_instance_id") or cfg.instance_id or "")
    if action == "get_my_performance":
        if not instance_id:
            return _json_result(_missing_instance_payload())
        query = urllib.parse.urlencode({"instance_id": instance_id})
        return _json_result(_api_fetch(cfg, f"/workspaces/{ws}/performance?{query}"))
    if action == "get_team_performance":
        return _json_result(_api_fetch(cfg, f"/workspaces/{ws}/performance"))
    if action == "collect_performance":
        return _json_result(_api_fetch(cfg, f"/workspaces/{ws}/performance/collect", method="POST"))
    return _json_result({"error": f"Unknown action: {action}"})


def proposals_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())

    action = str(args.get("action") or "")
    agent_id = str(args.get("agent_instance_id") or cfg.instance_id or "")
    if action in {"submit_approval_request", "check_trust_policy", "list_my_decisions"} and not agent_id:
        return _json_result(_missing_instance_payload())

    ws = cfg.workspace_id
    if action == "submit_approval_request":
        return _json_result(
            _api_fetch(
                cfg,
                "/workspaces/approval-requests",
                method="POST",
                body={
                    "workspace_id": ws,
                    "agent_instance_id": agent_id,
                    "action_type": args.get("action_type"),
                    "proposal": args.get("proposal"),
                    "context_summary": args.get("context_summary"),
                },
            )
        )
    if action == "check_trust_policy":
        query = urllib.parse.urlencode(
            {
                "workspace_id": ws,
                "agent_instance_id": agent_id,
                "action_type": str(args.get("action_type") or ""),
            }
        )
        return _json_result(_api_fetch(cfg, f"/workspaces/trust-policies/check?{query}"))
    if action == "list_my_decisions":
        query = urllib.parse.urlencode({"agent_id": agent_id})
        return _json_result(_api_fetch(cfg, f"/workspaces/{ws}/decision-records?{query}"))
    return _json_result({"error": f"Unknown action: {action}"})


def gene_discovery_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    action = str(args.get("action") or "")
    if action == "search_genes":
        query = urllib.parse.urlencode(
            _filtered_body(args, "keyword", "category")
        )
        suffix = f"?{query}" if query else ""
        return _json_result(_api_fetch(cfg, f"/genes{suffix}"))
    if action == "get_gene_detail":
        return _json_result(_api_fetch(cfg, f"/genes/{args.get('gene_id')}"))
    if action == "request_gene_learning":
        if not cfg.instance_id:
            return _json_result(_missing_instance_payload())
        return _json_result(
            _api_fetch(
                cfg,
                f"/instances/{cfg.instance_id}/genes/install",
                method="POST",
                body={"gene_slug": args.get("gene_slug")},
            )
        )
    return _json_result({"error": f"Unknown action: {action}"})


def file_download_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())

    file_id = str(args.get("file_id") or "")
    if not file_id:
        return _json_result({"error": "file_id is required"})

    headers = {}
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"

    url = f"{cfg.api_url}/workspaces/{cfg.workspace_id}/files/{urllib.parse.quote(file_id, safe='')}/download"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            disposition = response.headers.get("Content-Disposition")
            original_name = _parse_content_disposition_filename(disposition) or "unnamed"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return _json_result({"error": "File not found or has been deleted."})
        if exc.code == 403:
            return _json_result({"error": "No permission to access this file."})
        detail = exc.read().decode("utf-8", errors="replace")
        return _json_result({"error": f"Download failed (HTTP {exc.code}): {detail or exc.reason}"})
    except (urllib.error.URLError, OSError) as exc:
        return _json_result({"error": f"Network error: {exc}"})

    save_name = _sanitize_download_filename(str(args.get("save_as") or original_name))
    uploads_dir = cfg.workspace_root / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    local_path = _resolve_unique_file_path(uploads_dir, save_name)
    local_path.write_bytes(payload)

    return _json_result(
        {
            "path": str(local_path),
            "name": save_name,
            "size": len(payload),
            "content_type": content_type,
        }
    )


def chat_history_tool(args: dict[str, Any], **kwargs: Any) -> str:
    cfg = _resolve_tool_config(kwargs)
    if not cfg.workspace_id:
        return _json_result(_missing_workspace_payload())

    params: dict[str, str] = {"limit": str(min(int(args.get("limit") or 20), 100))}
    for key in ("q", "from_at", "to_at"):
        value = args.get(key)
        if value:
            params[key] = str(value)
    query = urllib.parse.urlencode(params)
    return _json_result(_api_fetch(cfg, f"/workspaces/{cfg.workspace_id}/messages?{query}"))


def _resolve_tool_config(kwargs: dict[str, Any]) -> ToolConfig:
    api_url = str(
        os.environ.get("NODESKCLAW_API_URL")
        or os.environ.get("DESKCLAW_API_URL")
        or _DEFAULT_API_URL
    ).rstrip("/")
    token = str(
        os.environ.get("NODESKCLAW_TOKEN")
        or os.environ.get("DESKCLAW_TOKEN")
        or ""
    )
    instance_id = str(
        os.environ.get("NODESKCLAW_INSTANCE_ID")
        or os.environ.get("DESKCLAW_INSTANCE_ID")
        or ""
    )
    workspace_root = Path(
        os.environ.get("NODESKCLAW_WORKSPACE_ROOT")
        or os.environ.get("DESKCLAW_WORKSPACE_ROOT")
        or (Path.home() / ".openclaw" / "workspace")
    )
    session_id = str(kwargs.get("session_id") or getattr(_thread_state, "session_id", ""))
    task_id = str(kwargs.get("task_id") or getattr(_thread_state, "task_id", ""))
    workspace_id = _resolve_workspace_id(
        task_id=task_id,
        session_id=session_id,
    )
    return ToolConfig(
        api_url=api_url,
        token=token,
        workspace_id=workspace_id,
        instance_id=instance_id,
        workspace_root=workspace_root,
    )


def _resolve_workspace_id(*, task_id: str, session_id: str) -> str:
    for value in (task_id, session_id):
        if value.startswith(_WORKSPACE_SESSION_PREFIX):
            return value[len(_WORKSPACE_SESSION_PREFIX):]
    return str(
        os.environ.get("NODESKCLAW_WORKSPACE_ID")
        or os.environ.get("DESKCLAW_WORKSPACE_ID")
        or ""
    )


def _on_pre_tool_call(*, session_id: str = "", task_id: str = "", **_: Any) -> None:
    _thread_state.session_id = session_id or ""
    _thread_state.task_id = task_id or ""


def _on_post_tool_call(**_: Any) -> None:
    _thread_state.session_id = ""
    _thread_state.task_id = ""


def _api_fetch(
    cfg: ToolConfig,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> Any:
    url = f"{cfg.api_url}{path}"
    headers = {"Content-Type": "application/json"}
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"error": True, "status": exc.code, "message": detail or exc.reason}
    except (urllib.error.URLError, OSError) as exc:
        return {"error": True, "message": f"Network error: {exc}"}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": True, "message": "Response is not valid JSON"}


def _bb_api_fetch(
    cfg: ToolConfig,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
) -> Any:
    result = _api_fetch(cfg, path, method=method, body=body)
    if isinstance(result, dict) and result.get("status") == 403:
        try:
            parsed = json.loads(str(result.get("message") or "{}"))
        except json.JSONDecodeError:
            parsed = {}
        detail = parsed.get("detail") if isinstance(parsed, dict) else None
        message_key = detail.get("message_key", "") if isinstance(detail, dict) else ""
        if isinstance(message_key, str) and message_key.startswith("errors.topology."):
            return {
                "error": "topology_unreachable",
                "message": (
                    "You are not connected to the blackboard via corridor topology. "
                    "Use nodeskclaw_topology get_my_neighbors to check your reachable nodes."
                ),
            }
    return result


def _json_result(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _missing_workspace_payload() -> dict[str, Any]:
    return {
        "error": True,
        "message": (
            "Workspace context is missing. Hermes expected task_id/session_id like "
            "'workspace:<workspace_id>' or NODESKCLAW_WORKSPACE_ID in the environment."
        ),
    }


def _missing_instance_payload() -> dict[str, Any]:
    return {
        "error": True,
        "message": "NODESKCLAW_INSTANCE_ID is not configured for this Hermes runtime.",
    }


def _filtered_body(args: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: args[key] for key in keys if key in args and args[key] is not None}


def _parse_content_disposition_filename(header: str | None) -> str | None:
    if not header:
        return None
    utf8_match = re.search(r"filename\\*=UTF-8''(.+)", header, re.IGNORECASE)
    if utf8_match:
        return urllib.parse.unquote(utf8_match.group(1))
    match = re.search(r'filename="?([^";\\n]+)"?', header, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _sanitize_download_filename(filename: str) -> str:
    safe_name = filename.replace("\\", "/").split("/")[-1].strip()
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "", safe_name)
    safe_name = safe_name.strip(". ")
    return safe_name or "unnamed"


def _resolve_unique_file_path(directory: Path, filename: str) -> Path:
    base_dir = directory.resolve()
    candidate = (base_dir / _sanitize_download_filename(filename)).resolve()
    if not candidate.is_relative_to(base_dir):
        raise ValueError("download path escapes uploads directory")
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 0
    while candidate.exists():
        counter += 1
        candidate = (base_dir / f"{stem}({counter}){suffix}").resolve()
        if not candidate.is_relative_to(base_dir):
            raise ValueError("download path escapes uploads directory")
    return candidate


_BLACKBOARD_SCHEMA = {
    "name": "nodeskclaw_blackboard",
    "description": "Workspace blackboard operations: content, tasks, objectives, and BBS discussion posts.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "get_blackboard",
                    "update_blackboard",
                    "patch_section",
                    "list_tasks",
                    "create_task",
                    "update_task",
                    "list_objectives",
                    "create_objective",
                    "update_objective",
                    "list_posts",
                    "create_post",
                    "get_post",
                    "reply_post",
                    "update_post",
                    "delete_post",
                    "pin_post",
                    "unpin_post",
                ],
                "description": "Which blackboard operation to perform.",
            },
            "title": {"type": "string", "description": "Task/post/objective title."},
            "description": {"type": "string", "description": "Task/objective description."},
            "content": {"type": "string", "description": "Markdown content for blackboard and BBS write actions."},
            "section": {"type": "string", "description": "patch_section: section heading to update."},
            "priority": {
                "type": "string",
                "enum": ["urgent", "high", "medium", "low"],
                "description": "create_task / update_task priority.",
            },
            "assignee_id": {"type": "string", "description": "create_task: assign to agent instance ID."},
            "estimated_value": {"type": "number", "description": "create_task: estimated monetary value."},
            "task_id": {"type": "string", "description": "update_task: target task ID."},
            "post_id": {"type": "string", "description": "Target post ID for post operations."},
            "objective_id": {"type": "string", "description": "update_objective: target objective ID."},
            "obj_type": {"type": "string", "description": "Objective type."},
            "parent_id": {"type": "string", "description": "Parent objective ID."},
            "progress": {"type": "number", "description": "update_objective: progress 0.0 ~ 1.0."},
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done", "blocked", "failed"],
                "description": "update_task: new task status.",
            },
            "actual_value": {"type": "number", "description": "update_task: actual output value."},
            "token_cost": {"type": "number", "description": "update_task: tokens consumed."},
            "blocker_reason": {"type": "string", "description": "update_task: reason when blocked."},
            "filter_status": {"type": "string", "description": "list_tasks: optional status filter."},
            "page": {"type": "number", "description": "list_posts: page number."},
        },
        "required": ["action"],
    },
}

_TOPOLOGY_SCHEMA = {
    "name": "nodeskclaw_topology",
    "description": "Query workspace topology: full graph, members, and reachable neighbors via corridor BFS.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_topology", "get_members", "get_my_neighbors"],
                "description": "Which topology operation to perform.",
            },
            "my_instance_id": {"type": "string", "description": "Optional override of current instance ID."},
        },
        "required": ["action"],
    },
}

_COLLABORATION_SCHEMA = {
    "name": "nodeskclaw_collaboration",
    "description": (
        "Send messages to other agents or humans in the workspace, "
        "and query the collaboration timeline. "
        "Use 'send_message' with target='agent:<name>' or target='agent:<instance_id>' "
        "to talk to another agent. The target agent will receive your message and can reply."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["send_message", "get_timeline", "get_my_messages"],
                "description": "Which collaboration operation to perform.",
            },
            "target": {
                "type": "string",
                "description": (
                    "send_message: target identifier. Use 'agent:<display_name>' to reach "
                    "another agent by name, or 'human:<display_name>' for a human member."
                ),
            },
            "text": {"type": "string", "description": "send_message: message content."},
            "depth": {"type": "number", "description": "send_message: collaboration chain depth (default 0)."},
            "conversation_id": {"type": "string", "description": "send_message: optional conversation to continue."},
            "limit": {"type": "number", "description": "get_timeline/get_my_messages: max results (default 50)."},
            "since": {"type": "string", "description": "get_timeline: ISO 8601 timestamp filter."},
        },
        "required": ["action"],
    },
}

_SHARED_FILES_SCHEMA = {
    "name": "nodeskclaw_shared_files",
    "description": (
        "Manage shared files on the workspace blackboard. "
        "List, upload (text content), read, delete, copy files and create directories. "
        "Files here are visible to ALL workspace members in the blackboard Files tab."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "upload", "read", "delete", "mkdir", "copy"],
                "description": "Which file operation to perform.",
            },
            "parent_path": {
                "type": "string",
                "description": "list/upload: parent directory path (default '/').",
            },
            "filename": {"type": "string", "description": "upload: filename to create."},
            "content": {"type": "string", "description": "upload: text content of the file."},
            "content_type": {"type": "string", "description": "upload: MIME type (default 'text/plain')."},
            "path": {"type": "string", "description": "mkdir: directory path to create."},
            "file_id": {"type": "string", "description": "read/delete/copy: target file ID."},
            "target_parent_path": {"type": "string", "description": "copy: destination parent path."},
            "target_filename": {"type": "string", "description": "copy: destination filename."},
        },
        "required": ["action"],
    },
}

_PERFORMANCE_SCHEMA = {
    "name": "nodeskclaw_performance",
    "description": "Read performance metrics: own performance, team comparison, or trigger collection.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get_my_performance", "get_team_performance", "collect_performance"],
                "description": "Which performance operation to perform.",
            },
            "my_instance_id": {"type": "string", "description": "Optional override of current instance ID."},
        },
        "required": ["action"],
    },
}

_PROPOSALS_SCHEMA = {
    "name": "nodeskclaw_proposals",
    "description": "Submit structured proposals and inspect trust-policy decisions.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["submit_approval_request", "check_trust_policy", "list_my_decisions"],
                "description": "Which proposal operation to perform.",
            },
            "action_type": {"type": "string", "description": "Proposal action type."},
            "proposal": {"type": "object", "description": "Structured proposal payload."},
            "context_summary": {"type": "string", "description": "Why the proposal is needed."},
            "agent_instance_id": {"type": "string", "description": "Optional override of current instance ID."},
        },
        "required": ["action"],
    },
}

_GENE_DISCOVERY_SCHEMA = {
    "name": "nodeskclaw_gene_discovery",
    "description": "Search the gene market, inspect gene details, or request to learn a new gene.",
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search_genes", "get_gene_detail", "request_gene_learning"],
                "description": "Which gene operation to perform.",
            },
            "keyword": {"type": "string", "description": "search_genes: keyword."},
            "category": {"type": "string", "description": "search_genes: category filter."},
            "gene_id": {"type": "string", "description": "get_gene_detail: gene ID."},
            "gene_slug": {"type": "string", "description": "request_gene_learning: gene slug."},
            "reason": {"type": "string", "description": "Optional reason for learning the gene."},
        },
        "required": ["action"],
    },
}

_FILE_DOWNLOAD_SCHEMA = {
    "name": "nodeskclaw_file_download",
    "description": (
        "Download a workspace attachment to the local OpenClaw-compatible workspace uploads/ directory "
        "so Hermes can inspect it with normal file tools."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Attachment file_id to download."},
            "save_as": {"type": "string", "description": "Optional local filename override."},
        },
        "required": ["file_id"],
    },
}

_CHAT_HISTORY_SCHEMA = {
    "name": "nodeskclaw_chat_history",
    "description": "Query workspace chat history with optional keyword or time-range filters.",
    "parameters": {
        "type": "object",
        "properties": {
            "q": {"type": "string", "description": "Keyword search."},
            "limit": {"type": "number", "description": "Number of messages to return (default 20, max 100)."},
            "from_at": {"type": "string", "description": "Start time in ISO 8601 format."},
            "to_at": {"type": "string", "description": "End time in ISO 8601 format."},
        },
        "required": [],
    },
}
