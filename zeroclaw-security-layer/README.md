# ZeroClaw Security Layer

ZeroClaw 工具执行安全流水线。通过 build-time `SecuredTool<T: Tool>` trait wrapper 在编译期注入安全流水线。

## 架构

```
SecuredTool<T: Tool>           (implements Tool trait)
  └── SecurityPipeline
        ├── Before Phase: policy-gate → approval-channel → ...
        ├── Around Phase: inner.execute(args)  (原始工具执行)
        └── After Phase: dlp-scanner → audit-logger → ...
```

Pipeline Core 零安全逻辑，所有安全能力由 SecurityPlugin trait 实现提供。

## 目录结构

```
zeroclaw-security-layer/
├── Cargo.toml
├── README.md
└── src/
    ├── lib.rs                # crate root, re-exports
    ├── types.rs              # 统一 SecurityPlugin 协议（Rust 版）
    ├── pipeline.rs           # SecurityPipeline 编排器
    ├── loader.rs             # 配置加载 + 插件工厂
    ├── secured_tool.rs       # SecuredTool<T> trait wrapper
    └── plugins/
        ├── mod.rs
        └── policy_gate.rs    # 内置插件: 工具白/黑名单
```

## 注入方式

ZeroClaw 不支持运行时插件（compile-time safety 是其设计哲学），build-time 注入是正确方式。

### Dockerfile 多阶段构建

```dockerfile
FROM rust:bookworm as builder
ARG ZEROCLAW_VERSION=main

# 拉取 ZeroClaw 源码（不改）
RUN git clone --branch ${ZEROCLAW_VERSION} --depth 1 \
    https://github.com/zeroclaw-labs/zeroclaw.git /build/zeroclaw

# COPY 安全层 crate
COPY zeroclaw-security-layer/ /build/zeroclaw-security-layer/

# 安全层 crate 引用 zeroclaw 为 path dependency
WORKDIR /build/zeroclaw-security-layer
RUN cargo build --release

# 最终镜像
FROM debian:bookworm-slim
COPY --from=builder /build/zeroclaw-security-layer/target/release/zeroclaw-secured /opt/zeroclaw/zeroclaw
```

## 前提条件

- ZeroClaw 必须通过 `src/lib.rs` 暴露 `Tool` trait、`ToolResult` 类型和工具注册表工厂函数
- 如果 ZeroClaw 仅为 binary crate，需在 Dockerfile build stage 中创建 `lib.rs` 包装

## 配置

从 `/opt/zeroclaw/config/security-policy.json` 读取配置（路径可通过 `SECURITY_POLICY_PATH` 环境变量覆盖），JSON 格式与 OpenClaw/nanobot 安全层一致。
