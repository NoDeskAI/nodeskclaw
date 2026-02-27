import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { nodeskclawPlugin } from "./src/channel.js";
import { setNoDeskClawRuntime } from "./src/runtime.js";
import { startSSEServer } from "./src/sse-server.js";
import { createNoDeskClawTools } from "./src/tools.js";

const plugin = {
  id: "nodeskclaw",
  name: "NoDeskClaw",
  description: "NoDeskClaw workspace agent collaboration channel",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setNoDeskClawRuntime(api.runtime);
    api.registerChannel({ plugin: nodeskclawPlugin });
    startSSEServer();
    for (const tool of createNoDeskClawTools(api.config)) {
      api.registerTool(tool, { optional: true });
    }
  },
};

export default plugin;
