export type LearningMode = 'learn' | 'create' | 'forget';

export type LearningScenario = {
  title: string;
  context: string;
  expected_focus: string;
};

export type LearningTask = {
  mode: LearningMode;
  task_id: string;
  gene_slug: string;
  gene_name: string;
  gene_version: string;
  gene_content: string;
  gene_meta: {
    name: string;
    description: string;
    category: string;
    short_description: string;
  };
  learning?: {
    objectives?: string[];
    scenarios?: LearningScenario[];
    force_deep_learn?: boolean;
  };
  callback_path: string;
  created_at: string;
};

export type LearningDecision =
  | 'direct_install'
  | 'learned'
  | 'failed'
  | 'created'
  | 'forgotten'
  | 'simplified'
  | 'forget_failed';

export type LearningResult = {
  task_id: string;
  gene_slug: string;
  mode: LearningMode;
  decision: LearningDecision;
  content?: string;
  self_eval?: number;
  reason?: string;
  completed_at: string;
};
