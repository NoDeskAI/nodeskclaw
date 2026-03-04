import type { ChannelPlugin, OpenClawConfig } from "openclaw/plugin-sdk";
import type {
  NoDeskClawAccountConfig,
  ResolvedNoDeskClawAccount,
  CollaborationPayload,
} from "./types.js";
import { getNoDeskClawRuntime } from "./runtime.js";
import { broadcast } from "./sse-server.js";

const CHANNEL_KEY = "nodeskclaw";
const DEFAULT_ACCOUNT_ID = "default";

function getChannelSection(cfg: OpenClawConfig): Record<string, unknown> | undefined {
  return (cfg as Record<string, unknown>).channels?.[CHANNEL_KEY] as
    | Record<string, unknown>
    | undefined;
}

function resolveAccount(
  cfg: OpenClawConfig,
  accountId?: string | null,
): ResolvedNoDeskClawAccount {
  const section = getChannelSection(cfg);
  const accounts = (section?.accounts ?? {}) as Record<string, NoDeskClawAccountConfig>;
  const id = accountId ?? DEFAULT_ACCOUNT_ID;
  const raw = accounts[id];

  if (!raw) {
    return {
      accountId: id,
      enabled: false,
      configured: false,
      workspaceId: "",
      instanceId: "",
      apiToken: "",
    };
  }

  return {
    accountId: id,
    enabled: raw.enabled !== false,
    configured: Boolean(raw.workspaceId && raw.instanceId),
    workspaceId: raw.workspaceId ?? "",
    instanceId: raw.instanceId ?? "",
    apiToken: raw.apiToken ?? "",
  };
}

export const nodeskclawPlugin: ChannelPlugin<ResolvedNoDeskClawAccount> = {
  id: CHANNEL_KEY,
  meta: {
    id: CHANNEL_KEY,
    label: "NoDeskClaw",
    selectionLabel: "DeskClaw (Cyber Office)",
    docsPath: "/channels/nodeskclaw",
    blurb: "DeskClaw cyber office AI employee collaboration channel.",
    aliases: ["cb"],
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
    isConfigured: (account, _cfg) => account.configured,
    isEnabled: (account, _cfg) => account.enabled,
    describeAccount: (account, _cfg) => ({
      accountId: account.accountId,
      enabled: account.enabled,
      configured: account.configured,
    }),
  },
  outbound: {
    deliveryMode: "direct",
    sendText: async ({ cfg, to, text, accountId }) => {
      const account = resolveAccount(cfg, accountId);

      const payload: CollaborationPayload = {
        workspace_id: account.workspaceId,
        source_instance_id: account.instanceId,
        target: to,
        text,
        depth: 0,
      };

      broadcast(payload);

      getNoDeskClawRuntime().channel.activity.record({
        channel: CHANNEL_KEY,
        accountId: account.accountId,
        direction: "outbound",
      });

      const messageId = `cb-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      return { channel: CHANNEL_KEY, messageId };
    },
  },
  agentPrompt: {
    messageToolHints: () => [
      `Use "send -t nodeskclaw -to \\"agent:{name}\\" -m \\"message\\"" to collaborate with other AI employees in the cyber office.`,
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
