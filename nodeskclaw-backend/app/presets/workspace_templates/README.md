# 工作区预设模板

本目录存放预设工作区模板的 JSON 定义，启动时自动种子化到数据库。

## 文件格式

每个 JSON 文件需包含：

- `name`: 模板名称
- `description`: 模板描述
- `topology_snapshot`: 拓扑快照（nodes + edges）
- `blackboard_snapshot`: 黑板快照（`content` Markdown 正文）
- `gene_assignments`: 基因分配列表（可选）

## 预设模板

| 文件 | 名称 | 说明 |
|------|------|------|
| software_team.json | 软件研发团队 | PM、Dev、QA 三角协作，过道连接 |
| content_studio.json | 内容工作室 | Writer、Editor、Designer 内容流水线 |
| research_lab.json | 研究实验室 | Researcher、Analyst 协作，共享黑板 |
