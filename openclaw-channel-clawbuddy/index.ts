import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { clawbuddyPlugin } from "./src/channel.js";
import { setClawBuddyRuntime } from "./src/runtime.js";
import { startSSEServer } from "./src/sse-server.js";

const plugin = {
  id: "clawbuddy",
  name: "ClawBuddy",
  description: "ClawBuddy workspace agent collaboration channel",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setClawBuddyRuntime(api.runtime);
    api.registerChannel({ plugin: clawbuddyPlugin });
    startSSEServer();
  },
};

export default plugin;
