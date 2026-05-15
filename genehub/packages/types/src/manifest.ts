import { z } from 'zod';
import { AuthorType, GeneCategory, GeneTag, ProductId } from './enums.js';

const SLUG_REGEX = /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/;
const SEMVER_REGEX = /^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$/;

export const AuthorSchema = z.object({
  type: AuthorType,
  name: z.string().max(128),
  ref: z.string().optional().default(''),
});
export type Author = z.infer<typeof AuthorSchema>;

export const CompatibilityEntrySchema = z.object({
  product: ProductId,
  min_version: z.string().optional().default('0.0.0'),
});
export type CompatibilityEntry = z.infer<typeof CompatibilityEntrySchema>;

export const DependencyEntrySchema = z.object({
  slug: z.string().regex(SLUG_REGEX),
  version: z.string(),
  optional: z.boolean().optional().default(false),
});
export type DependencyEntry = z.infer<typeof DependencyEntrySchema>;

export const SkillSchema = z.object({
  name: z.string().min(1).max(128),
  always: z.boolean().optional().default(false),
  content: z.string().optional(),
  file: z.string().optional(),
});
export type Skill = z.infer<typeof SkillSchema>;

export const RuleSchema = z.object({
  name: z.string().min(1).max(128),
  content: z.string(),
  applies_to: z.string().optional(),
});
export type Rule = z.infer<typeof RuleSchema>;

export const OpenClawConfigSchema = z.object({
  openclaw_config: z.record(z.unknown()).optional(),
  tool_allow: z.array(z.string()).optional(),
});

export const NanobotConfigSchema = z.object({
  capabilities: z.array(z.string()).optional(),
  requires: z
    .object({
      bins: z.array(z.string()).optional(),
      env: z.array(z.string()).optional(),
    })
    .optional(),
  always: z.boolean().optional(),
  os: z.array(z.string()).optional(),
  install: z
    .array(
      z.object({
        id: z.string(),
        kind: z.string(),
        formula: z.string().optional(),
        bins: z.array(z.string()).optional(),
        label: z.string().optional(),
      }),
    )
    .optional(),
});

export const GeneConfigSchema = z.object({
  common: z.record(z.unknown()).optional(),
  openclaw: OpenClawConfigSchema.optional(),
  nanobot: NanobotConfigSchema.optional(),
});
export type GeneConfig = z.infer<typeof GeneConfigSchema>;

export const McpServerSchema = z.object({
  name: z.string(),
  transport: z.enum(['stdio', 'http']).optional().default('stdio'),
  command: z.string().optional(),
  args: z.array(z.string()).optional(),
  env: z.record(z.string()).optional(),
  url: z.string().optional(),
  headers: z.record(z.string()).optional(),
});
export type McpServer = z.infer<typeof McpServerSchema>;

export const LearningScenarioSchema = z.object({
  title: z.string(),
  context: z.string(),
  expected_focus: z.string(),
});
export type LearningScenario = z.infer<typeof LearningScenarioSchema>;

export const LearningSchema = z.object({
  force_deep_learn: z.boolean().optional().default(false),
  objectives: z.array(z.string()).optional(),
  scenarios: z.array(LearningScenarioSchema).optional(),
});
export type Learning = z.infer<typeof LearningSchema>;

export const GeneManifestSchema = z.object({
  slug: z.string().regex(SLUG_REGEX, 'slug 必须为 kebab-case，3-64 字符'),
  name: z.string().min(1).max(128),
  version: z.string().regex(SEMVER_REGEX, '版本号必须符合 SemVer'),
  description: z.string(),
  short_description: z.string().max(256),
  category: GeneCategory,
  tags: z.array(GeneTag).min(1),
  icon: z.string().max(64).optional(),
  author: AuthorSchema.optional(),

  compatibility: z.array(CompatibilityEntrySchema).min(1),

  dependencies: z.array(DependencyEntrySchema).optional().default([]),
  synergies: z.array(z.string()).optional().default([]),

  skill: SkillSchema,
  rules: z.array(RuleSchema).optional().default([]),
  config: GeneConfigSchema.optional(),
  mcp_servers: z.array(McpServerSchema).optional().default([]),
  learning: LearningSchema.optional(),
});
export type GeneManifest = z.infer<typeof GeneManifestSchema>;
