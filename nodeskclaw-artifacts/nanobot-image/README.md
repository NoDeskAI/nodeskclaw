# Nanobot 镜像构建

Nanobot 是基于 Python 的超轻量 AI Agent 运行时，提供 OpenAI 兼容的 API 接口。

## 目录结构

```
nanobot-image/
├── Dockerfile             # Base 镜像: python:3.13-slim-bookworm + pip install nanobot-ai
├── Dockerfile.security    # 安全层镜像: FROM base + pip install 安全层 + startup wrapper
├── nanobot.yaml.template  # Nanobot 配置模板（envsubst 替换环境变量）
├── docker-entrypoint.sh   # 容器入口脚本
├── build-and-push.sh      # 构建和推送脚本（支持 --with-security）
└── README.md              # 本文件
```

## 构建

### Base 镜像（无安全层）

```bash
./build-and-push.sh --version 0.1.0
./build-and-push.sh --version 0.1.0 --build-only
./build-and-push.sh --version 0.1.0 --skip-verify
```

### 安全层镜像

```bash
# 需要先有 base 镜像（v0.1.0）
./build-and-push.sh --with-security --base-tag v0.1.0 --build-only
```

安全层镜像 FROM base，`pip install nanobot-security-layer`，CMD 替换为 `startup.py` wrapper 在同一进程内 monkey-patch `ToolRegistry.execute` 后启动 nanobot CLI。

**注意**: 构建目标平台为 `linux/amd64`，在 Apple Silicon 设备上通过 QEMU 模拟运行。

## 镜像说明

- 基础镜像: `python:3.13-slim-bookworm`
- 通过 `pip install nanobot-ai` 安装
- 默认监听端口: `18790`
- 配置文件: `/opt/nanobot/nanobot.yaml`（首次启动时从模板生成）
