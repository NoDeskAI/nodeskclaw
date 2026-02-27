"""Advanced config schemas for Volume/Sidecar/Init/Network + custom labels/annotations."""

from typing import Literal

from pydantic import BaseModel


class VolumeConfig(BaseModel):
    """自定义 Volume 挂载配置，支持多种 volume 类型。"""
    name: str
    volume_type: Literal["pvc", "emptyDir", "configMap", "secret"] = "pvc"
    mount_path: str
    sub_path: str | None = None
    read_only: bool = False
    # type-specific fields
    pvc: str | None = None             # volume_type=pvc 时必填
    config_map_name: str | None = None  # volume_type=configMap 时
    secret_name: str | None = None      # volume_type=secret 时
    items: list[dict] | None = None     # configMap/secret 的 key->path 映射


class SidecarConfig(BaseModel):
    """Sidecar 容器配置。"""
    name: str
    image: str
    command: list[str] = []
    args: list[str] = []
    cpu_request: str = "100m"
    cpu_limit: str = "500m"
    mem_request: str = "128Mi"
    mem_limit: str = "512Mi"
    env_vars: dict[str, str] = {}
    ports: list[int] = []


class InitContainerConfig(BaseModel):
    """Init 容器配置。"""
    name: str
    image: str
    command: list[str] = []
    args: list[str] = []
    env_vars: dict[str, str] = {}


class NetworkConfig(BaseModel):
    """跨实例网络配置。"""
    peers: list[str] = []  # 允许互访的实例 ID 列表


class AdvancedConfig(BaseModel):
    """完整高级配置结构。"""
    volumes: list[VolumeConfig] = []
    sidecars: list[SidecarConfig] = []
    init_containers: list[InitContainerConfig] = []
    network: NetworkConfig = NetworkConfig()
    custom_labels: dict[str, str] = {}
    custom_annotations: dict[str, str] = {}
