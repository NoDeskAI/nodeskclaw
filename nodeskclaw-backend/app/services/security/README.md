# Security Service

集中式工具执行安全评估服务。运行时安全层（OpenClaw、nanobot、ZeroClaw）通过 WebSocket 连接到 `/api/v1/security/ws`，发送 `evaluate_before` / `evaluate_after` 请求，本服务运行注册的安全插件并返回结果。

## 架构

```
Runtime Security Layers (WebSocket Clients)
    ↕ WebSocket
/api/v1/security/ws (security_ws.py)
    ↓
SecurityPipeline (pipeline.py)
    ├── before_execute: plugin1 → plugin2 → ...
    └── after_execute:  plugin1 → plugin2 → ...
```

## 目录结构

```
services/security/
├── __init__.py               # 模块导出
├── types.py                  # ExecutionContext / BeforeResult / AfterResult / SecurityPlugin 协议
├── pipeline.py               # SecurityPipeline 编排器（零安全逻辑，纯调度）
├── loader.py                 # 插件发现与实例化
├── README.md
└── plugins/
    ├── __init__.py
    ├── policy_gate.py        # 工具白/黑名单、路径 ACL、命令黑名单
    ├── dlp_scanner.py        # 敏感数据检测与脱敏
    ├── audit_logger.py       # 操作审计记录
    └── approval_channel.py   # 人工审批流（集成 Trust Policy API）
```

## 插件接口

```python
class SecurityPlugin(Protocol):
    id: str
    priority: int

    async def initialize(self, config: dict) -> None: ...
    async def destroy(self) -> None: ...
    async def before_execute(self, ctx: ExecutionContext) -> BeforeResult: ...
    async def after_execute(self, ctx: ExecutionContext, result: ExecutionResult) -> AfterResult: ...
```

## WebSocket 消息协议

### 安全层 -> 后端

```json
{"type": "evaluate_before", "id": "r-1", "ctx": {"tool_name": "exec", "params": {...}, ...}}
{"type": "evaluate_after",  "id": "r-2", "ctx": {...}, "exec_result": {"result": "...", ...}}
```

### 后端 -> 安全层

```json
{"type": "result",  "id": "r-1", "result": {"action": "allow"}}
{"type": "pending", "id": "r-1", "decision_id": "d-xxx"}
{"type": "result",  "id": "r-1", "result": {"action": "deny", "reason": "...", "message": "..."}}
```
