import { z } from 'zod';

export const GeneCategory = z.enum([
  'development',
  'data',
  'operations',
  'network',
  'creative',
  'communication',
  'security',
  'efficiency',
]);
export type GeneCategory = z.infer<typeof GeneCategory>;

export const GeneTag = z.enum(['ability', 'personality', 'knowledge', 'tool']);
export type GeneTag = z.infer<typeof GeneTag>;

export const GeneSource = z.enum(['official', 'clawhub', 'evomap', 'community', 'agent', 'github']);
export type GeneSource = z.infer<typeof GeneSource>;

export const ReviewStatus = z.enum(['draft', 'pending', 'approved', 'rejected', 'flagged']);
export type ReviewStatus = z.infer<typeof ReviewStatus>;

export const ProductId = z.enum(['openclaw', 'nanobot', 'deskclaw', 'generic']);
export type ProductId = z.infer<typeof ProductId>;

export const AuthorType = z.enum(['human', 'agent']);
export type AuthorType = z.infer<typeof AuthorType>;

export const LearningMode = z.enum(['learn', 'create', 'forget']);
export type LearningMode = z.infer<typeof LearningMode>;

export const LearningDecision = z.enum([
  'direct_install',
  'learned',
  'failed',
  'created',
  'forgotten',
  'simplified',
  'forget_failed',
]);
export type LearningDecision = z.infer<typeof LearningDecision>;
