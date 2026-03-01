# Three.js 代码建模参考

本文档记录了项目 3D 可视化场景中所有通过代码构建的模型清单、使用的几何体类型，以及自制模型的入门指南。

## 1. 概述

### 什么是"代码建模"

本项目的 3D 场景**没有使用任何外部模型文件**（如 `.glb`、`.gltf`、`.obj`、`.fbx`），所有 3D 物体均通过 TypeScript 代码调用 Three.js 内置几何体（Geometry Primitives）拼装而成。

这种方式类似于用基础积木块搭建造型：球体做头、胶囊体做身体、方块做桌面……通过设置位置、旋转、缩放和材质属性，组合出完整的角色和场景。

### 技术栈

- **语言**：TypeScript（`.ts` 文件）
- **3D 库**：Three.js（`three` NPM 包）
- **构建工具**：Vite
- **运行环境**：浏览器（WebGL）

### 适用场景

- Low Poly / 卡通风格的 3D 场景
- 不依赖 Blender 等建模软件
- 需要程序化生成、动态修改的模型
- 轻量级 Web 3D 可视化

---

## 2. 完整模型清单

### 2.1 角色模型

项目中有两个可切换的角色模型，通过 `ICharacter` 接口实现热替换。默认使用机器人角色。

#### 2.1.1 人形角色（Claude）

源文件：`entities/Claude.ts`

暖色调简约人偶风格，由 6 个核心部件组成。

| 部件 | 几何体 | 参数 | 颜色 | 材质 |
|---|---|---|---|---|
| 身体 | `CapsuleGeometry` | 半径 0.25, 高度 0.4 | `0xd4a574`（暖米色） | Standard, roughness 0.7, metalness 0.1 |
| 头部 | `SphereGeometry` | 半径 0.22, 分段 16x16 | `0xd4a574` | Standard, roughness 0.7, metalness 0.1 |
| 眼睛 (x2) | `SphereGeometry` | 半径 0.04, 分段 8x8 | `0x222222`（深灰） | Standard, roughness 0.3 |
| 手臂 (x2) | `CapsuleGeometry` | 半径 0.06, 高度 0.25 | `0xd4a574` | Standard, roughness 0.7, metalness 0.1 |
| 状态环 | `RingGeometry` | 内径 0.35, 外径 0.4, 分段 32 | `0x4ade80`（绿色） | Basic, 半透明 opacity 0.6 |
| 思考气泡 (x3) | `SphereGeometry` | 半径 0.08 / 0.12 / 0.18 | `0xffffff`（白色） | Basic, 半透明 opacity 0.85 |

**动画状态**

| 状态 | 状态环颜色 | 动画表现 |
|---|---|---|
| idle（空闲） | `0x4ade80` 绿色 | 身体微微上下浮动，手臂轻摆 |
| walking（行走） | `0x60a5fa` 蓝色 | 身体弹跳，手臂交替摆动，面朝移动方向 |
| working（工作） | `0xfbbf24` 黄色 | 右臂锤击/打字动作，身体微弹 |
| thinking（思考） | `0xa78bfa` 紫色 | 头部歪斜点头，右臂托腮，思考气泡浮现 |

#### 2.1.2 机器人角色（Grabby） -- 屏幕脸造型 v2

源文件：`components/hex3d/Grabby.ts`（六角格工作区版）

**设计风格**：屏幕脸机器人（Screen-Face Bot），类 Wall-E Eve 风格。圆角方块头部搭配整面发光屏幕，胶囊形蛋状身体，无腿悬浮设计。与旧版 ClaudeMon（球形头+矩形LED眼+圆柱躯干+腿脚）完全不同。

**结构色方案**（银灰蓝调，在深色背景上清晰可辨）：
- 主体色 `bodyMainMat`: `0x7a8a9a`（中灰蓝，metalness 0.7）
- 次要色 `bodySecMat`: `0x8a9aaa`（稍亮，metalness 0.6）
- 点缀色 `bodyTerMat`: `0x9aaabb`（最亮，metalness 0.7）
- 屏幕底色 `screenBackMat`: `0x1a2a3e`（深蓝黑）
- 面板色 `chestPanelMat`: `0x2a3a4e`

实现特性：
- 几何体模块级共享，accent 材质按 Agent 状态动态切换
- 整体缩放 0.65x，悬浮在扁平六棱柱底座（高度 0.08）上方
- 支持 5 种动画状态：idle（浮动）、working（屏幕闪烁+手臂忙碌）、thinking（托腮+思考气泡）、error（抖动+屏幕闪红）、disconnected（静止灰色）
- 支持每个 Agent 独立主题色（`theme_color`，后端持久化）

**头部组件**

| 部件 | 几何体 | 参数 | 颜色 | 说明 |
|---|---|---|---|---|
| 头壳 | `BoxGeometry` | 0.38 x 0.30 x 0.28 | `0x7a8a9a`（银灰蓝） | 圆角方块外壳，像显示器 |
| 屏幕底板 | `PlaneGeometry` | 0.34 x 0.26 | accent 色半透明 | 屏幕边框发光 |
| 屏幕 | `PlaneGeometry` | 0.32 x 0.24 | accent 色低透明度 | 主屏幕面板，working 时闪烁 |
| 圆形眼睛 (x2) | `CircleGeometry` | 半径 0.035 | accent 色 | 圆形眼睛（非矩形LED） |
| 嘴巴 | `Line` (QuadraticBezierCurve3) | 宽 0.07 | accent 色 | 微笑弧线 |
| 传感器 (x2) | `BoxGeometry` | 0.04 x 0.10 x 0.06 | `0x8a9aaa` | 头部两侧小方块（替代旧版圆盘耳） |
| 双天线杆 (x2) | `CylinderGeometry` | 上径 0.012, 下径 0.015, 高 0.08 | `0x9aaabb` | 头顶左右各一根 |
| 双天线灯 (x2) | `SphereGeometry` | 半径 0.025 | accent 色发光 | 天线顶端脉冲灯 |

**身体组件**

| 部件 | 几何体 | 参数 | 颜色 | 说明 |
|---|---|---|---|---|
| 躯干 | `BoxGeometry` | 0.34 x 0.28 x 0.24 | `0x7a8a9a` | 方块体，与方块头统一风格 |
| 胸部面板 | `PlaneGeometry` | 0.14 x 0.10 | `0x2a3a4e` | 半透明 opacity 0.8 |
| 胸灯 | `CircleGeometry` | 半径 0.025 | accent 色 | 脉冲发光状态指示 |
| 发光线条 (x2) | `PlaneGeometry` | 0.008 x 0.16 | accent 色半透明 | 身体两侧科技线条 |

**肢体组件**

| 部件 | 几何体 | 参数 | 颜色 | 说明 |
|---|---|---|---|---|
| 肩关节 (x2) | `SphereGeometry` | 半径 0.04 | `0x9aaabb` | metalness 0.7 |
| 臂段 (x2) | `CylinderGeometry` | 上径 0.028, 下径 0.032, 高 0.12 | `0x8a9aaa` | 比旧版更短 |
| 手 (x2) | `SphereGeometry` | 半径 0.038, scale(1.1, 0.7, 1.1) | `0x9aaabb` | 扁椭球手掌 |

**底部与附属**

| 部件 | 几何体 | 参数 | 颜色 | 说明 |
|---|---|---|---|---|
| 悬浮环 | `RingGeometry` | 内径 0.12, 外径 0.16 | accent 色半透明 | 底部悬浮推进器光环，匹配方块体宽度 |
| 状态环 | `RingGeometry` | 内径 0.28, 外径 0.32 | 随状态变化 | 地面旋转光环 |
| 思考气泡 (x3) | `CircleGeometry` | 半径 0.04 / 0.06 / 0.09, 6 段 | accent 色 | 六角形气泡，科技风 |

#### 2.1.2a 电话工位（Channel 指示物）

源文件：`components/hex3d/Grabby.ts` 中的 `createPhoneStation()` 函数

当 Agent 的 SSE 连接活跃（`sse_connected === true`）时，在工位底座右前方显示一个带小桌子的迷你复古电话，表示该 Agent 的 channel 处于活跃状态。

**小桌子**

| 部件 | 几何体 | 参数 | 颜色 | 说明 |
|---|---|---|---|---|
| 桌面 | `BoxGeometry` | 0.14 x 0.04 x 0.10 | `0x6a5a4a`（木色） | 小方桌 |
| 桌腿 (x4) | `CylinderGeometry` | 半径 0.008, 高 0.04 | `0x6a5a4a` | 四角细腿 |

**电话（scale 1.8x，放在桌面上）**

| 部件 | 几何体 | 参数 | 颜色 | 说明 |
|---|---|---|---|---|
| 底座 | `CylinderGeometry` | 半径 0.05, 高 0.018 | `0x8a9aaa`（银灰） | 扁圆盘 |
| 话筒支架 (x2) | `CylinderGeometry` | 半径 0.015, 高 0.012 | `0x8a9aaa` | 竖直搁架 |
| 听筒连接杆 | `CylinderGeometry` | 半径 0.01, 高 0.055 | accent 色金属 | 横向，连接两个耳件 |
| 听筒耳件 (x2) | `SphereGeometry` | 半径 0.02, scale(1, 0.7, 1) | accent 色发光 | 微微发光 |

- 位置：`(0.45, 0.02, 0.35)` 相对于 hex group，旋转 -30 度
- SSE 断开时整个 phoneStation `visible = false`

**动画状态颜色**

颜色优先级：断开时固定暗灰 > 用户自定义 `theme_color` > 状态色 > 默认 accent

`animateGrabby(robot, status, sseConnected, time, customColor?)` 支持第 5 个可选参数 `customColor`（从 `agent.theme_color` 解析的 number），SSE 连接时优先使用。

| 状态 | accent 颜色 |
|---|---|
| running / active | `0x4ade80` 绿色 |
| learning | `0x60a5fa` 蓝色 |
| thinking | `0xa78bfa` 紫色 |
| pending | `0xfbbf24` 琥珀色 |
| idle | `0x8b8b9e` 灰色 |
| error / failed | `0xf87171` 红色 |
| deploying / updating 等 | `0xf97316` 橙色 |
| disconnected | `0x555566` 暗灰 |

#### 2.1.3 子代理系统（SubagentManager）

源文件：`entities/SubagentManager.ts`

子代理管理器不定义新的模型，而是在 Portal 工作站处生成**缩小版的角色实例**：

| 属性 | 值 |
|---|---|
| 缩放比例 | 0.6（主角色的 60%） |
| 初始状态 | thinking |
| 生成位置 | Portal 工作站附近，按扇形散开避免重叠 |
| 颜色循环 | `0x60a5fa`（蓝）→ `0x34d399`（翠绿）→ `0xf472b6`（粉）→ `0xa78bfa`（紫）→ `0xfbbf24`（琥珀）→ `0x22d3ee`（青） |

每个子代理使用独立的主题色，在任务完成后自动销毁（调用 `dispose()` 释放资源）。

---

### 2.2 工作站模型

源文件目录：`scene/stations/`

所有工作站共享一个底座结构，在此之上各自添加装饰部件：

**共享底座**（在 `WorkshopScene.ts` 的 `createStationInZone` 中创建）

| 部件 | 几何体 | 参数 | 说明 |
|---|---|---|---|
| 桌体 | `BoxGeometry` | 1.5 x 0.8 x 1 | 颜色随工作站类型变化，roughness 0.7, metalness 0.2 |
| 指示环 | `RingGeometry` | 内径 0.9, 外径 1.0, 分段 32 | 半透明 opacity 0.3，平铺地面 |

#### 2.2.1 电脑终端（TerminalStation）

源文件：`scene/stations/TerminalStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| CRT 显示器框 | `BoxGeometry` | 1.1 x 0.8 x 0.3 | `0x2a2a35` |
| 屏幕 | `PlaneGeometry` | 0.85 x 0.55 | `0x0a0a12`，emissive `0x112244` |
| 命令行光标 | `PlaneGeometry` | 0.15 x 0.08 | `0x44ff88`（绿色发光） |
| 键盘 | `BoxGeometry` | 0.7 x 0.03 x 0.25 | `0x1a1a22` |

#### 2.2.2 书桌（DeskStation）

源文件：`scene/stations/DeskStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 纸张 | `BoxGeometry` | 0.6 x 0.02 x 0.8 | `0xf5f5dc`（米白） |
| 铅笔 | `CylinderGeometry` | 半径 0.02, 高 0.4 | `0xffd700`（金色） |
| 墨水瓶 | `CylinderGeometry` | 上径 0.08, 下径 0.1, 高 0.15 | `0x1a1a2e`（深色） |

#### 2.2.3 工作台（WorkbenchStation）

源文件：`scene/stations/WorkbenchStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 虎钳底座 | `BoxGeometry` | 0.2 x 0.15 x 0.15 | `0x888899`（金属色） |
| 虎钳夹爪 | `BoxGeometry` | 0.08 x 0.2 x 0.12 | `0x888899` |
| 锤头 | `BoxGeometry` | 0.15 x 0.08 x 0.08 | `0x888899` |
| 锤柄 | `CylinderGeometry` | 上径 0.02, 下径 0.025, 高 0.3 | `0x4a5a6a` |
| 大齿轮 | `TorusGeometry` | 主半径 0.1, 管半径 0.025 | `0xf97316`（橙色） |
| 小齿轮 | `TorusGeometry` | 主半径 0.07, 管半径 0.02 | `0xf97316` |
| 螺丝刀柄 | `CylinderGeometry` | 上径 0.03, 下径 0.035, 高 0.12 | `0xcc3333`（红色） |
| 螺丝刀杆 | `CylinderGeometry` | 半径 0.012, 高 0.15 | `0x888899` |

#### 2.2.4 书架（BookshelfStation）

源文件：`scene/stations/BookshelfStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 侧板 (x2) | `BoxGeometry` | 0.1 x 1.5 x 0.8 | `0x3a5a6a`（蓝灰） |
| 搁板 (x2) | `BoxGeometry` | 1.4 x 0.05 x 0.8 | `0x3a5a6a` |
| 书本 (x5) | `BoxGeometry` | 0.15 x 0.35 x 0.5 | 红/绿/蓝/黄/粉 各一本 |

书本颜色列表：`0xcc3333`, `0x33cc33`, `0x3333cc`, `0xcccc33`, `0xcc33cc`

#### 2.2.5 天线塔（AntennaStation）

源文件：`scene/stations/AntennaStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 塔杆 | `CylinderGeometry` | 上径 0.04, 下径 0.06, 高 1.2 | `0x666677`（金属灰） |
| 横梁 (x3) | `BoxGeometry` | 0.4 x 0.02 x 0.02 | `0x666677` |
| 卫星碟 | `SphereGeometry` | 半径 0.25, 半球 | `0xaaaabb`（亮银），metalness 0.8 |
| 信号波 (x2) | `RingGeometry` | 递增尺寸 | `0x66aaff`（淡蓝），半透明 |
| 顶部指示灯 | `SphereGeometry` | 半径 0.03 | `0xff4444`（红色） |

#### 2.2.6 扫描仪（ScannerStation）

源文件：`scene/stations/ScannerStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 放大镜手柄 | `CylinderGeometry` | 上径 0.04, 下径 0.05, 高 0.5 | `0x4a5a6a`（蓝灰） |
| 镜框 | `TorusGeometry` | 主半径 0.28, 管半径 0.04 | `0xc9a227`（金色），metalness 0.7 |
| 镜片 | `CircleGeometry` | 半径 0.26, 分段 24 | `0xaaddff`（淡蓝），半透明 opacity 0.4 |
| 反光点 | `CircleGeometry` | 半径 0.06 | `0xffffff`，半透明 opacity 0.6 |

#### 2.2.7 传送门（PortalStation）

源文件：`scene/stations/PortalStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 传送门环 | `TorusGeometry` | 主半径 0.6, 管半径 0.1 | `0x8844ff`（紫色），emissive `0x4422aa` |
| 传送中心 | `CircleGeometry` | 半径 0.5, 分段 32 | `0xaa66ff`（亮紫），半透明 opacity 0.5 |

#### 2.2.8 任务板（TaskboardStation）

源文件：`scene/stations/TaskboardStation.ts`

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 挂板 | `BoxGeometry` | 1.2 x 0.9 x 0.05 | `0x3a3a4e` |
| 便签卡片 (x4) | `BoxGeometry` | 0.3 x 0.2 x 0.01 | 绿/黄/蓝/粉 各一张 |

便签颜色列表：`0x4ade80`, `0xfbbf24`, `0x60a5fa`, `0xf472b6`

---

### 2.3 场景元素

#### 2.3.1 区域平台（Zone）

源文件：`scene/WorkshopScene.ts` 的 `createZonePlatform`

每个会话区域是一个六角形平台，包含以下元素：

| 部件 | 几何体 | 参数 | 说明 |
|---|---|---|---|
| 六角地板 | `ShapeGeometry` | 六角形, 半径 10 | 颜色 `0x1a2535`，接收阴影 |
| 边框环 | `ShapeGeometry` | 外六角 - 内六角（差值 0.5） | 使用区域主题色，半透明 opacity 0.5 |
| 中心基座 | `CylinderGeometry` | 上径 1, 下径 1.2, 高 0.2, 6 段 | 六棱柱，使用区域主题色，带发光 |
| 边缘线 | `LineSegments` | 六角形顶点连线 | 升高时显示，标示平台高度 |
| 侧面 | `Mesh` | 动态生成 | 升高时显示，填充平台侧面 |

**区域主题色循环**

```
0x4ac8e8（青色）→ 0x60a5fa（蓝色）→ 0x22d3d8（青绿）→ 0x4ade80（绿色）
→ 0xa78bfa（紫色）→ 0xfbbf24（橙色）→ 0xf472b6（粉色）→ 0xa3e635（黄绿）
```

#### 2.3.2 粒子系统

源文件：`scene/WorkshopScene.ts` 的 `createParticleSystem`

| 属性 | 值 |
|---|---|
| 粒子数量 | 20 |
| 几何体 | `BufferGeometry`（Float32Array 手动管理位置） |
| 材质 | `PointsMaterial`，size 0.15，AdditiveBlending |
| 用途 | 区域活动时的上升发光粒子效果 |

#### 2.3.3 六角网格（HexGrid）

源文件：`utils/HexGrid.ts`

世界坐标系基础网格，不直接创建 Mesh，而是提供坐标计算：
- 尖顶（pointy-top）六角形布局
- 轴向坐标系（axial coordinates：q 列, r 行）
- 默认六角半径 10，间距因子 1.1
- 螺旋式区域分配算法

#### 2.3.4 浮动标签（ZoneLabel）

源文件：`scene/WorkshopScene.ts` 的 `createZoneLabel`

| 属性 | 值 |
|---|---|
| 实现方式 | Canvas 2D 绑定文字 → `CanvasTexture` → `SpriteMaterial` → `Sprite` |
| Canvas 尺寸 | 512 x 96 |
| 文字样式 | 600 weight, 36px, system-ui |
| 特效 | 多层阴影 + 主题色辉光（3 层渐进 shadowBlur） |

#### 2.3.5 通知气泡（ZoneNotification）

源文件：`scene/ZoneNotifications.ts`

浮动上升并淡出的提示信息，同样采用 Canvas → Sprite 方案。支持 5 种样式：

| 样式 | 颜色 |
|---|---|
| success | `#4ade80` 绿色 |
| info | `#60a5fa` 蓝色 |
| warning | `#fbbf24` 琥珀色 |
| error | `#f87171` 红色 |
| muted | `#9ca3af` 灰色 |

#### 2.3.6 工作站面板（StationPanel）

源文件：`scene/StationPanels.ts`

工具历史记录的悬浮显示面板。Canvas 256x160 → Sprite，按 P 键切换显示/隐藏。

#### 2.3.7 等待区加载动画（Pending Zone）

源文件：`scene/WorkshopScene.ts` 的 `createPendingZone`

区域创建前的加载过渡动画，由旋转球点和六角线框组成：

| 部件 | 几何体 | 参数 | 颜色 |
|---|---|---|---|
| 六角线框 | `BufferGeometry` → `Line` | 半径 10 的六角形轮廓 | `0x4ac8e8`（青色），opacity 0.5 |
| 旋转点 (x3) | `SphereGeometry` | 半径 0.3, 分段 8x8 | `0x4ac8e8`，opacity 0.8 |

动画参数：旋转速度 2 rad/s，脉冲速度 3 Hz，缩放范围 0.8 +/- 0.3，垂直浮动 +/- 0.2。3 个点沿半径 1.5 的圆均匀分布，在高度 0.5 处旋转。

#### 2.3.8 世界地板（World Floor）

源文件：`scene/WorkshopScene.ts` 的 `createWorldFloor`

| 属性 | 值 |
|---|---|
| 几何体 | `PlaneGeometry` 500 x 500 |
| 材质 | `MeshBasicMaterial`，`visible: false` |
| 用途 | 不可见，仅用于鼠标射线检测（Raycasting），确定点击/悬浮的世界坐标 |

#### 2.3.9 世界六角网格（World Hex Grid）

源文件：`scene/WorkshopScene.ts` 的 `createWorldHexGrid`

| 属性 | 值 |
|---|---|
| 几何体 | `BufferGeometry`（所有六角边合并为单个顶点数组） |
| 渲染对象 | `LineSegments`（一次 draw call 渲染全部网格线） |
| 材质 | `LineBasicMaterial`，颜色 `0x4ac8e8`，opacity 0.35 |
| 范围 | 由 `gridRange` 控制（默认 20 环），轴向坐标约束为近似圆形 |

性能优化：使用合并几何体（merged geometry）将数百个六角形的线段合并为单个 `LineSegments` 对象，只需一次 GPU draw call。

#### 2.3.10 鼠标悬浮高亮（Hover Highlight）

源文件：`scene/WorkshopScene.ts` 的 `setupHoverHighlight`

| 属性 | 值 |
|---|---|
| 几何体 | `BufferGeometry`（7 个顶点的六角形闭合线） |
| 渲染对象 | `Line` |
| 材质 | `LineBasicMaterial`，颜色 `0x67e8f9`，opacity 0.6 |
| 行为 | 跟随鼠标移动，吸附到最近的六角格中心，空闲时隐藏 |

#### 2.3.11 点击脉冲波纹（Click Pulse）

源文件：`scene/WorkshopScene.ts` 的 `spawnClickPulse`

点击时产生的两层视觉反馈：

| 层 | 几何体 | 参数 | 说明 |
|---|---|---|---|
| 扩散环 | `RingGeometry` | 内径 0.2, 外径 0.4 | 从点击点扩散，AdditiveBlending，0.5 秒淡出 |
| 六角涟漪 (x N) | `BufferGeometry` → `Line` | 六角轮廓 | 从中心向外扩散最多 7 层环，强度按 0.6^n 衰减 |

涟漪以 45ms 间隔逐层生成，模拟水波扩散效果。使用 AdditiveBlending + depthWrite:false 避免遮挡底层网格。

#### 2.3.12 涂色六角柱（Painted Hex）

源文件：`scene/WorkshopScene.ts` 的 `paintHex`

绘画模式下创建的 3D 可堆叠六角柱体：

| 属性 | 值 |
|---|---|
| 几何体 | `ExtrudeGeometry`（从六角 `Shape` 拉伸） |
| 拉伸参数 | `depth` 随堆叠高度递增（每次 +0.5），`bevelEnabled: false` |
| 材质 | `MeshStandardMaterial`，颜色由调色板选择，emissive 同色 intensity 0.15 |
| 最大高度 | 100（近似无上限，供创意搭建） |

可用颜色调色板：`0x22d3ee`（青）、`0x38bdf8`（天蓝）、`0x60a5fa`（蓝）、`0x818cf8`（靛蓝）、`0xa78bfa`（紫）、`0x2dd4bf`（青绿）。

#### 2.3.13 堆叠特效（Stack Effect）

源文件：`scene/WorkshopScene.ts` 的 `spawnStackEffect`

六角柱高度增加时的一次性脉冲动画：

| 属性 | 值 |
|---|---|
| 几何体 | `RingGeometry`，内径 0.5, 外径 1.5, 分段 6（六角形环） |
| 材质 | `MeshBasicMaterial`，使用堆叠色，opacity 0.8 |
| 动画 | 从堆叠高度处向外扩散并淡出 |

#### 2.3.14 环境漂浮粒子（Ambient Particles）

源文件：`scene/WorkshopScene.ts` 的 `createAmbientParticles`

全场景的氛围装饰粒子，与区域粒子系统（2.3.2）独立：

| 属性 | 值 |
|---|---|
| 粒子数量 | 60 |
| 几何体 | `BufferGeometry`（Float32Array 手动管理） |
| 材质 | `PointsMaterial`，颜色 `0x4ac8e8`，size 0.12，AdditiveBlending |
| 运动 | 缓慢环形漂移 + 上下浮动，各粒子相位/速度/半径随机 |

#### 2.3.15 文字贴片（Text Tile）

源文件：`scene/WorkshopScene.ts` 的 `addTextTile` / `createTextTileSprite`

用户可在任意六角格上放置的文字标签：

| 属性 | 值 |
|---|---|
| 实现方式 | Canvas 2D → `CanvasTexture` → `SpriteMaterial` → `Sprite` |
| Canvas 尺寸 | 动态（根据文字长度） |
| 定位 | 吸附到六角格中心，高度随涂色六角柱自动抬升 |
| 特效 | 深色半透明背景 + 文字阴影 |

#### 2.3.16 Git 状态标签（Git Label）

源文件：`scene/WorkshopScene.ts` 的 `createGitLabel`

| 属性 | 值 |
|---|---|
| 实现方式 | Canvas 256x48 → `CanvasTexture` → `Sprite` |
| 位置 | 区域六角平台前方边缘（y=0.15, z=2.5） |
| 用途 | 显示该区域对应仓库的 Git 状态信息 |
| 默认状态 | 隐藏，收到 Git 数据后显示 |

#### 2.3.17 工作站上下文标签（Station Context）

源文件：`scene/WorkshopScene.ts` 的 `createTextSprite`

| 属性 | 值 |
|---|---|
| 实现方式 | Canvas 512x96 → `CanvasTexture` → `Sprite` |
| 位置 | 工作站上方 y=2.5 |
| 用途 | 显示当前工作站正在处理的文件名/命令等上下文信息 |
| 文字自适应 | 字号从 28px 向下缩减直到文字宽度不超过 Canvas |

---

### 2.4 工作站布局

所有工作站在区域内的相对位置（以区域中心为原点）：

```
                    书架 (0, -4)
                   /            \
          天线 (-3, -3)      扫描仪 (3, -3)
              |                    |
     工作台 (-4, 0)   中心 (0,0)   书桌 (4, 0)
              |                    |
         传送门 (-3, 3)      任务板 (3, 3)
                   \            /
                   终端 (0, 4)
```

坐标格式为 `(x, z)`，y 轴为高度方向。

---

## 3. Three.js 几何体速查表

以下是项目中实际使用到的全部几何体类型：

| 几何体 | 构造函数签名 | 典型用途 | 项目中的使用实例 |
|---|---|---|---|
| `BoxGeometry` | `(width, height, depth)` | 方块：桌面、显示器、书本 | 工作站底座 1.5x0.8x1、CRT 框 1.1x0.8x0.3 |
| `SphereGeometry` | `(radius, wSeg, hSeg)` | 球：头部、眼球、灯泡 | 角色头 r=0.22、天线灯 r=0.03 |
| `CapsuleGeometry` | `(radius, length, capSeg, radSeg)` | 胶囊：身体、手臂 | 人形身体 r=0.25 len=0.4 |
| `CylinderGeometry` | `(radiusTop, radiusBot, height, radSeg)` | 圆柱：铅笔、塔杆、腿 | 机器人躯干 top=0.18 bot=0.22 |
| `TorusGeometry` | `(radius, tube, radSeg, tubeSeg)` | 圆环：齿轮、镜框、腰带 | 传送门环 r=0.6 tube=0.1 |
| `RingGeometry` | `(innerR, outerR, thetaSeg)` | 扁环：状态环、信号波 | 状态环 inner=0.35 outer=0.4 |
| `PlaneGeometry` | `(width, height)` | 平面：屏幕、面罩 | 面罩 0.32x0.18、屏幕 0.85x0.55 |
| `CircleGeometry` | `(radius, segments)` | 圆形平面：镜片、灯 | 镜片 r=0.26、六角气泡 6 段 |
| `ShapeGeometry` | `(shape)` | 自定义 2D 形状平面 | LED 眼睛（圆角矩形）、六角地板 |
| `ExtrudeGeometry` | `(shape, options)` | 2D 形状拉伸为 3D 柱体 | 涂色六角柱（depth 可堆叠） |
| `BufferGeometry` | 手动设置顶点数据 | 自定义几何体：曲线、粒子 | 嘴巴曲线、网格线、粒子系统 |

### 材质速查

| 材质 | 特点 | 用途 |
|---|---|---|
| `MeshStandardMaterial` | PBR 物理材质，响应灯光 | 实体部件（身体、桌面、金属件） |
| `MeshBasicMaterial` | 不受灯光影响，纯色/发光 | 发光元素（眼睛、指示灯、状态环） |
| `PointsMaterial` | 粒子点阵材质 | 粒子系统 |
| `SpriteMaterial` | 始终面向摄像机的贴图 | 文字标签、通知 |
| `LineBasicMaterial` | 线条材质 | 网格线、嘴巴曲线 |

### 关键材质属性

| 属性 | 类型 | 说明 |
|---|---|---|
| `color` | hex 数值 | 基础颜色，如 `0x2a3a4a` |
| `roughness` | 0-1 | 粗糙度，0=镜面反射，1=完全粗糙 |
| `metalness` | 0-1 | 金属感，0=非金属，1=纯金属 |
| `emissive` | hex 数值 | 自发光颜色 |
| `emissiveIntensity` | number | 自发光强度 |
| `transparent` | boolean | 启用透明度 |
| `opacity` | 0-1 | 透明度，需配合 `transparent: true` |
| `side` | THREE.FrontSide / DoubleSide | 渲染面，DoubleSide 双面渲染 |

---

## 4. 自制模型入门指南

### 4.1 三步法

**第一步：创建几何体 + 材质 = Mesh**

```typescript
import * as THREE from 'three'

// 创建一个球体作为头部
const geometry = new THREE.SphereGeometry(0.3, 16, 16)
const material = new THREE.MeshStandardMaterial({
  color: 0x4a90d9,
  roughness: 0.4,
  metalness: 0.6,
})
const head = new THREE.Mesh(geometry, material)
head.position.y = 1.0  // 放到身体上方
head.castShadow = true
```

**第二步：用 Group 组合多个部件**

```typescript
const robot = new THREE.Group()

// 身体
const body = new THREE.Mesh(
  new THREE.CylinderGeometry(0.2, 0.25, 0.4, 12),
  new THREE.MeshStandardMaterial({ color: 0x3a4a5a, metalness: 0.5 })
)
body.position.y = 0.6

// 组合
robot.add(head)
robot.add(body)
robot.scale.setScalar(1.0)

scene.add(robot)
```

**第三步：在渲染循环中添加动画**

```typescript
let time = 0

function animate(delta: number) {
  time += delta * 2

  // 上下浮动
  head.position.y = 1.0 + Math.sin(time) * 0.02

  // 缓慢旋转
  robot.rotation.y += delta * 0.5
}
```

### 4.2 材质选择指南

| 场景 | 推荐材质 | 原因 |
|---|---|---|
| 实体部件（身体、桌面） | `MeshStandardMaterial` | 响应灯光，有真实感 |
| 发光元素（眼睛、指示灯） | `MeshBasicMaterial` | 不受灯光影响，始终可见 |
| 半透明效果（镜片、光环） | `MeshBasicMaterial` + transparent | 半透明 + 自发光 |
| 金属质感 | `MeshStandardMaterial` + metalness > 0.5 | PBR 金属反射 |

### 4.3 常用技巧

**用 scale 制造椭球**

```typescript
const footGeometry = new THREE.SphereGeometry(0.07, 12, 8)
footGeometry.scale(1.2, 0.5, 1.3)  // 压扁成脚掌形状
```

**用 CylinderGeometry 的 segments 参数控制棱数**

```typescript
// 6 段 = 六棱柱（六角形柱体）
new THREE.CylinderGeometry(1, 1.2, 0.2, 6)

// 32 段 = 光滑圆柱
new THREE.CylinderGeometry(0.1, 0.1, 1.0, 32)
```

**用 CircleGeometry 的 segments 做正多边形**

```typescript
// 6 段 = 正六边形
new THREE.CircleGeometry(0.09, 6)

// 32 段 = 近似圆形
new THREE.CircleGeometry(0.5, 32)
```

**用 ShapeGeometry 做自定义 2D 形状**

```typescript
const shape = new THREE.Shape()
const w = 0.032, h = 0.045, r = 0.012

// 绘制圆角矩形
shape.moveTo(-w/2 + r, -h/2)
shape.lineTo(w/2 - r, -h/2)
shape.quadraticCurveTo(w/2, -h/2, w/2, -h/2 + r)
shape.lineTo(w/2, h/2 - r)
shape.quadraticCurveTo(w/2, h/2, w/2 - r, h/2)
shape.lineTo(-w/2 + r, h/2)
shape.quadraticCurveTo(-w/2, h/2, -w/2, h/2 - r)
shape.lineTo(-w/2, -h/2 + r)
shape.quadraticCurveTo(-w/2, -h/2, -w/2 + r, -h/2)

const geometry = new THREE.ShapeGeometry(shape)
```

**用 ExtrudeGeometry 把 2D 形状拉伸为 3D 柱体**

```typescript
const shape = new THREE.Shape()
for (let i = 0; i < 6; i++) {
  const angle = (Math.PI / 3) * i - Math.PI / 2
  const x = 10 * Math.cos(angle)
  const y = 10 * Math.sin(angle)
  i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y)
}
shape.closePath()

const geometry = new THREE.ExtrudeGeometry(shape, {
  depth: 2.0,         // 拉伸高度
  bevelEnabled: false, // 无倒角
})
```

**用 AdditiveBlending 做发光粒子**

```typescript
new THREE.PointsMaterial({
  color: 0x4ac8e8,
  size: 0.15,
  transparent: true,
  opacity: 0.8,
  blending: THREE.AdditiveBlending,
  depthWrite: false,  // 避免遮挡其他透明物体
})
```

### 4.4 动画缓动函数

项目中使用的缓动函数，可直接复用：

```typescript
// 平滑启停（慢 → 快 → 慢）
const easeInOut = (t: number): number =>
  t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2

// 快出（快 → 慢）
const easeOut = (t: number): number =>
  1 - Math.pow(1 - t, 3)

// 弹跳
const bounce = (t: number): number => {
  const n1 = 7.5625, d1 = 2.75
  if (t < 1 / d1) return n1 * t * t
  if (t < 2 / d1) return n1 * (t -= 1.5 / d1) * t + 0.75
  if (t < 2.5 / d1) return n1 * (t -= 2.25 / d1) * t + 0.9375
  return n1 * (t -= 2.625 / d1) * t + 0.984375
}

// 弹性（过冲回弹）
const elastic = (t: number): number => {
  if (t === 0 || t === 1) return t
  return Math.pow(2, -10 * t) * Math.sin((t - 0.075) * (2 * Math.PI) / 0.3) + 1
}
```

### 4.5 性能注意事项

- 控制几何体分段数（segments）：球体 16 段足以，不必 64
- 共享材质实例：颜色相同的部件用同一个 material 对象
- 组件销毁时必须调用 `geometry.dispose()` 和 `material.dispose()`，防止 GPU 内存泄漏
- 粒子系统用 `BufferGeometry` + `Float32Array` 手动管理，避免每帧创建新对象
- 文字标签用 Canvas → Sprite 方案，比 3D 文字几何体轻量得多
