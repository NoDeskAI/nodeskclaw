#!/usr/bin/env npx ts-node
/**
 * NoDeskClaw Topology Awareness MCP Server
 * Lets agents query neighbors, members, and workspace topology.
 */
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";

const API = process.env.NODESKCLAW_API_URL || "http://localhost:8000/api/v1";
const TOKEN = process.env.NODESKCLAW_TOKEN || "";
const WORKSPACE_ID = process.env.NODESKCLAW_WORKSPACE_ID || "";

async function apiFetch(path: string) {
  const res = await fetch(`${API}${path}`, {
    headers: { Authorization: `Bearer ${TOKEN}` },
  });
  return res.json();
}

const server = new Server({ name: "nodeskclaw-topology-awareness", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "get_topology", description: "Get complete workspace topology (nodes, edges, reachability)", inputSchema: { type: "object", properties: {} } },
    { name: "get_members", description: "List all workspace members (agents + humans) with status", inputSchema: { type: "object", properties: {} } },
    { name: "get_my_neighbors", description: "Get agents/humans directly reachable from my position", inputSchema: { type: "object", properties: { my_instance_id: { type: "string" } }, required: ["my_instance_id"] } },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  const ws = WORKSPACE_ID;
  let result: unknown;

  switch (name) {
    case "get_topology":
      result = await apiFetch(`/workspaces/${ws}/topology`);
      break;
    case "get_members":
      result = await apiFetch(`/workspaces/${ws}/members`);
      break;
    case "get_my_neighbors":
      result = await apiFetch(`/workspaces/${ws}/topology`).then((r: any) => {
        const nodes = r.data?.nodes || [];
        const edges = r.data?.edges || [];
        const myNode = nodes.find((n: any) => n.entity_id === (args as any).my_instance_id);
        if (!myNode) return { error: "Node not found" };
        const neighborIds = new Set<string>();
        for (const e of edges) {
          if (e.a_q === myNode.hex_q && e.a_r === myNode.hex_r) neighborIds.add(`${e.b_q},${e.b_r}`);
          if (e.b_q === myNode.hex_q && e.b_r === myNode.hex_r) neighborIds.add(`${e.a_q},${e.a_r}`);
        }
        return nodes.filter((n: any) => neighborIds.has(`${n.hex_q},${n.hex_r}`));
      });
      break;
    default:
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
server.connect(transport);
