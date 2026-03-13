# ZeroClaw Security Layer

ZeroClaw 安全层 -- Thin WebSocket Client。通过 `SecuredTool<T>` trait wrapper 拦截工具调用，经 WebSocket 转发至后端集中安全评估服务。

自身不包含任何安全逻辑（无插件、无策略引擎），所有安全能力由后端 `services/security/` 统一提供。

## 架构

```
SecuredTool<T: Tool>
  └── SecurityWsClient (WebSocket 客户端)
        ├── evaluate_before → 后端 /api/v1/security/ws
        ├── inner.execute(args) (原始工具执行)
        └── evaluate_after  → 后端 /api/v1/security/ws
```

## 目录结构

```
zeroclaw-security-layer/
├── Cargo.toml
├── README.md
└── src/
    ├── lib.rs               # 模块导出
    ├── types.rs              # BeforeResult / AfterResult / Finding + WS 消息类型
    ├── ws_client.rs          # WebSocket 客户端：连接管理、请求/响应匹配
    └── secured_tool.rs       # SecuredTool<T> trait wrapper + kill switch
```

## 注入方式

Dockerfile 多阶段构建：

```dockerfile
# Stage 1: 编译 ZeroClaw + security layer
FROM rust:1.82 AS builder
COPY zeroclaw/ /build/zeroclaw/
COPY zeroclaw-security-layer/ /build/zeroclaw-security-layer/
WORKDIR /build/zeroclaw
# 在 Cargo.toml 中注入 security-layer 依赖后编译
RUN cargo build --release

# Stage 2: 运行镜像
FROM debian:bookworm-slim
COPY --from=builder /build/zeroclaw/target/release/zeroclaw /usr/local/bin/
```

构建时通过 `Cargo.toml` path 依赖引入本 crate，在 ZeroClaw 的工具注册点用 `SecuredTool::new(tool, client)` 包装每个工具。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECURITY_LAYER_ENABLED` | 总开关，设为 `false` 关闭安全层 | `true` |
| `SECURITY_WS_ENDPOINT` | 后端 WebSocket 地址 | 取 `NODESKCLAW_BACKEND_URL` 替换协议头 |
| `NODESKCLAW_BACKEND_URL` | 后端地址（备选） | `ws://localhost:8000` |
| `NODESKCLAW_API_TOKEN` | 认证 Token | 空 |
| `AGENT_INSTANCE_ID` | 实例 ID，传入 context | 空 |
| `WORKSPACE_ID` | 工作区 ID，传入 context | 空 |
