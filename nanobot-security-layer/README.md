# nanobot Security Layer

nanobot 工具执行安全流水线。通过 monkey-patch `ToolRegistry.execute` 拦截所有 tool 调用，运行可插拔的安全检查流水线。

## 架构

```
startup.py (entrypoint wrapper)
  └── injector.py (monkey-patch ToolRegistry.execute)
        └── SecurityPipeline
              ├── Before Phase: policy-gate → approval-channel → ...
              ├── Around Phase: (原始 ToolRegistry.execute)
              └── After Phase: dlp-scanner → audit-logger → ...
```

Pipeline Core 零安全逻辑，所有安全能力由 SecurityPlugin 插件提供。

## 目录结构

```
nanobot-security-layer/
├── pyproject.toml
├── README.md
└── nanobot_security_layer/
    ├── __init__.py
    ├── types.py              # 统一 SecurityPlugin 协议（Python 版）
    ├── pipeline.py           # Pipeline 编排器
    ├── loader.py             # 配置加载 + 插件工厂
    ├── injector.py           # monkey-patch ToolRegistry.execute
    ├── startup.py            # Entrypoint wrapper: inject → start nanobot
    └── plugins/
        ├── __init__.py
        └── policy_gate.py    # 内置插件: 工具白/黑名单、路径 ACL、命令黑名单
```

## 注入方式

Dockerfile 修改：

```dockerfile
COPY nanobot-security-layer/ /opt/nanobot-security-layer/
RUN pip install --no-cache-dir /opt/nanobot-security-layer

CMD ["python", "-m", "nanobot_security_layer.startup", "gateway", "--config", "/opt/nanobot/nanobot.yaml"]
```

`startup.py` 在 nanobot CLI 启动前 monkey-patch `ToolRegistry.execute`，同一进程内生效。

## 配置

从 `/opt/nanobot/config/security-policy.json` 读取配置（路径可通过 `SECURITY_POLICY_PATH` 环境变量覆盖），JSON 格式与 OpenClaw 安全层一致。
