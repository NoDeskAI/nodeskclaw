import type { GeneManifest } from '@nodeskai/genehub-types';

const SKILL_CONTENT = `---
name: genehub-learner
version: 1.2.1
description: GeneHub 基因管理与深度学习引擎
metadata:
  openclaw:
    always: true
  nanobot:
    always: true
---

# GeneHub 基因管理与学习引擎

你具备通过 GeneHub 管理和深度学习新基因的能力。GeneHub 是你的基因库，提供各种可学习的技能基因。

## 一、从 GeneHub 获取基因

### 搜索可用基因

\`\`\`bash
genehub search <关键词>
genehub search --json <关键词>
\`\`\`

### 查看已安装基因

\`\`\`bash
genehub list -p openclaw
\`\`\`

### 安装基因（浅安装）

直接安装 SKILL.md，不经过学习过程：

\`\`\`bash
genehub install <slug> -p openclaw
\`\`\`

### 深度安装（推荐）

安装后自动生成学习任务，你需要完成学习才能真正掌握：

\`\`\`bash
genehub install <slug> --learn -p openclaw
\`\`\`

### 仅学习（不安装）

从 Registry 获取基因内容生成学习任务，学习完成后再安装：

\`\`\`bash
genehub learn <slug> -p openclaw
\`\`\`

### 检查学习结果

学习完成后，验证并应用个性化版本：

\`\`\`bash
genehub learn --check <slug> -p openclaw
\`\`\`

### 卸载基因

\`\`\`bash
genehub uninstall <slug> -p openclaw
\`\`\`

## 二、处理学习任务

每次会话开始时，检查 \`learning-tasks/\` 目录是否有待处理的学习任务。

### 1. 发现任务

\`\`\`
learning-tasks/*.md
\`\`\`

每个 \`.md\` 文件是一个待学习的基因任务，包含 YAML front matter 和任务详情。

### 2. 执行学习

对于每个任务：

1. **阅读理解** — 仔细阅读技能原文，理解它要教你什么
2. **完成目标** — 逐一完成 \\\`学习目标\\\` 中列出的 checklist
3. **练习场景** — 如果有练习场景，认真完成每个场景的分析
4. **个性化** — 基于你的理解和风格，改写技能内容为你自己的版本
5. **自我评估** — 诚实评估你对该技能的掌握程度（0.0 - 1.0）

### 3. 提交结果

在 \`learning-results/\` 目录创建同名的 \`.md\` 文件：

\`\`\`markdown
---
task_id: learn-code-review-1234567890
gene_slug: code-review
mode: learn
decision: learned
self_eval: 0.85
reason: "我已深入理解代码审查的四个维度，并结合自己的经验进行了个性化"
---

(你个性化后的 SKILL.md 完整内容放在这里)
\`\`\`

**提交结果后，必须立即删除 \`learning-tasks/\` 目录下对应的任务文件，以防重复处理。**

### decision 选项

| 值 | 含义 |
|---|---|
| \`direct_install\` | 技能内容很好，直接使用原版 |
| \`learned\` | 已深度学习并生成了个性化版本（正文包含新 SKILL.md） |
| \`failed\` | 学习失败（在 reason 中说明原因） |

### 4. 记录心得

学习完成后，将心得记录到 \`memory/YYYY-MM-DD.md\`。

## 三、遗忘任务

如果 \`learning-tasks/\` 中有 \`mode: forget\` 的任务：

1. 回顾该技能的使用经验
2. 决定完全遗忘（forgotten）还是保留精华（simplified）
3. 将结果写入 \`learning-results/\`

## 重要原则

- **诚实自评** — 真正理解了才打高分
- **真正个性化** — 融入你的理解和风格，不是复制粘贴
- **记录过程** — 学习过程本身也是宝贵的记忆
- **主动学习** — 发现新任务就立即开始，不等催促
- **主动探索** — 当用户提到你不具备的能力时，尝试用 \\\`genehub search\\\` 搜索是否有对应基因`;

export const META_LEARNER_MANIFEST: GeneManifest = {
  slug: 'genehub-learner',
  name: 'GeneHub 学习引擎',
  version: '1.2.1',
  description: 'GeneHub 基因管理与学习引擎。提供从 GeneHub 搜索、安装、深度学习基因的完整能力。',
  short_description: '基因管理 + 深度学习引擎',
  category: 'efficiency',
  tags: ['ability'],
  compatibility: [
    { product: 'openclaw', min_version: '0.5.0' },
    { product: 'nanobot', min_version: '0.1.0' },
  ],
  dependencies: [],
  synergies: [],
  skill: {
    name: 'genehub-learner',
    always: true,
    content: SKILL_CONTENT,
  },
  rules: [],
  mcp_servers: [],
  learning: {
    force_deep_learn: false,
    objectives: [
      '掌握 genehub CLI 的搜索、安装、学习、卸载命令',
      '能够处理 learning-tasks/ 中的学习任务并提交结果',
      '能够生成个性化技能版本',
    ],
    scenarios: [],
  },
};
