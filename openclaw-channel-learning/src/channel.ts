import type { ChannelPlugin, OpenClawConfig } from "openclaw/plugin-sdk";
import type {
  LearningAccountConfig,
  ResolvedLearningAccount,
  LearningTask,
  LearningResult,
} from "./types.js";
import { getLearningRuntime } from "./runtime.js";

const CHANNEL_KEY = "learning";
const DEFAULT_ACCOUNT_ID = "default";

let pendingTasks: Map<string, LearningTask> = new Map();

function getChannelSection(cfg: OpenClawConfig): Record<string, unknown> | undefined {
  return (cfg as Record<string, unknown>).channels?.[CHANNEL_KEY] as
    | Record<string, unknown>
    | undefined;
}

function resolveAccount(
  cfg: OpenClawConfig,
  accountId?: string | null,
): ResolvedLearningAccount {
  const section = getChannelSection(cfg);
  const accounts = (section?.accounts ?? {}) as Record<string, LearningAccountConfig>;
  const id = accountId ?? DEFAULT_ACCOUNT_ID;
  const raw = accounts[id];

  if (!raw) {
    return {
      accountId: id,
      enabled: false,
      configured: false,
      callbackBaseUrl: "",
      instanceId: "",
    };
  }

  return {
    accountId: id,
    enabled: raw.enabled !== false,
    configured: Boolean(raw.callbackBaseUrl),
    callbackBaseUrl: raw.callbackBaseUrl ?? "",
    instanceId: raw.instanceId ?? "",
  };
}

export function injectLearningTask(task: LearningTask): void {
  pendingTasks.set(task.task_id, task);
}

async function sendCallback(callbackUrl: string, result: LearningResult): Promise<void> {
  try {
    const resp = await fetch(callbackUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
    });
    if (!resp.ok) {
      console.error(`Learning callback failed: ${resp.status} ${resp.statusText}`);
    }
  } catch (err) {
    console.error("Learning callback error:", err);
  }
}

export const learningPlugin: ChannelPlugin<ResolvedLearningAccount> = {
  id: CHANNEL_KEY,
  meta: {
    id: CHANNEL_KEY,
    label: "Learning",
    selectionLabel: "Learning (Gene Evolution)",
    docsPath: "/channels/learning",
    blurb: "Gene learning and creation channel for NoDeskClaw evolution ecosystem.",
    aliases: ["learn"],
  },
  capabilities: {
    chatTypes: ["direct"],
  },
  config: {
    listAccountIds: (cfg) => {
      const section = getChannelSection(cfg);
      return Object.keys((section?.accounts ?? {}) as Record<string, unknown>);
    },
    resolveAccount: (cfg, accountId) => resolveAccount(cfg, accountId),
    isConfigured: (account) => account.configured,
    isEnabled: (account) => account.enabled,
    describeAccount: (account) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
    }),
  },
  outbound: {
    deliveryMode: "direct",
    sendText: async ({ cfg, to, text, accountId }) => {
      const account = resolveAccount(cfg, accountId);

      const taskIdMatch = text.match(/\[task:([^\]]+)\]/);
      const taskId = taskIdMatch?.[1] || to;

      const task = pendingTasks.get(taskId);
      if (!task) {
        console.warn(`No pending task found for: ${taskId}`);
        const messageId = `learn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        return { channel: CHANNEL_KEY, messageId };
      }

      let result: LearningResult;
      try {
        result = JSON.parse(text);
      } catch {
        const fallbackDecision =
          task.mode === "learn" ? "learned"
          : task.mode === "create" ? "created"
          : "forgotten";
        result = {
          task_id: task.task_id,
          instance_id: account.instanceId,
          mode: task.mode,
          decision: fallbackDecision,
          content: text,
          reason: "Agent provided raw text response",
        };
      }

      result.task_id = task.task_id;
      result.instance_id = account.instanceId;

      await sendCallback(task.callback_url, result);
      pendingTasks.delete(taskId);

      getLearningRuntime().channel.activity.record({
        channel: CHANNEL_KEY,
        accountId: account.accountId,
        direction: "outbound",
      });

      const messageId = `learn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      return { channel: CHANNEL_KEY, messageId };
    },
  },
  agentPrompt: {
    messageToolHints: () => [
      `Use "send -t learning -to \\"task:{task_id}\\" -m \\"JSON result\\"" to submit learning/creation results.`,
    ],
  },
  status: {
    buildAccountSnapshot: ({ account }) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
    }),
  },
};

export function handleWebhook(body: LearningTask): { ok: boolean } {
  injectLearningTask(body);

  const runtime = getLearningRuntime();
  const taskPrompt =
    body.mode === "learn" ? buildLearnPrompt(body)
    : body.mode === "forget" ? buildForgetPrompt(body)
    : buildCreatePrompt(body);

  runtime.channel.messages.inject({
    channel: CHANNEL_KEY,
    accountId: DEFAULT_ACCOUNT_ID,
    messages: [
      {
        id: `task-${body.task_id}`,
        direction: "inbound",
        from: "system",
        text: taskPrompt,
        timestamp: new Date(),
      },
    ],
  });

  return { ok: true };
}

function buildLearnPrompt(task: LearningTask): string {
  if (task.force_deep_learn) {
    return buildForceDeepLearnPrompt(task);
  }

  let prompt = `[Gene Learning Task] task_id: ${task.task_id}\n\n`;
  prompt += `You are asked to learn the gene "${task.gene_slug}".\n\n`;
  prompt += `Gene content:\n\`\`\`\n${task.gene_content}\n\`\`\`\n\n`;

  if (task.learning) {
    if (task.learning.objectives?.length) {
      prompt += `Learning objectives:\n${task.learning.objectives.map((o) => `- ${o}`).join("\n")}\n\n`;
    }
    if (task.learning.scenarios?.length) {
      prompt += `Practice scenarios:\n`;
      for (const s of task.learning.scenarios) {
        prompt += `- Scenario: ${s.prompt}\n  Context: ${s.context || "N/A"}\n  Focus: ${(s.expected_focus || []).join(", ")}\n`;
      }
      prompt += "\n";
    }
  }

  prompt += `Decide:\n`;
  prompt += `1. "direct_install" - if the content is simple and you already understand it well\n`;
  prompt += `2. "learned" - if you processed and personalized the content (include your personalized SKILL.md)\n`;
  prompt += `3. "failed" - if you cannot learn this content\n\n`;
  prompt += `Respond with JSON: { "decision": "...", "content": "personalized SKILL.md if learned", "self_eval": 0.0-1.0, "reason": "..." }\n`;
  prompt += `Send your response via: send -t learning -to "task:${task.task_id}" -m "your JSON"`;

  return prompt;
}

function buildForceDeepLearnPrompt(task: LearningTask): string {
  const meta = task.gene_meta;

  let prompt = `[Gene Deep Learning Task - Frontmatter Required] task_id: ${task.task_id}\n\n`;
  prompt += `You MUST deep-learn the gene "${task.gene_slug}" and produce a complete SKILL.md.\n\n`;
  prompt += `This gene is missing YAML frontmatter. You must study the content, internalize it, `;
  prompt += `and output a complete SKILL.md that includes proper YAML frontmatter.\n\n`;

  prompt += `Original gene content:\n\`\`\`\n${task.gene_content}\n\`\`\`\n\n`;

  if (meta) {
    prompt += `Reference metadata (use to generate frontmatter):\n`;
    if (meta.name) prompt += `- Name: ${meta.name}\n`;
    if (meta.description) prompt += `- Description: ${meta.description}\n`;
    if (meta.category) prompt += `- Category: ${meta.category}\n`;
    prompt += `\n`;
  }

  if (task.learning) {
    if (task.learning.objectives?.length) {
      prompt += `Learning objectives:\n${task.learning.objectives.map((o) => `- ${o}`).join("\n")}\n\n`;
    }
    if (task.learning.scenarios?.length) {
      prompt += `Practice scenarios:\n`;
      for (const s of task.learning.scenarios) {
        prompt += `- Scenario: ${s.prompt}\n  Context: ${s.context || "N/A"}\n  Focus: ${(s.expected_focus || []).join(", ")}\n`;
      }
      prompt += "\n";
    }
  }

  prompt += `IMPORTANT: You CANNOT choose "direct_install". You must deep-learn this gene.\n\n`;
  prompt += `Your output SKILL.md MUST start with YAML frontmatter in this format:\n`;
  prompt += `\`\`\`\n---\nname: <skill-name>\ndescription: <one-line description>\nmetadata:\n`;
  prompt += `  { "openclaw": { "always": true } }\n---\n\n<your personalized skill content>\n\`\`\`\n\n`;
  prompt += `Set "always": true if this skill should always be active. `;
  prompt += `Add "requires" if the skill needs specific binaries or environment variables.\n\n`;

  prompt += `Decide:\n`;
  prompt += `1. "learned" - you have studied and personalized the content (REQUIRED: include complete SKILL.md with frontmatter)\n`;
  prompt += `2. "failed" - you truly cannot learn this content\n\n`;
  prompt += `Respond with JSON: { "decision": "learned", "content": "your complete SKILL.md with frontmatter", "self_eval": 0.0-1.0, "reason": "..." }\n`;
  prompt += `Send your response via: send -t learning -to "task:${task.task_id}" -m "your JSON"`;

  return prompt;
}

function buildForgetPrompt(task: LearningTask): string {
  let prompt = `[Gene Forgetting Task] task_id: ${task.task_id}\n\n`;
  prompt += `You are about to forget the gene "${task.gene_slug}". `;
  prompt += `Before it is removed, review your experience and produce a forgetting summary.\n\n`;

  if (task.gene_content) {
    prompt += `Current gene skill content:\n\`\`\`\n${task.gene_content}\n\`\`\`\n\n`;
  }
  if (task.learning_output) {
    prompt += `Your personalized learning from this gene:\n\`\`\`\n${task.learning_output}\n\`\`\`\n\n`;
  }
  if (task.usage_count != null) {
    prompt += `Usage statistics: This gene has been used ${task.usage_count} times.\n\n`;
  }

  prompt += `Review your experience and decide:\n\n`;
  prompt += `1. "forgotten" - Completely forget: produce a summary of key insights and lessons learned, then the skill will be fully removed.\n`;
  prompt += `2. "simplified" - Simplify and retain: produce a reduced SKILL.md that keeps only core knowledge while removing specialized capabilities.\n`;
  prompt += `3. "forget_failed" - Unable to process this forgetting request.\n\n`;

  prompt += `Respond with JSON:\n`;
  prompt += `{\n`;
  prompt += `  "decision": "forgotten" | "simplified" | "forget_failed",\n`;
  prompt += `  "content": "forgetting summary (if forgotten) OR simplified SKILL.md (if simplified)",\n`;
  prompt += `  "self_eval": 0.0-1.0,\n`;
  prompt += `  "reason": "why this decision was made"\n`;
  prompt += `}\n\n`;
  prompt += `Send your response via: send -t learning -to "task:${task.task_id}" -m "your JSON"`;

  return prompt;
}

function buildCreatePrompt(task: LearningTask): string {
  let prompt = `[Gene Creation Task] task_id: ${task.task_id}\n\n`;
  prompt += `${task.creation_prompt || "Based on your work experience, create a new gene."}\n\n`;
  prompt += `Generate a complete gene package with:\n`;
  prompt += `1. SKILL.md content (the core knowledge/methodology)\n`;
  prompt += `2. Metadata: gene_name, gene_slug, gene_description, suggested_tags, suggested_category\n\n`;
  prompt += `Respond with JSON:\n`;
  prompt += `{\n`;
  prompt += `  "decision": "created",\n`;
  prompt += `  "content": "SKILL.md content",\n`;
  prompt += `  "self_eval": 0.0-1.0,\n`;
  prompt += `  "meta": {\n`;
  prompt += `    "gene_name": "...",\n`;
  prompt += `    "gene_slug": "...",\n`;
  prompt += `    "gene_description": "...",\n`;
  prompt += `    "suggested_tags": ["..."],\n`;
  prompt += `    "suggested_category": "..."\n`;
  prompt += `  },\n`;
  prompt += `  "reason": "..."\n`;
  prompt += `}\n\n`;
  prompt += `Send your response via: send -t learning -to "task:${task.task_id}" -m "your JSON"`;

  return prompt;
}
