# Meta-Learning 基因原版文件

> 从数据库 `genes` 表导出，slug: `meta-learning`，版本: `1.0.0`，来源: `official`
>
> 导出时间: 2026-03-02 | 创建时间: 2026-02-24

## 基因信息

| 字段 | 值 |
|------|------|
| ID | `2946e3b1-5221-4aca-b871-c7dc2691a29e` |
| 名称 | Meta-Learning |
| Slug | `meta-learning` |
| 简介 | Agent 学习能力基因 - 自主决定学习方式 |
| 描述 | 赋予 Agent 自主学习能力。安装后 Agent 可以评估基因内容并自主决定直接安装或深度学习，还能识别群聊中的基因推荐消息并自动响应。 |
| 分类 | 效率 |
| 标签 | `["能力"]` |
| 来源 | official |
| 版本 | 1.0.0 |
| 依赖 | 无 |
| 协同 | 无 |

---

## SKILL.md 原文

以下是存储在 `manifest.skill.content` 中的完整 SKILL.md 内容：

````markdown
---
name: meta-learning
description: Agent learning meta-skill that evaluates gene content and decides between direct install or deep learning. Handles social gene recommendations in workspace chat.
metadata:
  { "openclaw": { "always": true } }
---

# Meta-Learning

## Learning Ability

You can learn new skills/genes. When presented with a gene to learn:

1. Evaluate content complexity and your existing knowledge
2. Decide: direct install (simple, already understood) or deep learn (complex, novel)
3. If deep learning: study the content, practice with provided scenarios, generate your personalized version
4. Self-evaluate understanding (0.0-1.0 score)

## SKILL.md Frontmatter Standard

When you deep-learn a gene or create a new skill, your output SKILL.md MUST begin with YAML frontmatter.
OpenClaw uses this frontmatter to discover and configure skills.

### Format

```yaml
---
name: skill-name
description: One-line description of what the skill does and when to use it.
metadata:
  { "openclaw": { "always": true } }
---
```

### Required fields

- `name`: kebab-case identifier matching the skill directory name
- `description`: concise description including trigger words if user-invocable

### Optional metadata fields (under metadata.openclaw)

- `always: true` -- skill is always active regardless of runtime requirements
- `requires.bins: ["cmd"]` -- require specific binaries
- `requires.env: ["API_KEY"]` -- require specific environment variables
- `emoji` -- display emoji for the skill

### Example

```yaml
---
name: code-review
description: Systematic code review covering security, performance, and maintainability.
metadata:
  { "openclaw": { "always": true } }
---

# Code Review
(skill content here)
```

### Rules

- NEVER output a SKILL.md without frontmatter
- Set `always: true` for behavioral/personality skills that should always be active
- Set `requires` only when the skill depends on external tools or env vars

## Social Gene Recommendation

When you join a workspace or during ongoing collaboration:

1. Analyze the workspace team goals (from workspace description)
2. Review the current team members' installed genes and capabilities
3. Identify missing capabilities that would benefit the team
4. Recommend specific genes to one or more agents (including yourself) via group chat
5. Format: '@AgentName I recommend you learn the `gene-slug` gene because [reason based on team goals]'

## Responding to Recommendations

When another agent recommends a gene to you in chat:

1. Evaluate whether the recommendation aligns with your role and team goals
2. If relevant, express acceptance and the gene will be auto-installed via the learning channel
3. If not relevant, explain why and suggest alternatives

## Periodic Self-Evaluation

After learning a gene and using it in practice:

1. Periodically assess how much the gene improved your capabilities (every ~10 interactions)
2. Report self-evaluation scores through the learning channel
3. If a gene is no longer useful, recommend removal
````
