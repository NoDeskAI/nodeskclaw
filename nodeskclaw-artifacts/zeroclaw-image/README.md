# ZeroClaw 镜像构建

ZeroClaw 是基于 Rust 构建的高性能 AI Agent 运行时，提供 OpenAI 兼容的 API 接口。

## 目录结构

```
zeroclaw-image/
├── Dockerfile             # Base 镜像: debian:bookworm-slim + 预编译二进制下载
├── Dockerfile.security    # 安全层镜像: 多阶段 Rust 源码构建（git clone + cargo build）
├── docker-entrypoint.sh   # 容器入口脚本
├── build-and-push.sh      # 构建和推送脚本（支持 --with-security）
└── README.md              # 本文件
```

## 构建

### Base 镜像（无安全层）

```bash
./build-and-push.sh --version v0.1.0
./build-and-push.sh --version v0.1.0 --build-only
./build-and-push.sh --version v0.1.0 --skip-verify
```

### 安全层镜像（Rust 源码构建）

```bash
# 使用默认 git 仓库和分支
./build-and-push.sh --with-security --base-tag v0.1.0 --build-only

# 指定 git 仓库和 ref
ZEROCLAW_REPO=https://github.com/nicholasgasior/zeroclaw.git ZEROCLAW_REF=v0.2.0 \
  ./build-and-push.sh --with-security --base-tag v0.1.0 --build-only
```

安全层模式不继承 base 镜像，而是完整的多阶段 Rust 源码构建：
- Stage 1: `rust:1.82-slim` builder，git clone zeroclaw 源码 + cargo build
- Stage 2: `debian:bookworm-slim` runtime，仅拷贝编译后的二进制
- 使用 BuildKit cache mount 缓存 Cargo registry，增量编译加速

**注意**: 构建目标平台为 `linux/amd64`，在 Apple Silicon 设备上通过 QEMU 模拟运行。Rust 编译首次可能需要较长时间。

## 镜像说明

- 基础镜像: `debian:bookworm-slim`
- Base 模式: 从 GitHub Release 下载 ZeroClaw 预编译的 `linux/amd64` 二进制
- Security 模式: 从源码编译，包含安全层集成
- 默认监听端口: `8080`
- 提供 `/health` 健康检查端点
