"""标准学习协议引擎（最小可用）：创建学习任务、检查结果。"""

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from genehub_sdk.types import GeneManifest


class LearningEngine:
    """创建学习任务、解析结果文件；可选注入 Adapter/Client 用于 meta-gene 等（后续扩展）。"""

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        adapter: Any = None,
        client: Any = None,
    ) -> None:
        self._workspace = Path(workspace_dir)
        self._adapter = adapter
        self._client = client

    @property
    def _tasks_dir(self) -> Path:
        return self._workspace / "learning-tasks"

    @property
    def _results_dir(self) -> Path:
        return self._workspace / "learning-results"

    def create_learning_task(self, manifest: GeneManifest) -> dict[str, Any]:
        """创建学习任务，写入 learning-tasks/<slug>.md，返回任务信息。"""
        self._tasks_dir.mkdir(parents=True, exist_ok=True)
        self._results_dir.mkdir(parents=True, exist_ok=True)

        slug = manifest.get("slug") or "unknown"
        task_id = f"learn-{slug}-{id(manifest)}"
        skill = manifest.get("skill") or {}
        learning = manifest.get("learning")

        task: dict[str, Any] = {
            "mode": "learn",
            "task_id": task_id,
            "gene_slug": slug,
            "gene_name": manifest.get("name") or slug,
            "gene_version": manifest.get("version") or "0.0.0",
            "gene_content": skill.get("content") or "",
            "gene_meta": {
                "name": manifest.get("name") or slug,
                "description": manifest.get("description") or "",
                "category": manifest.get("category") or "general",
                "short_description": manifest.get("short_description") or "",
            },
            "callback_path": str(self._results_dir / f"{slug}.md"),
            "created_at": datetime.now(UTC).isoformat(),
        }
        if learning:
            task["learning"] = {
                "objectives": learning.get("objectives"),
                "scenarios": learning.get("scenarios"),
                "force_deep_learn": learning.get("force_deep_learn"),
            }

        md_lines = [
            "---",
            f"task_id: {task_id}",
            f"gene_slug: {slug}",
            f"gene_name: {task['gene_name']}",
            f"gene_version: {task['gene_version']}",
            "---",
            "",
            task["gene_content"],
        ]
        task_path = self._tasks_dir / f"{slug}.md"
        task_path.write_text("\n".join(md_lines), encoding="utf-8")
        return task

    def check_result(self, slug: str) -> dict[str, Any] | None:
        """读取 learning-results/<slug>.md，解析 frontmatter 与正文，返回结果或 None。"""
        result_path = self._results_dir / f"{slug}.md"
        if not result_path.is_file():
            return None
        try:
            content = result_path.read_text(encoding="utf-8")
        except OSError:
            return None
        return self._parse_result(content)

    def _parse_result(self, content: str) -> dict[str, Any] | None:
        m = re.match(r"^---\n([\s\S]*?)\n---", content)
        if not m:
            return None
        fm = m.group(1)
        get_: dict[str, str] = {}
        for line in fm.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                get_[k.strip()] = v.strip().strip("'\"")

        task_id = get_.get("task_id")
        gene_slug = get_.get("gene_slug")
        decision = get_.get("decision")
        if not task_id or not gene_slug or not decision:
            return None
        body_start = content.find("---", 4)
        body = content[body_start + 3 :].strip() if body_start != -1 else None
        self_eval = get_.get("self_eval")
        return {
            "task_id": task_id,
            "gene_slug": gene_slug,
            "mode": get_.get("mode", "learn"),
            "decision": decision,
            "content": body or None,
            "self_eval": float(self_eval) if self_eval else None,
            "reason": get_.get("reason"),
            "completed_at": get_.get("completed_at", ""),
        }
