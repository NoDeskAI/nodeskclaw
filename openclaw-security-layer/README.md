# OpenClaw Security Layer

OpenClaw 工具执行安全流水线插件。通过原生 `before_tool_call` / `after_tool_call` Hook 拦截所有 tool 调用，运行可插拔的安全检查流水线。

## 架构

```
Plugin Entry (index.ts)
  └── SecurityPipeline
        ├── Before Phase: policy-gate → approval-channel → ...
        ├── Around Phase: (OpenClaw 原生执行)
        └── After Phase: dlp-scanner → audit-logger → ...
```

Pipeline Core 零安全逻辑，所有安全能力由 SecurityPlugin 插件提供。

## 目录结构

```
openclaw-security-layer/
├── index.ts                  # 插件入口，注册 before/after hook
├── package.json
├── openclaw.plugin.json      # { "id": "security-layer" }
├── README.md
└── src/
    ├── types.ts              # 统一 SecurityPlugin 协议
    ├── pipeline.ts           # Pipeline 编排器
    ├── loader.ts             # 配置加载 + 插件工厂
    └── plugins/
        └── policy-gate.ts    # 内置插件: 工具白/黑名单、路径 ACL、命令黑名单
```

## 配置

安全层从 `/root/.openclaw/config/security-policy.json` 读取配置：

```json
{
  "plugins": [
    {
      "id": "policy-gate",
      "enabled": true,
      "priority": 10,
      "config": {
        "mode": "monitor",
        "tools": {
          "exec": { "denied_commands": ["^sudo\\b"] },
          "read_file": { "denied_paths": ["**/.env"] }
        }
      }
    }
  ]
}
```

## 部署

由 NoDeskClaw 后端通过 `deploy_security_layer_plugin()` 部署到 OpenClaw 实例：

1. 文件 COPY 到 `/root/.openclaw/extensions/openclaw-security-layer/`
2. 更新 `openclaw.json` 的 `plugins.load.paths` 和 `plugins.entries`
3. 策略 JSON 写入 `/root/.openclaw/config/security-policy.json`
