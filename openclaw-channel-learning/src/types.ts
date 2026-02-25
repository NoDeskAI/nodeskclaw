export interface LearningAccountConfig {
  enabled?: boolean;
  callbackBaseUrl?: string;
  instanceId?: string;
}

export interface ResolvedLearningAccount {
  accountId: string;
  enabled: boolean;
  configured: boolean;
  callbackBaseUrl: string;
  instanceId: string;
}

export interface LearningTask {
  mode: "learn" | "create" | "forget";
  task_id: string;
  gene_slug?: string;
  gene_content?: string;
  learning?: {
    objectives?: string[];
    scenarios?: Array<{
      prompt: string;
      context?: string;
      expected_focus?: string[];
    }>;
  };
  creation_prompt?: string;
  /** Agent's personalized learning output (forget mode only). */
  learning_output?: string;
  /** How many times the gene has been used (forget mode only). */
  usage_count?: number;
  callback_url: string;
}

export interface LearningResult {
  task_id: string;
  instance_id: string;
  mode: "learn" | "create" | "forget";
  decision:
    | "direct_install" | "learned" | "failed" | "created"
    | "forgotten" | "simplified" | "forget_failed";
  content?: string;
  self_eval?: number;
  meta?: {
    gene_name?: string;
    gene_slug?: string;
    gene_description?: string;
    suggested_tags?: string[];
    suggested_category?: string;
    icon?: string;
  };
  reason?: string;
}
