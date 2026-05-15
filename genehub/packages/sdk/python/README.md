# GeneHub Python SDK

GeneHub 的 Python 客户端与产品适配层，与 TypeScript SDK 核心能力对齐，供 Python 侧 Agent 接入 GeneHub。

## 用途

- **GeneHubClient**：封装 Registry HTTP API，支持搜索基因、获取详情、获取 Manifest、发布基因。
- **GeneAdapter**：产品适配器抽象基类，定义 `detect` / `install` / `uninstall` / `is_installed` / `list`。
- **GenericAdapter**：基于文件系统的通用适配器，将基因写入 `.genehub/genes/`（可配置目录）。
- **LearningEngine**：标准学习协议引擎，创建学习任务、检查结果（最小可用）。

## 目录结构

```
packages/sdk/python/
├── pyproject.toml
├── README.md
├── src/
│   └── genehub_sdk/
│       ├── __init__.py
│       ├── client.py      # GeneHubClient
│       ├── types.py       # Gene / GeneManifest / 适配器相关类型
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py    # GeneAdapter 抽象基类
│       │   └── generic.py # GenericAdapter
│       └── learning/
│           ├── __init__.py
│           └── engine.py  # LearningEngine
└── tests/
    ├── test_client.py
    ├── test_generic_adapter.py
    └── test_learning_engine.py
```

## 使用方法

### 安装

在项目根目录使用 uv（推荐）：

```bash
uv add ./packages/sdk/python
# 或从 PyPI（发布后）：uv add genehub-sdk
```

### 客户端

```python
from genehub_sdk import GeneHubClient

client = GeneHubClient(base_url="https://registry.genehub.dev", token="ghb_xxx")
genes = client.search_genes("code")
gene = client.get_gene("clean-code")
manifest = client.get_manifest("clean-code", version="1.0.0")
published = client.publish(manifest)
```

### 适配器

```python
from genehub_sdk import GenericAdapter
from genehub_sdk.adapters import GeneAdapter

adapter: GeneAdapter = GenericAdapter(genes_dir="/path/to/genes")
if adapter.detect():
    adapter.install(manifest, options={"force": True})
    adapter.uninstall("clean-code")
    print(adapter.list())
```

### 学习引擎

```python
from genehub_sdk import GeneHubClient
from genehub_sdk.adapters import GenericAdapter
from genehub_sdk.learning import LearningEngine

engine = LearningEngine(workspace_dir=".", adapter=GenericAdapter(), client=GeneHubClient(...))
task = engine.create_learning_task(manifest)
result = engine.check_result(manifest["slug"])
```

## 技术栈

- Python 3.12+
- httpx（HTTP 客户端）
- PyYAML（Manifest 序列化）
- 测试：pytest、pytest-httpx
- Lint：Ruff

## 参考

- TypeScript SDK：`packages/sdk/typescript/src/`
- API 文档：`docs/architecture.md` 第 6 节
- 学习协议：`docs/gene-learning-protocol.md`
