#!/usr/bin/env npx ts-node
/**
 * NoDeskClaw Blackboard Tools MCP Server
 * Lets agents read/create/update tasks, read objectives, update output on the blackboard.
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

const server = new Server({ name: "nodeskclaw-blackboard-tools", version: "1.0.0" }, { capabilities: { tools: {} } });

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    { name: "get_blackboard", description: "Read the full structured blackboard (objectives, tasks, status, performance)", inputSchema: { type: "object", properties: {} } },
    { name: "list_tasks", description: "List all tasks on the blackboard", inputSchema: { type: "object", properties: {} } },
    { name: "create_task", description: "Create a new task on the blackboard", inputSchema: { type: "object", properties: { title: { type: "string" }, description: { type: "string" }, priority: { type: "string", enum: ["high", "medium", "low"] }, assignee_id: { type: "string" } }, required: ["title"] } },
    { name: "update_task", description: "Update an existing task (status, description, etc.)", inputSchema: { type: "object", properties: { task_id: { type: "string" }, status: { type: "string", enum: ["todo", "doing", "done", "blocked"] }, description: { type: "string" }, output_version: { type: "string" } }, required: ["task_id"] } },
    { name: "get_objectives", description: "Read current OKR objectives", inputSchema: { type: "object", properties: {} } },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  const ws = WORKSPACE_ID;
  let result: unknown;

  switch (name) {
    case "get_blackboard":
      result = await apiFetch(`/workspaces/${ws}/blackboard`);
      break;
    case "list_tasks":
      result = await apiFetch(`/workspaces/${ws}/blackboard`).then((r: any) => r.data?.tasks || []);
      break;
    case "create_task":
      result = await apiFetch(`/workspaces/${ws}/blackboard/tasks`, "POST", args);
      break;
    case "update_task": {
      const { task_id, ...rest } = args as any;
      result = await apiFetch(`/workspaces/${ws}/blackboard/tasks/${task_id}`, "PUT", rest);
      break;
    }
    case "get_objectives":
      result = await apiFetch(`/workspaces/${ws}/blackboard`).then((r: any) => r.data?.objectives || []);
      break;
    default:
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
server.connect(transport);
