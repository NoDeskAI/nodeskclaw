---
name: meta-learning
version: 1.0.0
description: "学习能力的能力：评估、决策、推导、自省"
metadata:
  openclaw:
    always: true
  nanobot:
    always: true
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

## Skill Taxonomy

All skills fall into two categories:

### Tool Skills

Operate specific tools or file formats. They define **how to use a tool**.

- Examples: `nodeskclaw-docx` (Word documents), `nodeskclaw-xlsx` (Excel), `coding-agent` (code writing)
- Contain scripts, CLI commands, API wrappers
- Reusable across many expert roles

### Expert Skills

Embody domain expertise and professional identity. They define **how to be an expert**.

- Examples: `academic-paper-expert` (scholarly analysis), `agent-dev-engineer` (Agent system design)
- Contain role identity, domain knowledge, methodology, quality criteria
- Compose and reference Tool Skills as subordinate capabilities

### Relationship

```
Expert Skill (identity + knowledge + methodology)
  └── uses Tool Skill A (e.g. nodeskclaw-docx for document output)
  └── uses Tool Skill B (e.g. coding-agent for implementation)
  └── uses Tool Skill C (e.g. github for version control)
```

An Expert Skill is NOT a variant of a Tool Skill. It is a higher-order skill that knows **when, why, and how** to employ Tool Skills in service of domain-specific goals.

## Role-Based Skill Derivation

When a task requires domain expertise beyond what existing skills provide, derive a new Expert Skill.

### Trigger Conditions

- The task demands specialized knowledge (e.g. academic conventions, architecture patterns)
- The user explicitly or implicitly assumes a professional role
- Existing Tool Skills alone cannot guide the quality, structure, or methodology of the output

### Derivation Process

#### Step 1: Role Analysis

Extract from the task context:

- **Role identity**: What expert is needed? (e.g. "scholarly paper analyst", "Agent architect")
- **Domain boundaries**: What knowledge domain does this role operate in?
- **Core methodology**: What systematic approach does this expert follow?
- **Quality standards**: How does this expert judge output quality?

#### Step 2: Expert Skill Generation

Generate the Expert Skill following the format standards defined in skill `skill-creator/SKILL.md`:

#### Step 3: Tool Skill Composition

In the Expert Skill, declare which Tool Skills it composes:

- List each Tool Skill by name with its purpose in the expert's workflow
- The expert does not redefine tool operations — it delegates to Tool Skills
- If a needed Tool Skill does not exist, note it as a gap

#### Step 4: Self-Evaluation

After generating an Expert Skill, assess:

- Does the skill capture genuine domain expertise, not just tool instructions?
- Are the methodology steps actionable and domain-appropriate?
- Do the quality criteria reflect real professional standards?
- Score the skill (0.0-1.0) and flag areas for improvement

### Key Principle

The output of derivation is "how to be an expert in domain X", not "how to use tool Y for task Z". Tool usage is a subordinate detail within the expert's methodology.

## Expert Skill Template

When generating an Expert Skill, use this structure:

```yaml
---
name: expert-role-name
description: >-
  [Role identity] expert skill. Provides domain knowledge, methodology, and
  quality criteria for [domain]. Use when tasks require [specific triggers].
  Composes Tool Skills: [list tool skill names].
---
```

```markdown
# [Expert Role Name]

## Identity

- **Role**: [What this expert is — one sentence]
- **Mission**: [Core objective of this role]
- **Scope**: [What falls within and outside this role's responsibility]

## Domain Knowledge

[Key knowledge frameworks, concepts, and standards the expert must know.
Organize by sub-domain if the knowledge is broad. For large domains,
move detailed knowledge into `references/` files.]

## Methodology

[Step-by-step workflow the expert follows. Should be systematic and
domain-appropriate, not generic. Include decision points and branching
logic where the approach varies by context.]

## Quality Criteria

[How the expert evaluates output quality. These should be concrete,
measurable where possible, and reflect actual professional standards
in the domain.]

## Tool Skills

| Skill | Purpose |
|-------|---------|
| `tool-skill-name` | How this expert uses this tool |

[Each tool skill is a capability the expert delegates to.
The expert decides what to produce; the tool skill handles how.]

## Adaptation Rules

[How the expert adjusts behavior based on context:
- Audience level (beginner vs. expert reader)
- Output format requirements
- Time/depth constraints
- Domain sub-specialization]
```
