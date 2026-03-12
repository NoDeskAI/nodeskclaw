# ZeroClaw 镜像构建

ZeroClaw 是基于 Rust 构建的高性能 AI Agent 运行时，提供 OpenAI 兼容的 API 接口。

## 目录结构

```
zeroclaw-image/
├── Dockerfile             # 多阶段构建，从 GitHub Release 下载预编译二进制
├── docker-entrypoint.sh   # 容器入口脚本
├── build-and-push.sh      # 构建和推送脚本（使用 common.sh 公共函数）
└── README.md              # 本文件
```

## 构建

```bash
# 构建指定版本
./build-and-push.sh --version v0.1.0

# 仅构建，不推送
./build-and-push.sh --version v0.1.0 --build-only

# 跳过验证步骤
./build-and-push.sh --version v0.1.0 --skip-verify
```

**注意**: 构建目标平台为 `linux/amd64`，在 Apple Silicon 设备上通过 QEMU 模拟运行。

## 镜像说明

- 基础镜像: `debian:bookworm-slim`
- 从 GitHub Release 下载 ZeroClaw 预编译的 `linux/amd64` 二进制
- 默认监听端口: `8080`
- 提供 `/health` 健康检查端点
