export type ClawBuddyAccountConfig = {
  enabled?: boolean;
  callbackUrl: string;
  workspaceId: string;
  instanceId: string;
  apiToken: string;
};

export type ClawBuddyChannelConfig = {
  accounts?: Record<string, ClawBuddyAccountConfig>;
};

export type ResolvedClawBuddyAccount = {
  accountId: string;
  enabled: boolean;
  configured: boolean;
  callbackUrl: string;
  workspaceId: string;
  instanceId: string;
  apiToken: string;
};

export type WebhookPayload = {
  workspace_id: string;
  source_instance_id: string;
  target: string;
  text: string;
  depth: number;
};
