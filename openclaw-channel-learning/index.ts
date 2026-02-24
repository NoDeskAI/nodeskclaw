import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { emptyPluginConfigSchema } from "openclaw/plugin-sdk";
import { learningPlugin, handleWebhook } from "./src/channel.js";
import { setLearningRuntime } from "./src/runtime.js";

const plugin = {
  id: "learning",
  name: "Learning",
  description: "Gene learning and creation channel for ClawBuddy evolution ecosystem",
  configSchema: emptyPluginConfigSchema(),
  register(api: OpenClawPluginApi) {
    setLearningRuntime(api.runtime);
    api.registerChannel({ plugin: learningPlugin });

    api.runtime.http?.registerRoute("POST", "/extensions/learning/webhook", async (req) => {
      const body = await req.json();
      const result = handleWebhook(body);
      return new Response(JSON.stringify(result), {
        headers: { "Content-Type": "application/json" },
      });
    });
  },
};

export default plugin;
