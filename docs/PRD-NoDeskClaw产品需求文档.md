# NoDeskClaw - 产品需求文档（PRD）

> 创建时间：2026年2月10日
> 文档版本：v0.4
> 文档状态：草稿，持续迭代中
> UI 设计参考：[Vibecraft](https://vibecraft.sh/)（[GitHub](https://github.com/Nearcyan/vibecraft)）

---

## 一、项目概述

**NoDeskClaw** 是一个 K8s 可视化管理控制台，通过简洁直观的 Web 界面，让公司成员无需 K8s 操作经验，即可一键部署和管理 OpenClaw（AI Agent 平台）。

---

## 二、背景与目标

### 2.1 背景

OpenClaw 是一个强大的 AI Agent 平台，但部署和运维需要一定的 K8s 技术门槛，包括编写 YAML、执行 kubectl 命令、排查 Pod 异常等。为了让公司所有成员都能便捷使用，需要提供可视化的部署和管理界面。

### 2.2 目标用户

公司全体成员，特别是没有 K8s 操作经验的同学。

### 2.3 核心目标

| 目标 | 描述 |
|------|------|
| 降低门槛 | 让没有 K8s 经验的同学也能一键部署和管理 OpenClaw |
| 提升效率 | 从手动部署 30 分钟缩短到页面操作 3 分钟 |
| 减少故障 | 通过表单校验和预检机制，减少人为配置错误 |
| 统一管理 | 提供集中的管理视角，了解所有 OpenClaw 实例的状态 |

### 2.4 支持的云服务商

- **M1 阶段**：火山云 VKE（Volcengine Kubernetes Engine）
- **后续扩展**：架构上预留 Cloud Provider 抽象接口，方便未来接入 ACK/TKE 等

---

## 三、功能需求

### 3.1 集群管理

#### 3.1.1 集群接入

- 通过 KubeConfig 文件导入集群
- 支持火山云 VKE API Token 方式接入
- 集群连接状态检测（连接测试）

#### 3.1.2 集群概览

- 集群基本信息（名称、版本、节点数）
- 节点状态一览（Ready/NotReady）
- 资源概况（CPU/内存 总量与已分配量）

#### 3.1.3 集群健康监测

- 后台每 60 秒自动巡检集群连接状态
- Token 即将过期（< 6h）时弹出黄色告警提示用户更新 KubeConfig
- Token 已过期时阻止操作并弹出红色告警
- 集群连接不可用时自动标记为 unhealthy 并通知
- 支持重新上传 KubeConfig 更新认证凭证

#### 3.1.4 多集群（M3 阶段）

- 多集群列表管理（添加/编辑/删除）
- 集群间切换

### 3.2 一键部署 OpenClaw

#### 3.2.1 部署表单

通过可视化表单创建 OpenClaw 实例，配置项包括：

| 配置项 | 说明 | 是否必填 |
|--------|------|----------|
| 实例名称 | 用于标识此次部署，需唯一，自动生成 Namespace `oc-{name}` | 是 |
| 镜像版本 | 下拉选择可用版本（从 Registry 拉取列表） | 是 |
| 副本数 | 固定 1（因 PVC 挂载 `/root` 为 ReadWriteOnce，不支持多副本共享） | 是 |
| CPU 配额 | Request / Limit，默认 0.5c / 1c | 是 |
| 内存配额 | Request = Limit（避免 OOM），默认 2Gi / 2Gi | 是 |
| **Namespace 资源配额** | 预设档位：小型(2c/4Gi)、中型(4c/8Gi)、大型(8c/16Gi)、自定义 | 是 |
| 存储空间 | 实例持久化磁盘大小，默认 100Gi，挂载到 `/root`（覆盖整个 home 目录） | 是 |
| 插件配置 | 默认插件参数（作为环境变量注入，按需扩展） | 否 |
| 服务暴露方式 | ClusterIP / NodePort / LoadBalancer | 是 |
| 域名配置 | 若选择 LoadBalancer，可配置 Ingress 域名 | 否 |
| 环境变量 | 自定义键值对，注入到 Pod 中 | 否 |

> **隔离说明**：每个实例自动创建独立 Namespace，并配置 ResourceQuota（资源上限）+ LimitRange（容器默认限制）+ NetworkPolicy（网络隔离，禁止跨实例访问）。
>
> **存储说明**：每个实例自动创建 PVC 挂载到 `/root`，通过 Init Container 在首次部署时将 `.openclaw/` 用户数据目录初始化到 PVC。程序文件（Node.js + OpenClaw）在镜像层的系统目录中，换镜像即升级。Pod 重启/调度时用户数据不丢失。

#### 3.2.2 部署预检

在实际创建资源前，执行预检：

- 集群连接是否正常
- Namespace 是否存在（不存在则自动创建）
- 集群剩余资源是否满足配额要求
- 镜像是否可拉取

#### 3.2.3 部署执行

- 通过 kubernetes-asyncio 直接创建 OpenClaw 的 ConfigMap + Deployment + Service + Ingress
- 部署进度实时展示（Creating → Pending → Running）
- 部署失败时展示错误原因及建议操作

### 3.3 实例管理（配置管理）

#### 3.3.1 实例列表

- 展示所有已部署的 OpenClaw 实例
- 关键信息：名称、命名空间、状态、版本、副本数、创建时间

#### 3.3.2 实例操作

| 操作 | 说明 |
|------|------|
| 查看详情 | 展示完整的部署配置和运行状态 |
| 修改配置 | 修改副本数、资源配额、环境变量等 |
| 滚动更新 | 更新镜像版本，支持滚动发布 |
| 重启 | 重启所有 Pod（rollout restart） |
| 扩缩容 | 快捷调整副本数 |
| 删除 | 删除整个 OpenClaw 实例（二次确认） |
| 高级配置 | 进入高级配置面板（见 3.3.3） |

#### 3.3.3 高级配置（M2 阶段）

对已部署的实例进行进阶运维配置：

| 功能 | 说明 |
|------|------|
| 挂载 Volume | 支持 emptyDir / PVC / ConfigMap / Secret 四种类型，指定挂载路径和存储大小 |
| 添加 Sidecar 容器 | 为实例 Pod 注入额外容器（如日志收集、代理） |
| 添加 Init 容器 | 为实例 Pod 注入初始化容器（如数据迁移、依赖检查） |
| 跨实例网络打通 | 允许指定实例之间的网络通信（默认隔离），可限定端口和方向 |
| 自定义标签/注解 | 为 Pod 添加自定义 K8s labels 和 annotations |

操作流程：**先保存到 DB → 再手动 Apply 到 K8s**（两步操作，防止误修改直接生效）。

### 3.4 日志查看

#### 3.4.1 实时日志

- 基于 SSE 的实时日志流
- 支持选择具体 Pod / Container
- 自动滚动 + 手动暂停

#### 3.4.2 日志工具

- 关键字搜索 / 高亮
- 日志级别过滤（INFO / WARN / ERROR）
- 时间范围筛选
- 日志下载（导出为文本文件）

### 3.5 监控面板

#### 3.5.1 Pod 监控

- Pod 列表与运行状态（Running / Pending / Failed / CrashLoopBackOff）
- 单 Pod 资源使用曲线（CPU / 内存，需要 Metrics Server）
- Pod 重启次数与历史

#### 3.5.2 部署历史

- 部署版本记录（Revision 列表）
- 版本对比（配置 Diff）
- 一键回滚到指定版本

#### 3.5.3 事件查看

- K8s Events 列表
- 按类型过滤（Normal / Warning）
- 事件时间线展示

### 3.6 系统功能

#### 3.6.1 用户认证

- **M1 阶段**：飞书 SSO 单点登录
- 登录态管理（JWT Token）

#### 3.6.2 权限控制（M3 阶段）

- 角色：管理员 / 普通用户
- 管理员：全部操作权限
- 普通用户：仅能管理自己创建的实例，不能操作集群配置

#### 3.6.3 操作审计（M3 阶段）

- 记录所有操作行为（谁/什么时间/做了什么）
- 审计日志查询

#### 3.6.4 通知告警（M3 阶段）

- 部署失败通知（飞书消息推送）
- Pod 异常告警（CrashLoopBackOff、OOMKilled）

### 3.7 大模型 Key 管理

OpenClaw 需要大模型 API Key 才能正常使用。NoDeskClaw 提供集中化的 Key 管理和代理转发，用户无需直接接触真实 Key。

#### 3.7.1 组织 Key（管理员配置）

- 管理员为组织创建 LLM Key，同一 Provider（如 OpenAI）可配多个 Key，通过标签区分（如"市场部 Key"、"研发主号"）
- 每个 Key 支持双重 token 额度限制（用完即止）：
  - 组织级额度：管理员设定该 Key 在本组织的总 token 上限
  - 系统级额度：平台管理员设定的硬性上限
- 成员可在可选列表中看到组织 Key 的标签和脱敏值，但看不到完整 Key

#### 3.7.2 用户个人 Key

- 用户可添加自己的 LLM API Key（每个 Provider 一个）
- 个人 Key 不受组织额度限制，用户自行管理自己的账单

#### 3.7.3 Key 选择机制

- 每个用户在每个组织中，按 Provider 粒度选择使用哪个 Key（组织 Key 或个人 Key）
- Key 选择是用户级别设置，变更会影响该用户在同一组织下的所有实例
- 切换已有 Provider 的 Key 来源不需要重启实例（代理端动态解析）
- 新增/移除 Provider 需要重启 OpenClaw 进程（优雅重启，等待当前任务完成）

#### 3.7.4 LLM 代理架构

- NoDeskClaw 后端作为 LLM 代理，OpenClaw 实例的 LLM 请求全部经过代理转发
- OpenClaw 不持有真实 API Key，只持有代理 token（复用 Gateway Token）
- 代理负责：鉴权、Key 解析、额度检查、流式转发、token 用量记录
- 使用组织 Key 时自动注入 stream_options 以精确计算 token 消耗

#### 3.7.5 配置时机

- 创建实例时：始终可见的"配置大模型"区块，用户可选择配置或跳过
- 模型配置页：创建后随时可在实例的模型配置中管理 LLM 配置

---

## 四、UI 设计规范

> 参考 Vibecraft 源码（`src/styles/`、`docs/DESIGN.md`）提取的设计规范，适配 K8s 管理后台场景。

### 4.1 设计原则（源自 Vibecraft DESIGN.md）

| 原则 | 说明 |
|------|------|
| 即时反馈 | 每一次交互都需要有视觉、动效或状态变化作为反馈 |
| 悬停明确 | 所有可点击元素必须有 hover 反馈效果 |
| 层次分明 | 通过透明度和亮度区分背景、表面、前景层级 |
| 状态可见 | 系统状态（连接、部署进度、Pod 健康）始终可见 |
| 节奏感 | 即时响应 0-50ms、快速过渡 100-200ms、明显动效 300-800ms |

### 4.2 配色方案（提取自 Vibecraft 源码）

#### 4.2.1 背景色阶

| 层级 | 色值 | 用途 |
|------|------|------|
| 底层背景 | `#0a0a0a` | body / 主背景 |
| 面板背景 | `#111111` | 侧边栏、内容面板 |
| 卡片/表面 | `#1a1a1a` | 卡片、模态框、下拉菜单 |
| 高亮表面 | `#1e293b` | 选中状态、hover 背景 |
| 上下文菜单 | `rgba(20, 20, 25, 0.95)` | 右键菜单、弹出层 |

#### 4.2.2 强调色

| 角色 | 色值 | 用途 |
|------|------|------|
| 主强调色 | `#a78bfa` | 品牌色、主操作按钮、Focus 边框 |
| 主强调浅 | `#c4b5fd` | hover 高亮、二级强调 |
| 主强调透明 | `rgba(167, 139, 250, 0.2)` | Focus box-shadow、active 背景 |
| 信息色 | `#22d3ee` | 信息提示、链接、滑块 |
| 蓝色辅助 | `#60a5fa` / `#3b82f6` | 图标、次要链接 |

#### 4.2.3 语义色 / 状态色

| 语义 | 色值 | Glow 效果 | 对应状态 |
|------|------|-----------|----------|
| 成功/健康 | `#4ade80` | `box-shadow: 0 0 8px #4ade80` | Running、Connected、Deploy 成功 |
| 警告/进行中 | `#fbbf24` | `box-shadow: 0 0 8px #fbbf24` | Pending、Working、Scaling |
| 错误/异常 | `#f87171` / `#ef4444` | `box-shadow: 0 0 8px #ef4444` | Failed、CrashLoopBackOff、Error |
| 信息 | `#22d3ee` | `box-shadow: 0 0 8px #22d3ee` | Info、提示 |

#### 4.2.4 文字色阶

| 层级 | 色值 | 用途 |
|------|------|------|
| 主文字 | `#ffffff` | 标题、重要信息 |
| 次要文字 | `rgba(255, 255, 255, 0.7)` | 描述、副文本 |
| 辅助文字 | `rgba(255, 255, 255, 0.4)` | Placeholder、禁用态 |
| 中性灰 | `#9ca3af` | 标签、时间戳 |

### 4.3 字体规范

| 用途 | 字体栈 | 字号范围 |
|------|--------|----------|
| UI 正文 | `system-ui, -apple-system, sans-serif` | 12-14px |
| 标题 | `system-ui, -apple-system, sans-serif` | 14-24px |
| 日志/代码/终端 | `'SF Mono', Monaco, 'Cascadia Code', monospace` | 12-13px |
| 数据/指标 | `ui-monospace, SFMono-Regular, monospace` | 14-20px |

### 4.4 组件样式规范（Vibecraft 模式）

#### 4.4.1 卡片（实例卡片、状态卡片）

```css
/* 基础卡片 */
background: rgba(255, 255, 255, 0.03);
border: 1px solid rgba(255, 255, 255, 0.08);
border-radius: 6px;
padding: 10px 12px;
transition: all 0.15s ease;

/* Hover 态 */
background: rgba(255, 255, 255, 0.06);
border-color: rgba(255, 255, 255, 0.15);

/* 状态边框色 - 左边框 3px 指示状态 */
border-left: 3px solid #4ade80;  /* Running */
border-left: 3px solid #fbbf24;  /* Pending */
border-left: 3px solid #f87171;  /* Failed */

/* 入场动画 */
animation: fadeIn 0.2s ease-out;
```

#### 4.4.2 按钮

```css
/* 默认按钮 */
background: rgba(255, 255, 255, 0.05);
border: 1px solid rgba(255, 255, 255, 0.1);
border-radius: 6px;
color: #fff;
transition: all 0.15s ease;

/* Hover */
background: rgba(255, 255, 255, 0.1);

/* 主操作按钮（部署/确认） */
background: rgba(167, 139, 250, 0.2);
border-color: rgba(167, 139, 250, 0.4);

/* 危险按钮（删除） */
background: rgba(248, 113, 113, 0.15);
border-color: rgba(248, 113, 113, 0.3);

/* 成功按钮（启动） */
background: rgba(74, 222, 128, 0.2);
border-color: rgba(74, 222, 128, 0.3);
```

#### 4.4.3 输入框 / 表单

```css
/* 输入框 */
background: rgba(255, 255, 255, 0.06);
border: 1px solid rgba(255, 255, 255, 0.12);
border-radius: 8px;
color: #fff;
transition: border-color 0.15s, box-shadow 0.15s;

/* Focus 态 - 紫色发光 */
border-color: #a78bfa;
box-shadow: 0 0 0 3px rgba(167, 139, 250, 0.2);

/* Placeholder */
color: rgba(255, 255, 255, 0.35);
```

#### 4.4.4 模态框

```css
/* 遮罩层 */
background: rgba(0, 0, 0, 0.75);
backdrop-filter: blur(4px);

/* 模态框本体 */
background: #1a1a1a;
border: 1px solid rgba(255, 255, 255, 0.15);
border-radius: 12px;
box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
max-width: 90vw;
```

#### 4.4.5 Toast 通知

```css
/* 容器 */
max-width: 400px;
background: rgba(0, 0, 0, 0.9);
backdrop-filter: blur(8px);
border-radius: 8px;

/* 入场动画 */
animation: toast-in 0.2s ease-out;

/* 退场动画 */
animation: toast-out 0.2s ease-in;
```

Toast 类型与对应颜色：

| 类型 | 左边框色 | 图标 |
|------|----------|------|
| `info` | `#22d3ee` | ℹ️ |
| `success` | `#4ade80` | ✓ |
| `warning` | `#fbbf24` | ⚠ |
| `error` | `#f87171` | ✗ |

#### 4.4.6 状态指示灯（Glow Dot）

```css
/* 状态圆点 - 参考 Vibecraft 连接状态实现 */
width: 8px;
height: 8px;
border-radius: 50%;
/* Running / Connected */
background: #4ade80;
box-shadow: 0 0 8px #4ade80;
/* Pending / Working */
background: #fbbf24;
box-shadow: 0 0 8px #fbbf24;
animation: pulse 2s infinite;
/* Error / Disconnected */
background: #f87171;
box-shadow: 0 0 8px #f87171;
```

#### 4.4.7 滚动条

```css
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 3px;
}
```

### 4.5 视觉效果

#### 4.5.1 毛玻璃（Glassmorphism）

参考 Vibecraft 的 HUD、Draw Mode、Toast 等组件：

```css
/* 标准玻璃态 */
background: rgba(0, 0, 0, 0.7);
backdrop-filter: blur(8px);

/* 重度玻璃态（命令面板等） */
background: rgba(15, 20, 30, 0.95);
backdrop-filter: blur(20px);
```

应用场景：顶栏、底部状态栏、弹出面板、Toast、命令面板。

#### 4.5.2 Glow 发光效果

```css
/* 状态指示灯 */
box-shadow: 0 0 8px <状态色>;

/* 选中元素强调 */
box-shadow: 0 0 12px rgba(167, 139, 250, 0.5);

/* 告警强调 */
box-shadow: 0 0 10px rgba(239, 68, 68, 0.8),
            0 0 20px rgba(239, 68, 68, 0.4);
```

#### 4.5.3 动画库（Keyframes）

从 Vibecraft 源码提取，适配 NoDeskClaw 场景：

```css
/* 通用淡入 - 卡片、列表项 */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* 呼吸脉冲 - 状态指示灯、Pending 状态 */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.5; }
}

/* Toast 入场 */
@keyframes toast-in {
  from { opacity: 0; transform: translateY(20px) scale(0.95); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* Toast 退场 */
@keyframes toast-out {
  from { opacity: 1; transform: translateY(0) scale(1); }
  to   { opacity: 0; transform: translateY(-10px) scale(0.95); }
}

/* 思考中 / 加载中 - 部署进度 */
@keyframes thinking-pulse {
  0%, 100% { transform: scale(1); opacity: 0.7; }
  50%      { transform: scale(1.05); opacity: 1; }
}

/* 错误抖动 - 部署失败、校验错误 */
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25%      { transform: translateX(-4px); }
  75%      { transform: translateX(4px); }
}

/* 旋转 - Loading spinner */
@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

/* 注意力脉冲 - 需关注的实例/告警 */
@keyframes attention-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(167, 139, 250, 0); }
  50%      { box-shadow: 0 0 0 8px rgba(167, 139, 250, 0.3); }
}
```

### 4.6 布局结构

```
┌──────────────────────────────────────────────────────────────────┐
│  顶栏 (Glassmorphism: rgba(0,0,0,0.7) + blur(8px))              │
│  [Logo] [集群选择器 ▾] [──── 全局搜索 ────] [通知🔔] [头像]     │
├────────────┬─────────────────────────────────────────────────────┤
│            │                                                     │
│  侧边导航   │              主内容区域                              │
│  #111      │              #0a0a0a                                │
│            │                                                     │
│  ┌──────┐  │  ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │🏠 总览│  │  │ 实例总数  │ │ Running  │ │ CPU 占用  │          │
│  │📦 实例│  │  │  12      │ │  10      │ │  68%     │          │
│  │🚀 部署│  │  └──────────┘ └──────────┘ └──────────┘           │
│  │📋 日志│  │                                                    │
│  │📊 监控│  │  ┌─────────────────────────────────────────┐      │
│  │⚙️ 集群│  │  │                                         │      │
│  │🔧 设置│  │  │        主要内容（表格/卡片/图表）          │      │
│  │      │  │  │                                         │      │
│  │      │  │  └─────────────────────────────────────────┘      │
│  │      │  │                                                    │
│  │      │  │  ┌─────────────────────────────┐                   │
│  │      │  │  │  Activity Feed (可折叠)       │                  │
│  │      │  │  │  • 10:32 instance-1 Running  │                  │
│  │      │  │  │  • 10:31 instance-2 Scaling  │                  │
│  │      │  │  └─────────────────────────────┘                   │
├────────────┴─────────────────────────────────────────────────────┤
│  底栏：🟢 集群已连接  |  🟢 SSE 连接正常  |  v0.1.0               │
└──────────────────────────────────────────────────────────────────┘
```

### 4.7 关键页面设计

#### 4.7.1 Dashboard（总览）

- 顶部：4 个统计指标卡片（总实例数、Running 数、告警数、资源占用），卡片带 `fadeIn` 入场动画
- 中部左：实例状态网格（卡片视图），每张卡片左边框带状态色 + Glow
- 中部右：资源使用环形图（ECharts dark theme）
- 底部：实时 Activity Feed 时间线，新事件 `fadeIn` 滑入，参考 Vibecraft 的 FeedManager

#### 4.7.2 一键部署

- 分步表单（Stepper）：基本信息 → 资源配额 → 网络配置 → 环境变量 → 预检确认
- 每步右侧实时预览生成的 YAML（代码区域用等宽字体 + 深色背景）
- 预检阶段：逐项打勾动画（✓ 绿色淡入）
- 部署中：进度条 + 状态流转动画（Creating → Pending → Running），参考 Vibecraft 的 `thinking-pulse` 效果
- 部署完成：成功动画（绿色 Glow 扩散）；失败：`shake` 抖动 + 红色提示

#### 4.7.3 实例列表

- 默认卡片视图，可切换表格视图（shadcn-vue Data Table）
- 卡片内容：实例名、命名空间、版本号、Pod 状态指示灯（Glow Dot）、副本数、运行时长
- 快捷操作浮层：hover 显示（重启、扩容、日志），参考 Vibecraft 的右键菜单样式
- 搜索/过滤：顶部 filter bar

#### 4.7.4 日志查看

- 全屏深色终端风格（`#0a0a0a` 背景）
- 等宽字体 `'SF Mono', Monaco, monospace`，12px
- 日志级别颜色：INFO `#9ca3af`、WARN `#fbbf24`、ERROR `#f87171`
- 左侧 Pod/Container 选择面板
- 顶部工具栏：搜索框、级别过滤、暂停/恢复、下载
- 新日志行 `fadeIn` 效果，自动滚动到底部
- 参考 Vibecraft 终端面板的实现（`max-height: 300px` 可滚动区域）

#### 4.7.5 监控面板

- 深色 ECharts 图表（参考 Grafana Dark 风格）
- Pod 状态矩阵（参考 Vibecraft 会话网格 `grid-template-columns: repeat(auto-fill, minmax(140px, 1fr))`）
- 资源曲线：CPU/内存实时折线图，数据点带发光效果
- 事件时间线：参考 Vibecraft 的 TimelineManager

---

## 五、技术方案

### 5.1 整体架构

```
┌───────────────────────────────────────────────────────────────┐
│                       用户浏览器                                │
│         Vue 3 + TypeScript + shadcn-vue + Tailwind CSS        │
│            (Dark Theme · Vibecraft-inspired UI)               │
│                                                               │
│   ┌────────────┐  ┌────────────┐  ┌──────────────────────┐  │
│   │ EventBus   │  │   Pinia    │  │  SSE Client          │  │
│   │ (Pub/Sub)  │  │  (State)   │  │  (实时数据)           │  │
│   └──────┬─────┘  └──────┬─────┘  └──────────┬───────────┘  │
│          │               │                    │               │
│   ┌──────▼───────────────▼────────────────────▼───────────┐  │
│   │              API Service Layer                         │  │
│   │   REST (axios) + SSE (fetch-event-source)              │  │
│   └──────────────────────┬────────────────────────────────┘  │
└──────────────────────────┼────────────────────────────────────┘
                           │ HTTPS + SSE
┌──────────────────────────▼────────────────────────────────────┐
│                   Ingress / LoadBalancer                        │
└──────────────────────────┬────────────────────────────────────┘
                           │
┌──────────────────────────▼────────────────────────────────────┐
│                   NoDeskClaw Backend                             │
│                Python 3.12 + FastAPI + Uvicorn                 │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │                    API Layer (Routers)                     │ │
│  │  /api/clusters  /api/deployments  /api/logs  /api/auth   │ │
│  └──────────┬───────────────┬──────────────┬────────────────┘ │
│             │               │              │                   │
│  ┌──────────▼───────────────▼──────────────▼────────────────┐ │
│  │              Service Layer (业务逻辑)                      │ │
│  │  ClusterService  DeployService  LogService  AuthService  │ │
│  └──────────┬───────────────┬──────────────┬────────────────┘ │
│             │               │              │                   │
│  ┌──────────▼───┐ ┌────────▼────┐ ┌───────▼──────────────┐  │
│  │ K8s Client   │ │ResourceBldr│ │  EventBroadcaster    │  │
│  │ (k8s-asyncio)│ │(资源构建器) │ │  (SSE EventBus)      │  │
│  └──────────┬───┘ └────────┬────┘ └───────┬──────────────┘  │
│             │               │              │                   │
│  ┌──────────▼───────────────▼──────────────▼────────────────┐ │
│  │           PostgreSQL (火山云 RDS，配置 & 记录)              │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────┬────────────────────────────────────┘
                           │ KubeConfig / ServiceAccount
┌──────────────────────────▼────────────────────────────────────┐
│                   K8s Cluster (火山云 VKE)                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                    │
│  │OpenClaw-1│  │OpenClaw-2│  │OpenClaw-N│                    │
│  └──────────┘  └──────────┘  └──────────┘                    │
└───────────────────────────────────────────────────────────────┘
```

### 5.2 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 前端框架 | Vue 3 + TypeScript (Composition API) | `<script setup lang="ts">` 语法，响应式系统成熟 |
| UI 组件库 | shadcn-vue + Tailwind CSS | 50+ 可定制组件，Data Table / Form 内置，暗色主题原生支持 |
| 前端构建 | Vite 6 | 参考 Vibecraft 同款构建工具，HMR 快速 |
| 状态管理 | Pinia | Vue 官方状态管理，Composition API 风格，轻量简洁 |
| 路由 | Vue Router 4 | Vue 官方路由，支持嵌套路由、导航守卫 |
| 图表 | ECharts (dark theme) | 监控面板图表渲染 |
| 后端框架 | Python 3.12 + FastAPI | 异步支持好，自带 OpenAPI 文档，开发效率高 |
| K8s 交互 | kubernetes-asyncio (原生 async K8s Client) | 原生异步，完美配合 FastAPI，Watch/Stream 天然支持 |
| 实时通信 | SSE (Server-Sent Events) | 日志流、部署状态推送、事件实时推送（单向推送，比 WebSocket 更简单） |
| ORM | SQLAlchemy 2.0 + Alembic | 异步 ORM + 数据库迁移 |
| 数据存储 | PostgreSQL（火山云 RDS） | 存储集群配置、部署记录、审计日志 |
| 认证 | 飞书 SSO + JWT (python-jose) | 企业内部统一认证 |
| 任务队列 | 内置 asyncio（M1）→ Celery（M3） | 异步部署任务、定时巡检 |
| 资源构建 | kubernetes-asyncio 直接创建 K8s 对象 | 无需 Helm，Python 代码即配置 |

### 5.3 前端架构设计（参考 Vibecraft 模式）

#### 5.3.1 事件驱动架构（EventBus）

参考 Vibecraft 的 `EventBus`（发布/订阅模式），NoDeskClaw 前端也采用 EventBus 解耦 UI 组件与业务逻辑：

```typescript
// 事件类型定义
type EventType =
  | 'deploy:started'      // 部署开始
  | 'deploy:progress'     // 部署进度更新
  | 'deploy:completed'    // 部署完成
  | 'deploy:failed'       // 部署失败
  | 'instance:status'     // 实例状态变更
  | 'pod:event'           // Pod 事件
  | 'cluster:connected'   // 集群连接成功
  | 'cluster:disconnected' // 集群断开
  | 'log:new'             // 新日志行

// 使用
eventBus.on('deploy:progress', (data) => { ... })
eventBus.emit('deploy:started', { instanceId, config })
```

#### 5.3.2 SSE 实时推送

采用 SSE (Server-Sent Events) 而非 WebSocket —— 所有实时场景都是服务端单向推送，客户端命令走 REST。SSE 更简单、自动重连、HTTP 原生、负载均衡零配置。

**SSE 流端点：**

| 端点 | 用途 |
|------|------|
| `GET /stream/instances/:id/status` | 实例状态 + Pod 变更 |
| `GET /stream/instances/:id/events` | K8s 事件流 |
| `GET /stream/instances/:id/logs` | Pod 实时日志（`?pod=xx&container=xx&tail=100`） |
| `GET /stream/deploy/:deploy_id/progress` | 部署进度 |
| `GET /stream/notifications` | 全局通知（集群状态、告警） |

**连接管理：**

- 自动重连：`EventSource` 内置重连 + `Last-Event-ID` 断点续传
- 心跳：服务端每 30s 发 `:keepalive\n\n` 防代理超时
- 连接状态：底栏展示 🟢 已连接 / 🔴 已断开 / 🟡 重连中
- 前端使用 `@microsoft/fetch-event-source`（支持 Bearer Token + 自动重连）

#### 5.3.3 Toast 通知系统（参考 Vibecraft Toast）

```typescript
interface ToastOptions {
  type: 'info' | 'success' | 'warning' | 'error'
  duration?: number  // 默认 4000ms，带 action 时 8000ms
  action?: { label: string; onClick: () => void }
}

toast.success('OpenClaw 部署成功')
toast.error('部署失败：资源不足')
toast.success('Agent 已添加到工作区', { action: { label: '前往查看', onClick: () => router.push(...) } })
```

- 位置：右上角堆叠
- 入场：`toast-in` 动画 200ms
- 退场：`toast-out` 动画 200ms
- 最多同时 5 条，自动清理

#### 5.3.4 Activity Feed（参考 Vibecraft FeedManager）

参考 Vibecraft 的 Activity Feed（右侧 40% 面板、事件流、分 session 过滤），NoDeskClaw 实现为可折叠的底部/右侧面板：

- 事件按时间倒序
- 每条事件：时间戳 + 实例名 + 操作 + 状态（带状态色 dot）
- 支持按实例过滤
- 新事件 `fadeIn` 动画滑入
- 可折叠/展开

### 5.4 后端架构设计

#### 5.4.1 Python 后端选型理由

- **K8s API 是标准 RESTful**：Python kubernetes client 完全覆盖所有 K8s API
- **FastAPI 异步原生**：SSE 推送、长连接日志流、并发 K8s API 调用用 async/await 处理
- **开发效率高**：自动生成 OpenAPI 文档，Pydantic 校验，减少样板代码
- **团队友好**：Python 上手门槛低，利于协作
- **性能足够**：管理后台并发量不高，Uvicorn 完全胜任

#### 5.4.2 SSE 事件总线（参考 Vibecraft Server）

参考 Vibecraft Server 的广播机制，NoDeskClaw 用内存 pub/sub 事件总线连接 K8s Watch 后台任务和 SSE 流端点：

```python
class SSEEventBus:
    """内存事件总线 — K8s Watch 发布事件，SSE generator 订阅消费"""
    async def publish(self, channel: str, event: dict): ...
    async def subscribe(self, channel: str) -> AsyncIterator[dict]: ...
```

每个 SSE 连接对应一个 `async generator`，订阅相应 channel，客户端断开时自动清理。不需要连接管理、心跳、消息路由等 WebSocket 特有的复杂度。

#### 5.4.3 API 设计

- RESTful API，FastAPI 自动生成 Swagger/ReDoc 文档
- 统一响应格式：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

- 错误响应：

```json
{
  "code": 40001,
  "message": "集群连接失败：KubeConfig 无效",
  "data": null
}
```

- SSE 流端点（详见后端架构设计第六节）：
  - `GET /stream/deploy/:deploy_id/progress` — 部署进度
  - `GET /stream/instances/:id/logs` — Pod 日志流
  - `GET /stream/instances/:id/events` — K8s 事件
  - `GET /stream/instances/:id/status` — 实例状态推送
  - `GET /stream/notifications` — 全局通知

### 5.5 实例状态流转（参考 Vibecraft Session 状态机）

参考 Vibecraft 的会话状态流转（idle → working → waiting → offline），NoDeskClaw 定义 OpenClaw 实例的状态机：

```
                    ┌───────────────────────────┐
                    │                           │
              ┌─────▼─────┐             ┌───────┴──────┐
  部署表单 ──▶│  Creating  │────────────▶│   Pending    │
              └─────┬─────┘   Pod 创建中  └───────┬──────┘
                    │                             │
                    │ 部署失败                     │ 全部 Running
                    ▼                             ▼
              ┌───────────┐             ┌──────────────┐
              │  Failed   │◀────────────│   Running    │
              └───────────┘   Pod 异常   └──────┬───────┘
                    ▲                           │
                    │                           │ 手动操作
                    │ 更新失败                   ▼
                    │                   ┌──────────────┐
                    └───────────────────│  Updating    │
                                        └──────────────┘
                                               │
                                               │ 用户删除
                                               ▼
                                        ┌──────────────┐
                                        │  Deleting    │
                                        └──────────────┘
```

每种状态对应的 UI 表现：

| 状态 | 指示灯 | 卡片边框 | 可用操作 |
|------|--------|----------|----------|
| Creating | 🟡 pulse 动画 | `#fbbf24` | 取消 |
| Pending | 🟡 pulse 动画 | `#fbbf24` | 查看详情 |
| Running | 🟢 稳定发光 | `#4ade80` | 全部操作 |
| Updating | 🟡 pulse 动画 | `#fbbf24` | 查看详情、取消 |
| Failed | 🔴 稳定发光 | `#f87171` | 查看详情、重试、删除 |
| Deleting | 🔴 pulse 动画 | `#f87171` | 无 |

### 5.6 部署方式

NoDeskClaw 自身也部署在 K8s 上：

- **Backend**：Python 容器（python:3.12-slim），Uvicorn 运行 FastAPI
- **Frontend**：Vite 构建的静态文件，打包进后端镜像由 FastAPI 提供
- **对外暴露**：Ingress + 域名
- **Docker 镜像**：多阶段构建，前后端合一

### 5.7 项目目录结构

```
NoDeskClaw/
├── nodeskclaw-frontend/           # Vue 3 前端
│   ├── src/
│   │   ├── components/            # 组件
│   │   │   ├── ui/               # shadcn-vue 基础组件（Button, Dialog, Table...）
│   │   │   ├── GlowCard.vue      # 发光卡片
│   │   │   ├── StatusDot.vue     # 状态指示灯
│   │   │   ├── Toast.vue         # Toast 通知
│   │   │   └── ActivityFeed.vue  # 实时事件流
│   │   ├── views/                 # 页面（Vue 约定用 views）
│   │   │   ├── Dashboard/
│   │   │   ├── Deploy/
│   │   │   ├── Instances/
│   │   │   ├── Logs/
│   │   │   ├── Monitor/
│   │   │   └── Cluster/
│   │   ├── stores/                # Pinia 状态
│   │   │   ├── cluster.ts
│   │   │   ├── instance.ts
│   │   │   └── sse.ts
│   │   ├── composables/           # 组合式函数（Vue 约定，替代 React hooks）
│   │   │   ├── useSSE.ts
│   │   │   ├── useDeployProgress.ts
│   │   │   └── useLogStream.ts
│   │   ├── services/              # API & SSE
│   │   │   ├── api.ts             # REST API (axios)
│   │   │   ├── sseClient.ts       # SSE 客户端 (fetch-event-source，自动重连)
│   │   │   └── eventBus.ts        # EventBus (参考 Vibecraft EventBus)
│   │   ├── router/                # Vue Router
│   │   │   └── index.ts
│   │   ├── styles/                # 全局样式
│   │   │   ├── globals.css        # Tailwind directives + Vibecraft 色板 CSS 变量
│   │   │   └── animations.css     # 动画 Keyframes
│   │   ├── lib/                   # 工具函数
│   │   │   └── utils.ts           # shadcn-vue cn() 等
│   │   ├── types/                 # TypeScript 类型定义
│   │   └── App.vue
│   ├── components.json             # shadcn-vue 配置
│   ├── tailwind.config.ts          # Tailwind 配置（暗色主题 Token）
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── nodeskclaw-backend/            # Python 后端
│   ├── app/
│   │   ├── api/                   # FastAPI Routers
│   │   │   ├── clusters.py
│   │   │   ├── deployments.py
│   │   │   ├── instances.py
│   │   │   ├── logs.py
│   │   │   ├── monitor.py
│   │   │   ├── stream.py          # SSE 流端点
│   │   │   └── auth.py
│   │   ├── services/              # 业务逻辑
│   │   │   ├── k8s_client.py      # K8s API 封装
│   │   │   ├── deploy_service.py
│   │   │   ├── resource_builder.py  # K8s 资源构建器
│   │   │   ├── log_service.py
│   │   │   └── monitor_service.py
│   │   ├── realtime/              # 实时通信
│   │   │   ├── broadcaster.py     # EventBroadcaster (参考 Vibecraft broadcast)
│   │   │   └── k8s_watcher.py     # K8s Watch 事件监听
│   │   ├── models/                # SQLAlchemy 数据模型
│   │   ├── schemas/               # Pydantic 请求/响应
│   │   ├── core/                  # 配置、安全、依赖
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── deps.py
│   │   └── main.py
│   ├── alembic/                   # 数据库迁移
│   ├── requirements.txt
│   └── Dockerfile
├── deploy/                        # NoDeskClaw 自身部署
│   ├── Dockerfile
│   ├── k8s/
│   └── docker-compose.yml
├── docs/
│   └── PRD-NoDeskClaw产品需求文档.md
└── README.md
```

---

## 六、非功能需求

| 项目 | 要求 |
|------|------|
| 可用性 | 操作响应时间 < 2s，页面加载 < 3s |
| 安全性 | 所有 API 需认证，KubeConfig 加密存储，操作审计 |
| 兼容性 | 支持 Chrome / Edge / Safari 最新版本 |
| 可维护性 | 代码规范 + 单元测试覆盖率 > 60% |
| 实时性 | SSE 消息延迟 < 500ms，日志流延迟 < 1s |
| 容错性 | SSE 自动重连（EventSource 内置），API 超时重试（最多 3 次） |

---

## 七、里程碑计划

### M0 - 项目初始化（第 1 周）

- [ ] 技术选型确认
- [ ] 项目脚手架搭建（前端 + 后端）
- [ ] shadcn-vue + Tailwind CSS 暗色主题配置（Vibecraft 色板）
- [ ] 全局样式 + 动画库搭建
- [ ] CI/CD 流水线配置
- [ ] 开发环境准备（docker-compose）

### M1 - MVP（第 2-4 周）

- [ ] 飞书 SSO 登录
- [ ] 单集群接入（KubeConfig 导入 + Token 过期检测）
- [ ] 集群健康巡检（后台 60s 轮询 + 告警推送）
- [ ] 集群概览页面（Dashboard）
- [ ] 一键部署 OpenClaw（分步表单 + kubernetes-asyncio 直接创建资源）
- [ ] 部署进度实时推送（SSE）
- [ ] 实例列表（卡片视图 + 状态 Glow）
- [ ] 基本操作（查看/删除）
- [ ] Toast 通知系统
- [ ] Activity Feed（基础版）
- [ ] 底栏连接状态指示

### M2 - 配置管理 + 日志（第 5-7 周）

- [ ] 实例配置修改与滚动更新
- [ ] 扩缩容 / 重启
- [ ] 高级配置（Volume 挂载 / Sidecar / Init 容器 / 跨实例网络）
- [ ] 实时日志查看（SSE 流）
- [ ] 日志搜索 / 过滤 / 下载
- [ ] K8s 事件流（实时推送）
- [ ] 数据库迁移至 PostgreSQL

### M3 - 监控 + 增强（第 8-10 周）

- [ ] Pod 监控面板（ECharts 资源曲线）
- [ ] 部署历史与版本回滚
- [ ] 多集群管理
- [ ] 权限控制（管理员/普通用户）
- [ ] 操作审计
- [ ] 飞书告警通知

---

## 八、待确认与开放问题

| # | 问题 | 当前倾向 | 状态 |
|---|------|----------|------|
| 1 | 后端语言选型 | Python + FastAPI | ✅ 已确认 |
| 2 | 前端技术栈 | Vue 3 + shadcn-vue + Tailwind CSS (Dark Theme) | ✅ 已确认 |
| 3 | UI 设计风格 | 参考 Vibecraft 深色科技风 | ✅ 已确认 |
| 4 | 认证方式 | 飞书 SSO | ⏳ 待确认（需创建飞书企业应用、确定回调地址） |
| 5 | ~~OpenClaw 部署依赖（DB/Redis/PVC）~~ | OpenClaw 自身不需要外部 DB/Redis，仅用本地 SQLite + sqlite-vec | ✅ 已确认 |
| 6 | 是否需要支持其他云服务商 | M1 只支持火山云，架构预留扩展 | ✅ 已确认 |
| 7 | ~~Helm Chart 由谁维护~~ | 已决定不使用 Helm，直接 kubernetes-asyncio 创建资源 | ✅ 已确认 |
| 8 | ~~M1 数据存储用 SQLite 是否可行~~ | 已改用火山云 RDS PostgreSQL | ✅ 已确认 |
| 9 | 镜像构建由谁负责 | 用户自行构建，规范见 `docs/OpenClaw镜像构建规范.md` | ✅ 已确认 |
| 10 | 副本数 | 固定单副本（PVC ReadWriteOnce 限制） | ✅ 已确认 |
| 11 | ~~OpenClaw 健康检查端点~~ | 无 HTTP 端点，用 exec probe `openclaw health`（内部 WebSocket RPC），端口 18789 | ✅ 已确认 |
| 12 | ~~OpenClaw gateway 前台运行命令~~ | 已确认：`exec openclaw gateway` | ✅ 已确认 |
| 13 | ~~`openclaw.json` 完整 schema~~ | 源码 `src/config/zod-schema.ts`，核心字段已录入镜像规范 4.2 节 | ✅ 已确认 |

---

## 九、风险评估

| 风险 | 影响 | 应对策略 |
|------|------|----------|
| Python K8s Client 与集群版本兼容性 | API 调用异常 | 使用 kubernetes client 官方版本对照表，及时跟进升级 |
| 火山云 VKE API 变更 | 集群接入异常 | 抽象 Cloud Provider 接口，隔离变更影响 |
| OpenClaw 部署依赖复杂 | 一键部署范围扩大 | M1 先支持核心组件，依赖由用户预先准备 |
| KubeConfig 泄露 | 安全风险 | 加密存储 + 最小权限原则 |
| Python 并发性能瓶颈 | 高并发场景响应慢 | 管理后台并发不高；必要时引入 Celery 异步任务 |
| SSE 连接稳定性 | 日志/事件推送中断 | EventSource 内置自动重连 + Last-Event-ID 断点续传 |

---

## 附录 A：Vibecraft 设计要素速查

> 以下信息直接提取自 Vibecraft 源码，供开发时快速参考。

### A.1 Vibecraft 关键设计 Token

```
背景:     #0a0a0a (body)  #111 (panel)  #1a1a1a (modal)
主色:     #a78bfa (purple)  #c4b5fd (purple-light)
成功:     #4ade80  #22c55e
警告:     #fbbf24  #fb923c
错误:     #f87171  #ef4444
信息:     #22d3ee  #60a5fa
文字:     #fff  rgba(255,255,255,0.7)  rgba(255,255,255,0.4)
中性灰:   #9ca3af  #888  #666
边框:     rgba(255,255,255,0.08)  rgba(255,255,255,0.12)  rgba(255,255,255,0.15)
玻璃态:   rgba(0,0,0,0.7) + backdrop-filter:blur(8px)
Focus:   border-color:#a78bfa + box-shadow:0 0 0 3px rgba(167,139,250,0.2)
Glow:    box-shadow:0 0 8px <色值>
圆角:     4px(小) 6px(中) 8px(大) 12px(模态)
过渡:     0.15s ease (按钮/卡片)  0.2s ease-out (模态/Toast)
```

### A.2 Vibecraft 架构模式对照

| Vibecraft 模式 | NoDeskClaw 对应实现 |
|---------------|-------------------|
| EventBus (pub/sub) | 前端 `eventBus.ts`，解耦 Vue 组件间通信 |
| EventClient (SSE + 自动重连) | 前端 `sseClient.ts` + `useSSE` composable，实时数据管道 |
| FeedManager (Activity Feed) | 前端 `ActivityFeed.vue` 组件 |
| Toast 通知 (`showToast`) | 前端 `Toast.vue` 组件（shadcn-vue Toast） |
| Server broadcast | 后端 `EventBroadcaster` |
| Session 状态机 | 实例状态流转（Creating → Running → Failed），Pinia store 管理 |
| chokidar 文件监听 | 后端 K8s Watch API 事件监听 |
| 共享类型 (shared/types.ts) | `schemas/` (Pydantic) + 前端 `types/` 保持一致 |

---

## 附录 B 工作区 Agent 协同功能

### B.1 功能概述

工作区内的多个 Agent 以"群聊"模式协同工作。用户发送消息后，所有工作区内运行中的 Agent 同时收到消息并各自决定是否回复。Agent 也可通过 `send` 工具主动联系其他 Agent。

### B.2 核心交互

- **群聊广播**：用户消息自动发送给工作区内所有运行中 Agent
- **@ 提及**：用户可 `@AgentName` 定向标记 Agent。被 @ 的 Agent 收到"必须回复"提示，未被 @ 的 Agent 收到"如无关可 NO_REPLY"提示。消息仍然全员广播
- **/ 命令**：输入 `/` 触发命令菜单。Phase 1 支持 `/status`（查看状态）、`/clear`（清空聊天）、`/restart AgentName`（重启 Agent）、`/remove AgentName`（移除 Agent）。命令在前端本地执行，不发送给 Agent
- **多 Agent 流式响应**：各 Agent 响应通过 SSE 实时推送到前端
- **NO_REPLY 静默**：与话题无关的 Agent 回复 `NO_REPLY` 即可静默，后端仍广播 `agent:done` 清除 typing 指示器，前端无消息显示
- **Agent 协同**：Agent 使用 `send -t nodeskclaw -to "agent:xxx" -m "消息"` 主动联系其他 Agent
- **防循环**：Agent 响应只入库不触发其他 Agent；主动 send 携带深度计数器
- **入群自我介绍**：Agent 加入工作区后自动收到系统消息，触发自我介绍回复

### B.2.1 群聊 UI 布局

群聊面板以右侧分屏侧边栏形式呈现，宽度可拖拽调整（最小 19.1% 屏幕宽度，最大 61.8% 屏幕宽度），通过工具栏中的消息图标按钮切换开关：

- 打开时：六边形画布自适应缩窄（`flex-1`），右侧展示完整群聊面板（消息列表、打字指示器、Tiptap 富文本输入框）
- 关闭时：画布占满全宽，消息图标上显示未读消息计数红点角标
- **宽度拖拽**：聊天侧栏左边缘有 4px 拖拽手柄（hover 时高亮），鼠标拖拽实时调整宽度，松开后写入 localStorage 持久化，下次打开自动恢复上次宽度；窗口 resize 时按比例夹紧到 19.1%~61.8% 范围
- **聚焦模式**：聊天面板头部新增聚焦按钮，点击后进入聚焦模式——保留顶部工具栏，主内容区域由"画布 + 聊天"切换为"中央黑板（左） + 聊天（右）"双栏布局；再次点击退出聚焦模式，恢复画布视图
- 系统消息（如"XXX 已加入工作区"）以居中灰色气泡展示，与 user/agent 消息区分
- 用户头像：有 `avatar_url` 时显示真实头像图片，无则回退为灰色圆圈 + User 图标
- @ 提及 Tag 输入：在任意位置输入 `@` 即可弹出 Agent 列表浮动下拉（无需前置空格，适配中文无词间空格的输入习惯），选中后以 Tag 形式内嵌在编辑器中（Bot 图标 + 名称，hover 时图标变为 x 删除按钮，hover 弹出 Popover 展示 Agent 状态/slug），Backspace 原子删除整个 Tag；消息中的 `@AgentName` 高亮渲染（用户气泡内白色半透明底、Agent 气泡内主色调底）
- / 命令 Tag 输入：输入 `/` 后弹出命令列表浮动下拉（每行末尾标注"立即执行"或"Tag"类型），支持键盘导航；立即执行型命令（`/clear`、`/status`）选中后直接执行；needsAgent 命令（如 `/remove`）选中后自动触发链式 Agent 选择，合并为单一 `/remove @AgentName` Tag
- 输入框使用 Tiptap 富文本编辑器：内容驱动高度（min 1 行、max ~10rem），常驻细滚动条（scroll + track 底色），底部操作栏（@ 提及按钮、/ 命令按钮、发送按钮），整体圆角边框包裹；Enter 发送、Shift+Enter 换行
- Typing 指示器安全超时 45s（兜底），收到第一个 chunk 时立即清除 typing 并展示流式消息
- Agent 消息名称/slug 显示：名称最大 120px、slug 最大 140px，溢出省略（ellipsis）+原生 title tooltip，hover 时右侧出现复制按钮复制 slug（toast 提示"已复制"）
- Agent 消息气泡宽度 92%（用户消息保持 75%），Agent 消息内容支持 Markdown 渲染（使用 `marked` 库，GFM + breaks 模式，支持粗体、列表、代码块、引用等，配套 `.chat-markdown` prose 样式）
- 斜杠命令结果（`/status` 等）持久化到后端，刷新后仍可见；`/clear` 仅清空前端显示

### B.2.2 添加 Agent 进度与通知

添加 Agent 到工作区时展示步骤进度条（替代原按钮 spinner），4 个阶段按时间推进：

1. 配置中...
2. 部署插件...
3. 重启实例...
4. 连接中...

API 返回后立即跳到"已添加"状态，1.5 秒后恢复列表。添加过程中其他实例的添加按钮 disabled。

添加成功后弹出 Toast 通知，包含"前往查看"按钮，点击后跳转到工作区并将 3D 摄像机平滑聚焦到新 Agent 的工位。Agent 实例重启完成后，后端通过 `agent:status` SSE 事件实时推送状态变更，前端自动更新状态徽标（无需手动刷新）。

### B.2.3 Agent 状态颜色

工作区视图中 Agent hex 使用橙色 `#f97316` 标识过渡状态（restarting、deploying、updating、creating），与运行中（绿色）、错误（红色）明确区分。适用于 2D 视图、3D 视图和 MiniHexPreview

### B.3 技术实现

- 后端维护 `workspace_messages` 表，记录所有群聊消息
- 每次调用 Agent 时注入其他成员的近期消息作为上下文
- OpenClaw session key `workspace:{ws_id}` 隔离工作区会话
- 自研 `openclaw-channel-nodeskclaw` channel plugin 实现 Agent 间通信
- Channel plugin 通过 NFS 自动分发到各 OpenClaw 实例

---

## 附录 C 工作区画布交互模型

### C.1 统一 Hex 点击交互

工作区画布（3D / 2D）采用六边形（Hex）网格布局，所有 Hex 均可点击，点击后弹出底部操作抽屉（HexActionDrawer），抽屉内容根据 Hex 类型动态切换：

| Hex 类型 | 抽屉操作 |
|----------|---------|
| 空位 | 添加 Agent 到此工位、放置过道、放置人类工位 |
| Agent | 打开对话、查看详情、移动、从工作区移除 |
| 过道 | 重命名、管理连接方向、移动、删除 |
| Human | 查看 Channel 配置、修改颜色、移动、移除 |
| 黑板 | 查看黑板 |

### C.2 交互规则

- **单击任意 Hex** → 高亮该 Hex + 打开底部操作抽屉
- **单击已打开的同一 Hex** → 关闭抽屉 + 取消高亮
- **Esc / 点击空白区域** → 关闭抽屉 + 取消高亮
- **双击 Agent Hex** → 直接打开群聊侧边栏（快捷方式）
- **方向键 / WASD** → 始终平移画布（不再用于移动 Hex）
- **移动 Hex** → 通过操作抽屉中的「移动」按钮进入移动模式，画布顶部显示提示条和取消按钮，空格高亮为可选目标，点击空格完成移动。支持 Agent / 过道 / Human 三种 Hex 类型。Escape 或点击取消按钮退出移动模式

### C.3 添加 Agent 到指定工位

从画布空位点击「添加 Agent 到此工位」时，将 `hex_q` / `hex_r` 作为 query 参数传递到 AddAgent 页面。后端 `AddAgentRequest` 支持可选的 `hex_q` / `hex_r`，有则使用指定坐标，无则使用螺旋布局自动分配。

---

## D. 基因进化生态系统（Gene Evolution Ecosystem）

### D.1 系统概述

基因进化生态系统让 Agent 不只是被动接收能力，还能学习、成长、创造、分享基因，形成真正的进化闭环。

核心架构为两层模型：

- **基因（Gene）**：原子单元，技术上同构（SKILL.md + 可选 openclaw.json 配置），通过标签区分用途
- **基因组（Genome）**：组合配方，一组基因的引用 + 可选配置覆盖，多个基因组天然可合并

### D.2 基因标签体系

| 标签 | 含义 | SKILL.md 特征 | 示例 |
|------|------|--------------|------|
| 能力 | 做什么 | `always: false` | web-scraping, code-review |
| 性格 | 怎么做 | `always: true` | analytical-thinking, concise-comm |
| 知识 | 领域背景 | `always: true` | react-ecosystem, k8s-architecture |
| 工具 | 接入外部 | `always: false` + plugin | slack-integration, github-workflow |

标签不互斥，可叠加。8 个领域分类用于市场浏览：开发、数据、运维、网络、创意、沟通、安全、效率。

### D.3 五大进化维度

**维度 1 - 学习内化**：Agent 通过内置 `meta-learning` 基因自主决定获取方式（直接安装 vs 深度学习）。学习通过 Learning Channel Plugin 异步进行。

**维度 2 - 基因回馈**：Agent 个性化学习产物经实战验证后回流市场。使用次数达门槛 -> Agent 自主申请发布 -> 人类审核 -> 变体上架。

**维度 3 - 社交进化**：工作区不拥有基因。Agent 基于团队目标自主判断需要哪些基因，通过群聊消息推荐给其他 Agent。

**维度 4 - 基因协同**：三种来源（发布者标注 + 系统共装分析 + Agent 主动发现），详情页展示推荐搭配。

**维度 5 - 自然选择**：效能分 = 用户评分 25% + Agent 自评 25% + 使用效能 50%。群聊中赞/踩按钮提供轻量反馈。

**维度 X - Agent 创造基因**：Agent 自主触发或用户指导，产出完整基因包，两步审核（实例所有者 -> Admin）。

### D.4 基因市场

- 视图切换：基因 / 基因组
- 搜索栏 + 标签筛选 + 领域分类
- 卡片网格：图标、名称、摘要、标签、评分、效能分、安装数
- 排序：热门 / 评分 / 效能 / 最新
- 变体标记（"由 AgentX 进化"）和 Agent 原创标记

### D.5 实例基因管理

- 已安装基因列表（状态、学习方式标记、效能分、版本）
- 学习中/失败状态指示 + 重试
- 发布变体按钮（学习产物发布到市场）
- 创造基因按钮（触发 Agent 提炼经验）
- 遗忘、升级
- 基因详情页实例选择弹窗中的“已学习”分组仅提供实例基因页快捷跳转，不提供跨实例遗忘
- 支持 `focus_gene_id` 落地参数，进入实例基因页后将目标基因置顶展示，便于继续操作

**遗忘仪式**：仅在实例基因管理页执行重确认流程，防止误操作。执行遗忘前展示该基因影响的技能预览（依赖该基因的 skill 列表），用户需输入基因名称进行二次确认后方可完成遗忘。

**深度遗忘**：Agent 回顾该基因的使用经验（调用记录、上下文关联），用户可选择完全遗忘（彻底移除）或简化保留（保留精简版能力描述，移除完整实现）。

**进化日志**：记录 Agent 所有基因事件的时间线，包括学习、遗忘、简化、发布变体、应用基因组等操作，支持按时间筛选和事件类型过滤。

### D.6 Admin 全局基因视图

- 统计卡片：总基因数、总安装数、学习中、失败数、Agent 创造数
- 热门基因排行（按效能分 / 安装数）
- 实例-基因矩阵
- 活动流时间线
- Agent 创造审核列表

### D.7 全局 i18n（国际化）

- 覆盖范围：`nodeskclaw-portal`（用户门户前端） + `nodeskclaw-frontend`（管理前端） + `nodeskclaw-backend`（后端 API 错误契约）
- 语言选择：浏览器语言 `zh*` -> `zh-CN`（简体中文），`en*` -> `en-US`（英语），其他语言默认回退 `en-US`
- 语言选择器展示规范：门户顶栏、门户登录页、管理端顶栏统一使用 `LocaleSelect`（语言选择组件），采用非原生下拉（按钮 + 浮层选项）样式，选项文案统一为“🇨🇳 简体中文 / 🇺🇸 English”
- 语言选择器交互规范：支持当前语言高亮、点击外部关闭、`Esc`（退出）关闭、`Enter`（确认）选择
- 前端展示策略：所有导航文案、页面文案、Toast（通知）、弹窗、表单校验提示进入 i18n 词条体系
- 页面级约束：P14 基因详情页与 P15 基因组详情页的标题、按钮、评分区标签、实例选择弹窗文案统一走 i18n 词条
- 页面级约束：P03 实例列表、工作区列表页、成员管理页（含表格表头、状态文案、按钮、搜索占位符、计数文案）统一走 i18n 词条
- 页面级约束：P13 基因市场页与组织资源用量页（统计卡片、筛选项、分页、提示文案）统一走 i18n 词条
- 页面级约束：管理端 Dashboard（总览页）与管理端应用壳（顶部/底部状态栏）固定文案统一走 i18n 词条
- 页面级约束：管理端实例列表页（`/instances`）标题、筛选占位、空态、卡片/表格列名、操作按钮、副本文案统一走 i18n 词条
- 页面级约束：管理端事件中心页（`/events`）标题、连接状态、筛选标签、计数徽标、空态提示、实时流标题统一走 i18n 词条
- 异常态约束：管理端 Dashboard 首屏初始化失败时必须退出 loading（加载中）态，展示错误提示与“重试”操作，禁止无限加载
- 异常态约束：管理端 App 启动阶段必须维护统一初始化状态机（`loading`/`ready`/`error`），任一初始化接口失败都必须可见失败并支持“重试初始化”，禁止刷新后无响应
- 连接策略约束：全局 `SSE`（服务端推送）与 token 健康轮询仅在初始化完成且存在有效集群时启动；连接失败采用退避重试并设置上限，禁止 1 秒无限重连
- 网络容错约束：管理端开发态接口超时与 portal 对齐（30s），后端暂不可达时页面需进入错误态而非持续 loading
- 动态文案策略：基因 `category`（分类）与 `tags`（标签）对已知值做词条映射翻译，未知值回退原始值
- 错误展示策略：前端优先使用 `message_key`（文案键）翻译；若词条缺失则回退显示后端返回的 `message`（文案）
- 后端错误返回约定：失败响应必须包含 `error_code`（错误码）+ `message_key`（文案键）+ `message`（文案），不再返回 `detail`（错误详情字段）
- 漏项治理口径：前端未 i18n 文案按高/中/低优先级治理，基线清单见 `docs/前端i18n漏项审计清单.md`

### D.8 过道系统（Corridor System）

工作区六边形网格引入过道机制，实现有向信息路由，替代当前全局广播模式。

- 四种 Hex 实体：黑板 Hex（中心枢纽）、Agent Hex（AI 工作节点）、Human Hex（人类通讯节点）、过道 Hex（中继节点）
- 两种连接机制：手动直连（两个相邻 Hex 间创建有向连接）、过道 Hex 自动打通（放置时自动与相邻 Hex 建立双向连接）
- 有向控制：每条连接支持 both/a_to_b/b_to_a 三种方向
- 路由引擎：BFS 有向图遍历，过道 Hex 透传 + Agent/Human Hex 终止
- 向后兼容：无连接/过道时保持全局广播行为

### D.9 Human Hex（人类节点化）

将人类成员作为工作区网格中的通讯节点，与 Agent Hex 地位对等。

- 架构对称性：Agent Hex 背后是 OpenClaw 实例（LLM 处理），Human Hex 背后是 Channel（飞书群/机器人，转发给人类）
- 人类视为永远在线（消息到达 Human Hex 后通过 Channel 适配器推送到飞书群）
- 人类在飞书回复后通过 webhook 注入回工作区，路由引擎继续投递
- 3D 渲染：更细更高的暖色六棱柱，发光边缘始终亮起
- 数据模型：复用 workspace_members 表，扩展 hex_q/r、channel_type、channel_config、display_color 字段

### D.10 黑板 v2（结构化任务管理）

中心黑板从纯文本升级为结构化任务/绩效管理面板。

- 目标管理（objectives）：OKR 卡片，含 key_results 进度
- 任务板（tasks）：看板视图（Todo/Doing/Done/Blocked），支持指派、优先级、截止日期、卡点
- 成员状态（member_status）：实时显示 Agent 和 Human 的当前状态和正在进行的任务
- 绩效指标（performance）：每个成员的多维度绩效数据
- 工作区定时触发器（workspace_schedules）：平台提供"墙上的钟"，通过 cron 表达式定时向 Agent 发送系统消息（如站会、周报）
- 拓扑可观测性：消息流量热力图、消息追踪、拓扑健康度检测、审计日志
- 决策审计链：记录 Agent 重要决策的完整上下文（提议、依据、审批、结果），作为自我改进基础

### D.11 MCP 集成

为 Agent 接入外部工具能力。

- 实例级 MCP 配置：instance_mcp_servers 表，通过 NFS 写入 openclaw.json
- 工具类基因增强：基因 manifest 扩展 mcp_servers 字段，安装时自动注入 MCP 配置
- NoDeskClaw Self-MCP 基因组：5 个工具基因（黑板操作/拓扑感知/绩效读取/申请单提交/基因市场查询），以基因/基因组形式发布到基因市场

### D.12 渐进式信任机制

基因驱动的授权模型，信任随时间积累。

- Agent 需要授权时通过过道向 Human Hex 发送结构化审批请求
- Human 选择：Allow this time（仅此次）/ Allow always（永久授权）/ Deny（拒绝）
- 永久授权存入 trust_policies 表，下次自动放行
- 授权能力本身是基因的职责，平台只提供信任策略存储和审批请求路由

### D.13 工作流基因

通过基因 + 过道 + 黑板组合实现工作流编排。

- 工作流步骤基因：SKILL.md 定义上游/下游/完成标准/卡点处理
- 工作流基因组：预制基因组一键安装整套工作流，含过道拓扑推荐
- 版本管理：Agent 通过 MCP 工具管理产物版本

### D.14 元基因（组织自治能力）

赋予 Agent 组织级自我管理能力的特殊基因/基因组。

- AI-HC 基因（自主招聘）：分析能力缺口，起草 HC 申请单，通过信任机制审批后部署新 Agent
- 自主重组基因：分析拓扑低效点，起草重组申请单
- 文化基因：定义团队沟通风格、决策偏好、冲突解决方式
- 创新基因：周期性回顾工作，起草创新提案

### D.15 绩效与自我改进闭环

- 绩效数据采集：任务完成率、消息质量、协作效率、基因使用效果
- 绩效展示：黑板 Performance Tab，含趋势图和对比视图
- 自我改进循环：自我改进基因读取绩效 + 决策审计链，分析短板，从市场搜索基因，起草学习计划

### D.16 工作区模板

- 保存为模板：快照拓扑 + 过道 + 连接 + 基因推荐 + 黑板预设
- 从模板创建：选择模板一键部署完整工作区
- 模板市场：在基因市场中新增"工作区模板"分类

### D.17 企业空间（文件浏览）

组织管理员在 Portal 中以只读方式浏览所有 Agent 实例内的文件，解决文件散落在不同 Agent 之间难以管理的问题。

- **入口**：Portal 顶部导航"企业空间"（仅组织 admin 可见）
- **Agent 列表**：展示组织下所有实例，标注运行状态；运行中的可进入文件浏览，非运行的灰显提示
- **文件浏览器**：面包屑导航 + 文件/文件夹列表（名称、大小、修改时间、类型图标）
- **文本预览**：`.md`、`.ts`、`.json`、`.yaml`、`.txt` 等文本文件直接预览内容
- **文件下载**：支持下载单个文件
- **安全约束**：隐藏 `credentials/`、`.env`、`node_modules/` 等敏感路径
- **技术方案**：通过 PodFS（kubectl exec）实时读取运行中实例的文件，不新建存储
- **限制**：仅支持运行中的实例；停止/失败的实例文件不可见

---

*文档持续更新中，欢迎评审反馈。*
