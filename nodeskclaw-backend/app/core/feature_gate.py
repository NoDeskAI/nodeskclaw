"""CE/EE Feature Gate — 运行时功能开关。

通过检测项目根目录下 ee/ 子目录是否存在来判断 edition：
  - ee/ 存在 -> edition = "ee"，所有 feature 启用
  - ee/ 不存在 -> edition = "ce"，仅 CE feature 启用

EE feature 清单从 features.yaml 加载，支持 ee/features.yaml 合并扩展。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(
    os.getenv("NODESKCLAW_ROOT", str(Path(__file__).resolve().parents[3]))
)
_FEATURES_YAML = _PROJECT_ROOT / "features.yaml"
_EE_DIR = _PROJECT_ROOT / "ee"
_EE_FEATURES_YAML = _EE_DIR / "features.yaml"


class FeatureGate:
    def __init__(self) -> None:
        self._edition: str = "ce"
        self._ee_feature_ids: set[str] = set()
        self._all_features: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        self._edition = "ee" if _EE_DIR.is_dir() else "ce"

        if _FEATURES_YAML.exists():
            with open(_FEATURES_YAML) as f:
                data = yaml.safe_load(f) or {}
            ee_features = data.get("edition_features", {}).get("ee", [])
            self._all_features.extend(ee_features)

        if self._edition == "ee" and _EE_FEATURES_YAML.exists():
            with open(_EE_FEATURES_YAML) as f:
                data = yaml.safe_load(f) or {}
            extra = data.get("edition_features", {}).get("ee", [])
            existing_ids = {f["id"] for f in self._all_features}
            for feat in extra:
                if feat["id"] not in existing_ids:
                    self._all_features.append(feat)

        self._ee_feature_ids = {f["id"] for f in self._all_features}

        logger.info(
            "FeatureGate: edition=%s, ee_features=%d",
            self._edition,
            len(self._ee_feature_ids),
        )

    @property
    def edition(self) -> str:
        return self._edition

    @property
    def is_ee(self) -> bool:
        return self._edition == "ee"

    def is_enabled(self, feature_id: str) -> bool:
        if feature_id not in self._ee_feature_ids:
            return True
        return self._edition == "ee"

    def enabled_features(self) -> list[str]:
        if self._edition == "ee":
            return sorted(self._ee_feature_ids)
        return []

    def all_features(self) -> list[dict[str, Any]]:
        return [
            {**f, "enabled": self.is_enabled(f["id"])}
            for f in self._all_features
        ]


feature_gate = FeatureGate()
