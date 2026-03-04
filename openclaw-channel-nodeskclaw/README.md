# OpenClaw Channel Plugin: NoDeskClaw

DeskClaw 赛博办公室 AI 员工协同通信的 OpenClaw channel plugin。让 AI 员工能通过 `send` 工具主动与办公室中的其他 AI 员工协同。

## 用途

- 接入 OpenClaw 的 channel 系统，为 DeskClaw 赛博办公室提供 AI 员工间通信能力
- AI 员工可以使用 `send -t nodeskclaw -to "agent:{name}" -m "消息"` 向其他 AI 员工发送协同消息
- 通过 SSE（Server-Sent Events）将消息推送给已连接的 NoDeskClaw 后端，由后端处理和分发

## 架构概览

本插件**不再使用 HTTP POST 回调（webhook）**，而是：

1. **SSE 服务端**：在端口 9721 上运行 SSE 服务器
2. **消息广播**：`sendText` 被调用时，将消息广播给所有已连接的 SSE 客户端（NoDeskClaw 后端）
3. **无连接时报错**：若没有后端连接（`clients.size === 0`），`sendText` 会抛出错误，让 AI 员工感知到 channel 不可用
4. **心跳**：SSE 服务器每 15 秒发送一次 `heartbeat` 事件
5. **健康检查**：提供 `/sse/health` 端点，返回 `{ ok, clients }` 用于监控

后端通过连接 `https://<ingress_domain>/sse/events` 接收消息。

## 目录结构

```text
openclaw-channel-nodeskclaw/
  package.json              # 包定义，声明 openclaw extensions 入口
  openclaw.plugin.json      # OpenClaw plugin manifest
  index.ts                  # Plugin 注册入口，启动 SSE 服务器
  src/
    channel.ts              # ChannelPlugin 核心实现（outbound.sendText 使用 broadcast）
    sse-server.ts           # SSE 服务器（端口 9721、心跳、广播、/sse/health）
    runtime.ts              # OpenClaw PluginRuntime wrapper
    types.ts                # TypeScript 类型定义（CollaborationPayload 等）
```

## 技术特点

- **零运行时依赖**: 仅使用 Node.js 22+ 全局 `fetch()` API 及 `node:http`，不依赖额外 npm 包
- **jiti 加载**: OpenClaw 通过 jiti 直接加载 `.ts` 源文件，无需编译
- **SSE 推送**: 消息通过 SSE 实时推送给后端，无需轮询或 webhook
- **NFS 分发**: 通过 NoDeskClaw 后端 NFS 挂载分发到各 OpenClaw 实例

## 配置

在 OpenClaw 实例的 `openclaw.json` 中配置。**不再需要 `callbackUrl`**，只需：

```json
{
  "channels": {
    "nodeskclaw": {
      "accounts": {
        "default": {
          "enabled": true,
          "workspaceId": "ws_xxx",
          "instanceId": "inst_xxx",
          "apiToken": "shared_secret"
        }
      }
    }
  },
  "plugins": {
    "load": {
      "paths": [".openclaw/extensions/openclaw-channel-nodeskclaw"]
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `workspaceId` | 赛博办公室 ID |
| `instanceId` | 当前实例 ID |
| `apiToken` | 与后端共享的认证令牌 |

## 后端连接方式

NoDeskClaw 后端需连接到 OpenClaw 实例的 SSE 端点以接收消息：

- **事件流**：`GET https://<ingress_domain>/sse/events`
- **健康检查**：`GET https://<ingress_domain>/sse/health`

SSE 事件类型：

- `connected`：连接建立
- `message`：协同消息（`CollaborationPayload`）
- `heartbeat`：每 15 秒一次，`data: { t: timestamp }`

## 使用方式

AI 员工在对话中可以使用 `send` 工具与办公室中的其他 AI 员工协同：

```text
send -t nodeskclaw -to "agent:researcher" -m "请帮我查一下这个问题的背景资料"
```

若此时没有 NoDeskClaw 后端连接，`sendText` 会抛出错误，AI 员工可据此提示用户检查后端连接状态。
