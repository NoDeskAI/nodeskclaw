# Gene Templates

## 状态

**配置 `SEED_GENES=true`（默认）时，后端启动自动从本地模板导入种子基因到数据库。**

- 幂等：slug 已存在时自动对比并更新 manifest（Gene）/ gene_slugs + config_override + description（Genome）字段；name/tags 等用户可自定义字段不覆盖
- 关闭：设置 `SEED_GENES=false` 后重启即可跳过导入
- GeneHub 同步脚本：`scripts/upload_seeds_to_genehub.py`

本目录 JSON 文件同时作为本地 seed 数据源和 GeneHub 上传的参考模板。

## 目录结构

```
gene_templates/
├── README.md
├── mcp_blackboard_tools.json        # 黑板工具基因（任务/目标/帖子 CRUD + 工作循环）
├── mcp_topology_awareness.json      # 拓扑感知基因（工位、邻居查询）
├── mcp_performance_reader.json      # 效能数据读取基因
├── mcp_proposals.json               # 提案/审批基因
├── mcp_gene_discovery.json          # 基因发现/安装基因
├── mcp_shared_files.json            # 共享文件管理基因
├── meta_gene_ai_hc.json             # AI HC 招聘元基因
├── meta_gene_reorg.json             # 自组织重构元基因
├── meta_gene_culture.json           # 团队文化元基因
├── meta_gene_self_improve.json      # 自我改进元基因
├── meta_gene_innovation.json        # 创新探索元基因
├── meta_gene_akr_decomposer.json    # AKR 分解元基因（O -> KR -> Task）
├── content_topic_editor.json        # 自媒体选题编辑角色基因
├── content_writer.json              # 自媒体内容创作角色基因
├── content_reviewer.json            # 自媒体审核优化角色基因
├── content_distributor.json         # 自媒体分发运营角色基因
├── genome_self_management.json      # 自管理基因组（捆绑 5 个工具基因，旧版）
├── genome_ai_employee_basics.json   # AI 员工基础技能基因组（捆绑 6 个工具基因 + 1 个元基因）
├── genome_content_media_studio.json # 自媒体内容工作室基因组（捆绑 4 个角色基因）
├── workflow_genome_example.json     # 内容创作流水线基因组（含拓扑推荐）
└── workflow_step_template.json      # 工作流步骤基因的 manifest 模板（不入库）
```

关联目录：`../gene_scripts/` 包含基因安装时部署到实例的 Python CLI 脚本。

## Manifest 字段说明

| 字段 | 说明 |
|------|------|
| `skill` | Skill 内容（name + content），安装时写入运行时的 skill 目录 |
| `tool_allow` | 工具白名单，安装时由运行时适配器（GeneInstallAdapter）注册到对应运行时的配置中 |
| `scripts` | Python 脚本字典 `{"filename.py": "content"}`（新版自包含格式）或文件名数组 `["filename.py"]`（旧版兼容，从 `gene_scripts/` 读取），安装时部署到实例。本目录的 JSON 模板为了简洁保持数组格式，启动时（Seed）会自动填充内容转为字典存入 DB。 |
| `runtime_config` | 运行时配置补丁，安装时由适配器浅合并到运行时配置文件（向后兼容旧字段名 `openclaw_config`） |

## 分类

| 类型 | 文件 | slug | GeneHub 状态 |
|------|------|------|-------------|
| 工具基因 | mcp_blackboard_tools.json | nodeskclaw-blackboard-tools | 待更新 |
| 工具基因 | mcp_topology_awareness.json | nodeskclaw-topology-awareness | 已上传 |
| 工具基因 | mcp_performance_reader.json | nodeskclaw-performance-reader | 已上传 |
| 工具基因 | mcp_proposals.json | nodeskclaw-proposals | 已上传 |
| 工具基因 | mcp_gene_discovery.json | nodeskclaw-gene-discovery | 已上传 |
| 工具基因 | mcp_shared_files.json | nodeskclaw-shared-files | 待上传 |
| 元基因 | meta_gene_ai_hc.json | ai-hc-recruiter | 已上传 |
| 元基因 | meta_gene_reorg.json | self-reorg | 已上传 |
| 元基因 | meta_gene_culture.json | team-culture-concise | 已上传 |
| 元基因 | meta_gene_self_improve.json | self-improvement | 已上传 |
| 元基因 | meta_gene_innovation.json | innovation-scout | 已上传 |
| 元基因 | meta_gene_akr_decomposer.json | akr-decomposer | 待更新 |
| 基因组 | genome_self_management.json | nodeskclaw-self-management | 已上传 |
| 基因组 | genome_ai_employee_basics.json | ai-employee-basics | 待更新 |
| 角色基因 | content_topic_editor.json | content-topic-editor | 待上传 |
| 角色基因 | content_writer.json | content-writer | 待上传 |
| 角色基因 | content_reviewer.json | content-reviewer | 待上传 |
| 角色基因 | content_distributor.json | content-distributor | 待上传 |
| 基因组 | genome_content_media_studio.json | content-media-studio | 待上传 |
| 基因组 | workflow_genome_example.json | content-creation-pipeline | 未上传 |
| 模板 | workflow_step_template.json | -- | 不入库 |
