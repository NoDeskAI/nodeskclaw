"""产品适配器抽象基类，与 types/adapter.ts GeneAdapter 对齐。"""

from abc import ABC, abstractmethod

from genehub_sdk.types import (
    GeneManifest,
    InstalledGene,
    InstallOptions,
    InstallResult,
    UninstallOptions,
    UninstallResult,
)


class GeneAdapter(ABC):
    """将 Gene Manifest 注入到目标产品的适配器接口。"""

    @property
    @abstractmethod
    def product(self) -> str:
        """产品标识，如 generic / openclaw / nanobot。"""
        ...

    @abstractmethod
    def detect(self) -> bool:
        """检测当前环境是否支持该适配器。"""
        ...

    @abstractmethod
    def install(
        self, manifest: GeneManifest, options: InstallOptions | None = None
    ) -> InstallResult:
        """安装基因。"""
        ...

    @abstractmethod
    def uninstall(self, slug: str, options: UninstallOptions | None = None) -> UninstallResult:
        """卸载基因。"""
        ...

    @abstractmethod
    def is_installed(self, slug: str) -> bool:
        """是否已安装该基因。"""
        ...

    @abstractmethod
    def list(self) -> list[InstalledGene]:
        """列出已安装的基因。"""
        ...

    def get_installed_version(self, slug: str) -> str | None:
        """返回已安装版本号，未安装返回 None。默认通过 list 查找。"""
        for g in self.list():
            if g["slug"] == slug:
                return g["version"]
        return None
