"""基于文件系统的通用适配器，与 TypeScript generic.ts 对齐。"""

from datetime import UTC, datetime
from pathlib import Path

import yaml

from genehub_sdk.adapters.base import GeneAdapter
from genehub_sdk.types import (
    GeneManifest,
    InstalledGene,
    InstallOptions,
    InstallResult,
    UninstallOptions,
    UninstallResult,
)

DEFAULT_GENES_DIR = Path.cwd() / ".genehub" / "genes"


class GenericAdapter(GeneAdapter):
    """将基因写入本地目录的适配器，默认 `.genehub/genes/<slug>/`。"""

    def __init__(self, genes_dir: str | Path | None = None) -> None:
        self._genes_dir = Path(genes_dir) if genes_dir else DEFAULT_GENES_DIR

    @property
    def product(self) -> str:
        return "generic"

    def detect(self) -> bool:
        return True

    def install(
        self,
        manifest: GeneManifest,
        options: InstallOptions | None = None,
    ) -> InstallResult:
        opts = options or {}
        target = opts.get("target_path")
        if target:
            target_dir = Path(target) / manifest["slug"]
        else:
            target_dir = self._genes_dir / manifest["slug"]
        target_dir.mkdir(parents=True, exist_ok=True)
        files: list[str] = []

        gene_yaml = target_dir / "gene.yaml"
        gene_yaml.write_text(
            yaml.safe_dump(manifest, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        files.append(str(gene_yaml))

        skill = manifest.get("skill") or {}
        if skill.get("content"):
            skill_path = target_dir / "SKILL.md"
            skill_path.write_text(skill["content"], encoding="utf-8")
            files.append(str(skill_path))

        deps = [
            d["slug"]
            for d in (manifest.get("dependencies") or [])
            if isinstance(d.get("slug"), str)
        ]
        return {
            "success": True,
            "slug": manifest["slug"],
            "version": manifest["version"],
            "files": files,
            "needs_restart": False,
            "dependencies": deps,
        }

    def uninstall(self, slug: str, options: UninstallOptions | None = None) -> UninstallResult:
        target_dir = self._genes_dir / slug
        if target_dir.exists():
            import shutil

            shutil.rmtree(target_dir, ignore_errors=True)
        return {
            "success": True,
            "slug": slug,
            "files": [str(target_dir)],
            "needs_restart": False,
        }

    def is_installed(self, slug: str) -> bool:
        return (self._genes_dir / slug / "gene.yaml").is_file()

    def list(self) -> list[InstalledGene]:
        result: list[InstalledGene] = []
        if not self._genes_dir.is_dir():
            return result
        for path in self._genes_dir.iterdir():
            if not path.is_dir():
                continue
            yaml_path = path / "gene.yaml"
            if not yaml_path.is_file():
                continue
            try:
                raw = yaml_path.read_text(encoding="utf-8")
                data = yaml.safe_load(raw)
                version = (
                    (data.get("version") or "unknown") if isinstance(data, dict) else "unknown"
                )
                if not isinstance(version, str):
                    version = "unknown"
                mtime = datetime.fromtimestamp(yaml_path.stat().st_mtime, tz=UTC)
                result.append(
                    {
                        "slug": path.name,
                        "version": version,
                        "installed_at": mtime.isoformat(),
                        "files": [str(yaml_path)],
                    }
                )
            except (OSError, yaml.YAMLError):
                continue
        return result

    def get_installed_version(self, slug: str) -> str | None:
        yaml_path = self._genes_dir / slug / "gene.yaml"
        if not yaml_path.is_file():
            return None
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("version"), str):
                return data["version"]
        except (OSError, yaml.YAMLError):
            pass
        return None
