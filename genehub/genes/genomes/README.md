# 基因组目录

本目录存放多 Agent 协作单元（Office Unit）的基因组定义。每个基因组是一组基因的引用组合，用于将 Agent 塑造为特定角色。

## 目录结构

```
genomes/
├── README.md             # 本文件
├── agile-executor/       # 灵敏 -- 执行者基因组
│   └── genome.yaml
├── visionary-planner/    # 远见 -- 规划者基因组
│   └── genome.yaml
├── erudite-scholar/      # 渊博 -- 博学者基因组
│   └── genome.yaml
└── steadfast-guardian/   # 威严 -- 守护者基因组
    └── genome.yaml
```

## 基因组与基因的关系

- **基因**（Gene）：原子能力单元，存放在 `../skills/<slug>/`，包含 `gene.yaml` 和 `SKILL.md`。
- **基因组**（Genome）：基因的引用列表 + 可选的配置覆盖，不包含技能内容本身。

## 使用方法

通过 GeneHub CLI 管理基因组：

```bash
genehub genome publish ./genes/genomes/agile-executor   # 发布基因组到 Registry
genehub genome install agile-executor                    # 安装基因组（递归安装所有基因）
genehub genome list                                      # 搜索基因组
genehub genome info agile-executor                       # 查看基因组详情
```

本地的 `genome.yaml` 文件是基因组的源定义，发布后会存储到 Registry（DB + Gitea）。

## 已定义基因组

| slug | 名称 | 分类 | 角色 |
|------|------|------|------|
| agile-executor | 灵敏 -- 执行者基因组 | efficiency | 卓越执行者（Act 类型） |
| visionary-planner | 远见 -- 规划者基因组 | leadership | 远见规划者（Plan 类型） |
| erudite-scholar | 渊博 -- 博学者基因组 | knowledge | 博学者（Knowledge 类型） |
| steadfast-guardian | 威严 -- 守护者基因组 | governance | 守护者（Judge 类型） |
