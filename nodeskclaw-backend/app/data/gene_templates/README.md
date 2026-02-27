# Gene Templates

## 用途

存放预制的基因/基因组模板 JSON，用于：

1. **工作流步骤基因模板** (`workflow_step_template.json`)：定义工作流步骤基因的 SKILL.md 模板结构
2. **工作流基因组示例** (`workflow_genome_example.json`)：包含过道拓扑推荐的完整工作流基因组

## 目录结构

```
gene_templates/
├── README.md
├── workflow_step_template.json    # 工作流步骤基因的 manifest 模板
└── workflow_genome_example.json   # 内容创作流水线基因组示例（含拓扑推荐）
```

## 使用方法

基因组的 `config_override.topology_recommendation` 字段包含拓扑推荐，
前端在安装基因组时可以读取该字段，向用户展示推荐的 Agent 布局和过道配置。
