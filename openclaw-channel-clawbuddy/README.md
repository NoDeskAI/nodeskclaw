# OpenClaw Channel Plugin: ClawBuddy

ClawBuddy 工作区 Agent 协同通信的 OpenClaw channel plugin。让 Agent 能通过 `send` 工具主动与工作区中的其他 Agent 协同。

## 用途

- 接入 OpenClaw 的 channel 系统，为 ClawBuddy 工作区提供 Agent 间通信能力
- Agent 可以使用 `send -t clawbuddy -to "agent:{name}" -m "消息"` 向其他 Agent 发送协同消息
- 通过 webhook 回调将消息路由到 ClawBuddy 后端进行处理和分发

## 目录结构

```
openclaw-channel-clawbuddy/
  package.json              # 包定义，声明 openclaw extensions 入口
  openclaw.plugin.json      # OpenClaw plugin manifest
  index.ts                  # Plugin 注册入口
  src/
    channel.ts              # ChannelPlugin 核心实现（outbound.sendText 使用 fetch）
    runtime.ts              # PluginRuntime wrapper
    types.ts                # TypeScript 类型定义
```

## 技术特点

- **零运行时依赖**: 仅使用 Node.js 22+ 全局 `fetch()` API，不依赖任何 npm 包
- **jiti 加载**: OpenClaw 通过 jiti 直接加载 `.ts` 源文件，无需编译
- **NFS 分发**: 通过 ClawBuddy 后端 NFS 挂载分发到各 OpenClaw 实例

## 配置

在 OpenClaw 实例的 `openclaw.json` 中配置：

```json
{
  "channels": {
    "clawbuddy": {
      "accounts": {
        "default": {
          "enabled": true,
          "callbackUrl": "https://api.clawbuddy.com/api/webhook/clawbuddy",
          "workspaceId": "ws_xxx",
          "instanceId": "inst_xxx",
          "apiToken": "shared_secret"
        }
      }
    }
  },
  "plugins": {
    "load": {
      "paths": [".openclaw/extensions/openclaw-channel-clawbuddy"]
    }
  }
}
```

## 使用方式

Agent 在对话中可以使用 `send` 工具与工作区中的其他 Agent 协同：

```
send -t clawbuddy -to "agent:researcher" -m "请帮我查一下这个问题的背景资料"
```
