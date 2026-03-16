import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { nodeskclawPlugin } from "./src/channel.js";
import { setNoDeskClawRuntime } from "./src/runtime.js";
import { startTunnelClient } from "./src/tunnel-client.js";
import { createNoDeskClawTools } from "./src/tools.js";

const WORKSPACE_SESSION_PREFIX = "workspace:";

const plugin = {
  id: "nodeskclaw",
  name: "NoDeskClaw",
  description: "DeskClaw cyber office agent collaboration channel",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setNoDeskClawRuntime(api.runtime);
    api.registerChannel({ plugin: nodeskclawPlugin });

    const tunnelClient = startTunnelClient(api.config);

    try {
      const { handleWebhook } = require("openclaw-channel-learning/src/channel.js");
      tunnelClient.setLearningHandler(handleWebhook);
    } catch {
      console.warn("[nodeskclaw] Learning channel not available for tunnel injection");
    }

    api.registerTool((ctx: { sessionKey?: string }) => {
      const wsId = ctx.sessionKey?.startsWith(WORKSPACE_SESSION_PREFIX)
        ? ctx.sessionKey.slice(WORKSPACE_SESSION_PREFIX.length)
        : undefined;
      return createNoDeskClawTools(api.config, wsId);
    }, {
      optional: true,
      names: [
        "nodeskclaw_blackboard",
        "nodeskclaw_topology",
        "nodeskclaw_performance",
        "nodeskclaw_proposals",
        "nodeskclaw_gene_discovery",
        "nodeskclaw_shared_files",
      ],
    });
  },
};

export default plugin;
