# Agent Device 实验 PRD

## 背景

DeskClaw 的办公室 Hex 已经可以放置 AI 员工、人类、黑板和过道。Agent Device 实验把外部可操作资源也作为办公室中的一类可放置对象，让 Agent 通过拓扑可达关系、显式授权、租约和审计来使用设备。

产品展示名约定：

| 场景 | 名称 |
| --- | --- |
| 中文 UI | 办公设施 |
| 英文 UI / 协议名 | Agent Device |

## 目标

1. 在办公室拓扑中放置受治理的设备节点，而不是把设备伪装成某个 Agent 的私有 Skill / MCP。
2. 先建立可扩展抽象，再用第一批内置预设验证；MVP 只预置 Browser Pilot。
3. Agent 通过 Controller 暴露的发现、可见性、授权、租约和调用接口使用设备。
4. 人类和 Agent 都可以参与设备治理；Agent 之间允许在授权链内自动委托权限。
5. 所有设备发现、授权、租约、调用和回收动作必须进入审计链路。

## 非目标

1. MVP 不做公开市场、第三方设备商店或用户自定义设备发布流程。
2. 不把设备身份、设备状态、授权、租约和审计下放给某个 Agent 私有 Skill / MCP。
3. 不在核心抽象里硬编码 Browser Pilot 的页面操作细节；Browser Pilot 只是第一个 Provider。
4. 不支持无拓扑直接本地访问设备；MVP 必须拓扑可达。后续保留 remote reachability 扩展口。

## 核心概念

| 概念 | 说明 |
| --- | --- |
| Agent Device / 办公设施 | 放置在办公室 Hex 上的受治理设备实例 |
| Device Preset | 内置设备预设，例如 `browser.bpilot.session` |
| Device Provider | 真正执行设备动作的适配器，例如 `browser.bpilot` |
| Device Grant | 授予某个 Agent 或 Human 的设备权限 |
| Device Lease | Agent 操作设备前必须获取的独占租约 |
| Agent Device Gene | 给 Agent 的操作说明和受控脚本入口，不拥有设备身份和治理状态 |
| Controller | 当前由 DeskClaw 后端承担，管理设备实例、拓扑可达、授权、租约、调用和审计 |

## Agent 如何发现和使用设备

Agent 不靠“自己装了某个 Skill”来判断设备存在，而是通过 Agent Device Gene 获得受控入口：

```bash
python3 ~/.deskclaw/tools/deskclaw_agent_device.py list_reachable
python3 ~/.deskclaw/tools/deskclaw_agent_device.py visibility --device-id <id>
python3 ~/.deskclaw/tools/deskclaw_agent_device.py acquire_lease --device-id <id>
python3 ~/.deskclaw/tools/deskclaw_agent_device.py invoke --device-id <id> --lease-id <lease> --provider-action page.goto --payload-json '{"url":"https://example.com"}'
python3 ~/.deskclaw/tools/deskclaw_agent_device.py release_lease --device-id <id> --lease-id <lease>
```

这些脚本只负责调用 Controller API。设备身份、设备状态、拓扑可达、授权、租约和审计都来自 Controller 返回的结构化结果。

Agent 可见一个设备需要同时满足：

1. 设备预设已启用。
2. Provider 状态可用。
3. Agent 在办公室拓扑中放置。
4. 办公室存在连接关系，且 Agent 到设备 Hex 拓扑可达。
5. Agent 持有 `discover` 授权。

Agent 使用设备需要进一步满足：

1. 持有 `lease` 授权并成功获取独占租约。
2. 持有 `invoke` 授权。
3. 调用时提交有效 `lease_id`。

## 权限模型

MVP 设备权限范围：

| Scope | 含义 |
| --- | --- |
| `discover` | 可以发现和读取可见性 |
| `lease` | 可以获取和续租设备 |
| `invoke` | 可以通过有效租约调用 Provider 动作 |
| `delegate` | 可以把自己拥有的部分权限委托给其他 Agent |

权限来源：

| 授予方 | 能力 |
| --- | --- |
| Human with `manage_devices` | 可以创建、撤销设备授权，回收任意活跃租约 |
| Agent with delegable grant | 可以把自己拥有的 scope 子集委托给其他 Agent |

Agent 委托规则：

1. Agent 只能委托给其他 Agent。
2. 子授权 scope 必须是父授权 scope 的子集。
3. 父授权必须包含 `delegate` 且 `can_delegate=true`。
4. 未显式设置过期时间时，Agent 委托默认短 TTL。
5. 子授权过期时间不能超过父授权。
6. Agent 只能回收自己持有的租约，或自己授权链下游 Agent 持有的租约。

## 人类如何参与治理

人类通过办公室 UI 管理办公设施：

1. 在空 Hex 放置内置设备预设。
2. 查看设备状态、Provider 状态、拓扑位置和可见性原因。
3. 给办公室中的 Agent 授权。
4. 撤销授权。
5. 回收活跃租约。
6. 移动、重命名或删除设备。

这些动作要求工作区成员权限中的 `manage_devices`；涉及 Hex 放置或移动时还要求 `edit_topology`。

## MVP 范围

后端：

1. 设备预设启停：`/workspaces/{workspace_id}/device-presets`
2. 设备实例 CRUD：`/workspaces/{workspace_id}/devices`
3. 设备授权：`/devices/{device_id}/grants`
4. 可达设备发现：`/reachable-devices`
5. 可见性检查：`/devices/{device_id}/visibility`
6. 租约获取、续租、释放、回收
7. Provider 调用：`/devices/{device_id}/invoke`
8. 操作审计记录 user / agent 两类 actor
9. 拓扑变化后同步 Agent Device Gene

前端：

1. 2D / 3D Hex 渲染设备节点。
2. 空 Hex 可放置办公设施。
3. 设备详情抽屉展示状态、可见性、租约和授权。
4. 支持重命名、移动、删除、授权和回收租约。

首个 Provider：

| 字段 | 值 |
| --- | --- |
| Preset | `browser.bpilot.session` |
| Provider | `browser.bpilot` |
| Gene | `agent-device-browser-bpilot` |
| Lease | exclusive |
| Actions | `session.create`, `session.use`, `page.goto`, `page.observe`, `page.click`, `page.type` |

## Remote 预留口

MVP 强制拓扑可达，`visibility.reachability_source` 当前为 `topology` 或空。后续如需要 remote access，应增加显式 remote grant / policy，而不是把无拓扑访问混入普通授权。

建议后续扩展：

1. `reachability_source=remote`
2. 独立 `remote` scope 或 policy flag
3. remote 授权必须有更短 TTL 和更明确审计原因
4. UI 明确标识“远程使用”，避免和拓扑可达混淆

## 待讨论

1. Human subject grant 是否要在 MVP 中开放，还是仅作为模型预留。
2. Agent 委托默认 TTL 是否固定 30 分钟，还是由工作区策略控制。
3. Provider 返回语义是否需要在 UI 中展示更细的“下一步建议”。
4. remote 入口是设备级策略、Agent 级策略，还是工作区级策略。
5. Browser Pilot Provider 的动作 schema 是否要在 Controller 层做白名单校验。
