# nodeskclaw-portal

NoDeskClaw 用户门户前端，基于 Vue 3 + Vite + TypeScript + Tailwind CSS 构建。

## 技术栈

| 依赖 | 版本 |
|------|------|
| Vue | 3 |
| Vite | 6 |
| TypeScript | 5.6+ |
| Tailwind CSS | 4 |
| Pinia | 2 |
| vue-i18n | 10 |
| lucide-vue-next | 图标库 |

## 目录结构

```
nodeskclaw-portal/
├── src/
│   ├── components/        # 通用组件
│   ├── i18n/              # 国际化（zh-CN、en-US）
│   │   └── locales/
│   ├── router/            # Vue Router 路由定义
│   ├── services/          # API 请求封装（axios）
│   ├── stores/            # Pinia 状态管理
│   └── views/             # 页面视图
│       ├── WorkspaceList.vue       # 工作区列表
│       ├── WorkspaceView.vue       # 工作区详情（拓扑图）
│       ├── InstanceList.vue        # 实例列表
│       ├── InstanceDetail.vue      # 实例详情
│       ├── OrgMembers.vue          # 组织成员管理
│       ├── GeneMarket.vue          # 基因市场
│       ├── EnterpriseFiles.vue     # 企业空间 — Agent 列表
│       ├── EnterpriseFileBrowser.vue  # 企业空间 — 文件浏览器
│       └── ...
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── vite.config.ts
```

## 启动

```bash
npm install
npm run dev      # 开发服务器
npm run build    # 生产构建
vue-tsc -b       # 类型检查
```

## 页面路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | 工作区列表 | 首页 |
| `/workspace/:id` | 工作区视图 | 拓扑图 + 群聊 |
| `/instances` | 实例列表 | 所有 Agent 实例 |
| `/instances/:id` | 实例详情 | 概览/基因/进化/MCP/Channel/设置/文件/成员 |
| `/members` | 组织成员 | 成员管理 |
| `/usage` | 用量 | 组织用量统计 |
| `/gene-market` | 基因市场 | 浏览安装基因 |
| `/enterprise-files` | 企业空间 | Agent 文件浏览（仅 org admin） |
| `/enterprise-files/:instanceId` | 文件浏览器 | 单个 Agent 的文件列表和预览 |

## 企业空间

企业空间允许组织管理员以只读方式浏览所有运行中 Agent 实例的文件。

- 入口：顶部导航"企业空间"（仅 `portal_org_role === 'admin'` 可见）
- Agent 列表展示所有实例，标注运行状态
- 文件浏览器：面包屑导航 + 文件列表 + 文本预览侧面板 + 下载
- 后端通过 PodFS（kubectl exec）实时读取文件

## 实例文件管理

实例详情页内的"文件"Tab，提供文件读写能力，仅实例 admin 可见。

- 入口：实例详情侧边栏"文件"（仅 `my_role === 'admin'` 可见）
- 文件浏览复用企业空间模式：面包屑 + 文件表格 + 过滤 + 下载
- 文本文件侧面板：默认只读预览，可切换编辑模式
- 保存时弹出确认对话框，提示修改可能影响运行中实例
- 后端 API：`/instances/{id}/files`，权限检查使用 `check_instance_access(InstanceRole.admin)`
