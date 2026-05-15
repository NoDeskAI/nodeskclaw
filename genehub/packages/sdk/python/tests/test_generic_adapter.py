"""GenericAdapter 单元测试（临时目录）。"""

from pathlib import Path

from genehub_sdk.adapters import GenericAdapter
from genehub_sdk.types import GeneManifest


def _sample_manifest() -> GeneManifest:
    return {
        "slug": "test-gene",
        "name": "Test Gene",
        "version": "1.0.0",
        "description": "Description",
        "short_description": "Short",
        "category": "development",
        "tags": ["ability"],
        "compatibility": [{"product": "openclaw"}],
        "skill": {"name": "test-gene", "always": False, "content": "# Skill\n\nContent here."},
        "dependencies": [{"slug": "other-gene", "version": ">=1.0", "optional": False}],
    }


def test_detect_returns_true() -> None:
    adapter = GenericAdapter()
    assert adapter.detect() is True


def test_install_creates_dir_and_files(tmp_path: Path) -> None:
    adapter = GenericAdapter(genes_dir=str(tmp_path))
    manifest = _sample_manifest()
    result = adapter.install(manifest)
    assert result["success"] is True
    assert result["slug"] == "test-gene"
    assert result["version"] == "1.0.0"
    assert "dependencies" in result
    assert "other-gene" in result["dependencies"]

    gene_dir = tmp_path / "test-gene"
    assert gene_dir.is_dir()
    assert (gene_dir / "gene.yaml").is_file()
    assert (gene_dir / "SKILL.md").is_file()
    assert (gene_dir / "SKILL.md").read_text(encoding="utf-8") == "# Skill\n\nContent here."


def test_install_with_target_path(tmp_path: Path) -> None:
    adapter = GenericAdapter(genes_dir=str(tmp_path))
    target = tmp_path / "custom"
    target.mkdir()
    result = adapter.install(_sample_manifest(), options={"target_path": str(target)})
    assert result["success"] is True
    assert (target / "test-gene" / "gene.yaml").is_file()


def test_uninstall_removes_dir(tmp_path: Path) -> None:
    adapter = GenericAdapter(genes_dir=str(tmp_path))
    adapter.install(_sample_manifest())
    assert adapter.is_installed("test-gene") is True
    result = adapter.uninstall("test-gene")
    assert result["success"] is True
    assert result["slug"] == "test-gene"
    assert adapter.is_installed("test-gene") is False


def test_list_returns_installed(tmp_path: Path) -> None:
    adapter = GenericAdapter(genes_dir=str(tmp_path))
    assert adapter.list() == []
    adapter.install(_sample_manifest())
    listed = adapter.list()
    assert len(listed) == 1
    assert listed[0]["slug"] == "test-gene"
    assert listed[0]["version"] == "1.0.0"


def test_get_installed_version(tmp_path: Path) -> None:
    adapter = GenericAdapter(genes_dir=str(tmp_path))
    assert adapter.get_installed_version("test-gene") is None
    adapter.install(_sample_manifest())
    assert adapter.get_installed_version("test-gene") == "1.0.0"
