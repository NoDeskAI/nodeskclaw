"""LearningEngine 单元测试（最小可用）。"""

from pathlib import Path

from genehub_sdk.learning import LearningEngine
from genehub_sdk.types import GeneManifest


def _sample_manifest() -> GeneManifest:
    return {
        "slug": "test-gene",
        "name": "Test Gene",
        "version": "1.0.0",
        "description": "Desc",
        "short_description": "Short",
        "category": "development",
        "tags": ["ability"],
        "compatibility": [{"product": "openclaw"}],
        "skill": {"name": "test-gene", "always": False, "content": "# Skill\n\nContent."},
    }


def test_create_learning_task_creates_file(tmp_path: Path) -> None:
    engine = LearningEngine(workspace_dir=tmp_path)
    manifest = _sample_manifest()
    task = engine.create_learning_task(manifest)
    assert task["gene_slug"] == "test-gene"
    assert task["mode"] == "learn"
    assert (tmp_path / "learning-tasks" / "test-gene.md").is_file()
    assert (tmp_path / "learning-results").is_dir()


def test_check_result_returns_none_when_no_file(tmp_path: Path) -> None:
    engine = LearningEngine(workspace_dir=tmp_path)
    assert engine.check_result("test-gene") is None


def test_check_result_parses_result_file(tmp_path: Path) -> None:
    engine = LearningEngine(workspace_dir=tmp_path)
    (tmp_path / "learning-results").mkdir(parents=True, exist_ok=True)
    result_path = tmp_path / "learning-results" / "test-gene.md"
    result_path.write_text(
        "---\ntask_id: t1\ngene_slug: test-gene\ndecision: learned\n---\n\nLearned content.",
        encoding="utf-8",
    )
    result = engine.check_result("test-gene")
    assert result is not None
    assert result["gene_slug"] == "test-gene"
    assert result["decision"] == "learned"
    assert "Learned content" in (result.get("content") or "")
