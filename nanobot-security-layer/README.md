# nanobot Security Layer

nanobot 安全层 -- Thin WebSocket Client。通过 monkey-patch `ToolRegistry.execute` 拦截工具调用，经 WebSocket 转发至后端集中安全评估服务。

自身不包含任何安全逻辑（无插件、无策略引擎），所有安全能力由后端 `services/security/` 统一提供。

## 架构

```
startup.py (entrypoint wrapper)
  └── injector.py (monkey-patch ToolRegistry.execute)
        └── ws_client.py (WebSocket 客户端)
              ├── evaluate_before → 后端 /api/v1/security/ws
              ├── (原始 ToolRegistry.execute)
              └── evaluate_after  → 后端 /api/v1/security/ws
```

## 目录结构

```
nanobot-security-layer/
├── pyproject.toml
├── README.md
└── nanobot_security_layer/
    ├── __init__.py
    ├── types.py              # BeforeResult / AfterResult / Finding 类型
    ├── ws_client.py          # WebSocket 客户端：连接管理、请求/响应匹配
    ├── injector.py           # monkey-patch ToolRegistry.execute + kill switch
    └── startup.py            # Entrypoint wrapper: inject → start nanobot
```

## 注入方式

Dockerfile 修改：

```dockerfile
COPY nanobot-security-layer/ /opt/nanobot-security-layer/
RUN pip install --no-cache-dir /opt/nanobot-security-layer

CMD ["python", "-m", "nanobot_security_layer.startup", "gateway", "--config", "/opt/nanobot/nanobot.yaml"]
```

`startup.py` 在 nanobot CLI 启动前 monkey-patch `ToolRegistry.execute`，同一进程内生效。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SECURITY_LAYER_ENABLED` | 总开关，设为 `false` 关闭安全层 | `true` |
| `SECURITY_WS_ENDPOINT` | 后端 WebSocket 地址 | 取 `NODESKCLAW_BACKEND_URL` 替换协议头 |
| `NODESKCLAW_BACKEND_URL` | 后端地址（备选） | `ws://localhost:8000` |
| `NODESKCLAW_API_TOKEN` | 认证 Token | 空 |
| `AGENT_INSTANCE_ID` | 实例 ID，传入 context | 空 |
| `WORKSPACE_ID` | 工作区 ID，传入 context | 空 |
