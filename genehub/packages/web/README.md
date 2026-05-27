# @nodeskai/genehub-web

GeneHub Web 前端 -- AI 员工基因库的浏览与管理界面。

## 技术栈

- **框架**：React 19 + TypeScript
- **构建**：Vite
- **样式**：Tailwind CSS
- **UI 组件**：自建组件库（`src/components/ui/`）
- **图标**：Lucide React

## 页面

| 路由 | 页面 | 说明 |
|---|---|---|
| `/` | Home | 首页、分类导航、推荐基因 |
| `/browse` | Browse | 基因浏览、联邦搜索、标签过滤 |
| `/genes/:slug` | GeneDetail | 基因详情、版本列表、审核信息 |
| `/genomes` | GenomeBrowse | 基因组列表 |
| `/genomes/:slug` | GenomeDetail | 基因组详情、依赖关系 |
| `/settings/keys` | Settings | API Key 管理 |

## 目录结构

```
packages/web/
├── src/
│   ├── App.tsx               # 路由配置
│   ├── api/
│   │   └── client.ts         # API 请求封装
│   ├── pages/                # 页面组件
│   ├── components/           # 业务组件
│   │   ├── Layout.tsx        # 布局、导航、用户菜单
│   │   ├── GeneCard.tsx
│   │   ├── GenomeCard.tsx
│   │   ├── FederatedSearchCard.tsx
│   │   ├── CategoryNav.tsx
│   │   ├── ReviewList.tsx
│   │   ├── LucideIcon.tsx
│   │   └── ui/              # 基础 UI 组件
│   └── lib/                  # 工具函数
├── public/                   # 静态资源
└── package.json
```

## 开发

```bash
pnpm dev            # 开发模式（http://localhost:5173）
pnpm build          # 构建
pnpm preview        # 预览构建产物
```

开发模式下 API 请求通过 Vite proxy 转发到 `http://localhost:3000`（Registry 服务）。

## 部署

生产环境构建产物部署在 Registry 服务的 `public/` 目录下，由 Hono 静态文件中间件提供服务，不需要独立部署。
