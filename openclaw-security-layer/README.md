# OpenClaw Security Layer

OpenClaw 安全层 -- Thin WebSocket Client。通过原生 `before_tool_call` / `after_tool_call` Hook 拦截工具调用，经 WebSocket 转发至后端集中安全评估服务。

自身不包含任何安全逻辑（无插件、无策略引擎），所有安全能力由后端 `services/security/` 统一提供。

## 架构

```
Plugin Entry (index.ts)
  └── ws-client.ts (WebSocket 客户端)
        ├── evaluate_before → 后端 /api/v1/security/ws
        ├── (OpenClaw 原生执行)
        └── evaluate_after  → 后端 /api/v1/security/ws
```

## 目录结构

```
openclaw-security-layer/
├── index.ts                  # 插件入口，注册 before/after hook + kill switch
├── package.json
├── openclaw.plugin.json      # { "id": "security-layer" }
├── README.md
└── src/
    ├── types.ts              # BeforeResult / AfterResult / Finding 类型
    └── ws-client.ts          # WebSocket 客户端：连接管理、请求/响应匹配
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECURITY_LAYER_ENABLED` | 总开关，设为 `false` 关闭安全层 | `true` |
| `SECURITY_WS_ENDPOINT` | 后端 WebSocket 地址 | 取 `NODESKCLAW_BACKEND_URL` 替换协议头 |
| `NODESKCLAW_BACKEND_URL` | 后端地址（备选） | `ws://localhost:8000` |
| `NODESKCLAW_API_TOKEN` | 认证 Token | 空 |
| `AGENT_INSTANCE_ID` | 实例 ID，传入 context | 空 |
| `WORKSPACE_ID` | 工作区 ID，传入 context | 空 |

## 部署

由 NoDeskClaw 后端通过 `deploy_security_layer_plugin()` 部署到 OpenClaw 实例：

1. 文件 COPY 到 `/root/.openclaw/extensions/openclaw-security-layer/`
2. 更新 `openclaw.json` 的 `plugins.load.paths` 和 `plugins.entries`
