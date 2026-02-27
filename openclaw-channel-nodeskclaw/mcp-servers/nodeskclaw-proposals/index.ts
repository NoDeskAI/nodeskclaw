#!/usr/bin/env npx ts-node
/**
 * NoDeskClaw Proposals MCP Server
 * Lets agents submit structured proposals (HC, reorg, innovation) and check status.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const API = process.env.NODESKCLAW_API_URL || "http://localhost:8000/api/v1";
const TOKEN = process.env.NODESKCLAW_TOKEN || "";
const WORKSPACE_ID = process.env.NODESKCLAW_WORKSPACE_ID || "";

async function apiFetch(path: string, method = "GET", body?: unknown) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${TOKEN}` },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

const server = new Server({ name: "nodeskclaw-proposals", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "submit_approval_request", description: "Submit an approval request (HC hire, reorg, innovation proposal) routed to human reviewers", inputSchema: { type: "object", properties: { agent_instance_id: { type: "string" }, action_type: { type: "string", description: "hc_request, reorg_proposal, innovation_proposal, gene_install, etc." }, proposal: { type: "object", description: "Structured proposal content (JSON)" }, context_summary: { type: "string" } }, required: ["agent_instance_id", "action_type", "proposal"] } },
    { name: "check_trust_policy", description: "Check if an action is already trusted (allow_always)", inputSchema: { type: "object", properties: { agent_instance_id: { type: "string" }, action_type: { type: "string" } }, required: ["agent_instance_id", "action_type"] } },
    { name: "list_my_decisions", description: "List my past decision records", inputSchema: { type: "object", properties: { agent_instance_id: { type: "string" } }, required: ["agent_instance_id"] } },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  const ws = WORKSPACE_ID;
  let result: unknown;

  switch (name) {
    case "submit_approval_request":
      result = await apiFetch(`/workspaces/${ws}/approval-requests`, "POST", args);
      break;
    case "check_trust_policy": {
      const a = args as any;
      result = await apiFetch(`/workspaces/${ws}/trust-policies/check?agent_instance_id=${a.agent_instance_id}&action_type=${a.action_type}`);
      break;
    }
    case "list_my_decisions": {
      const a = args as any;
      result = await apiFetch(`/workspaces/${ws}/decision-records?agent_id=${a.agent_instance_id}`);
      break;
    }
    default:
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
server.connect(transport);
