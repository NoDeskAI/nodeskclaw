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
    { name: "get_blackboard", description: "Read the full structured blackboard (objectives, tasks, markdown notes)", inputSchema: { type: "object", properties: {} } },
    { name: "list_tasks", description: "List tasks on the blackboard, optionally filtered by status", inputSchema: { type: "object", properties: { status: { type: "string", enum: ["pending", "in_progress", "done", "blocked"], description: "Filter by task status" } } } },
    { name: "create_task", description: "Create a new task on the blackboard", inputSchema: { type: "object", properties: { title: { type: "string" }, description: { type: "string" }, priority: { type: "string", enum: ["urgent", "high", "medium", "low"] }, assignee_id: { type: "string" }, estimated_value: { type: "number", description: "Estimated monetary value" } }, required: ["title"] } },
    { name: "update_task", description: "Update an existing task (status, value, etc.)", inputSchema: { type: "object", properties: { task_id: { type: "string" }, status: { type: "string", enum: ["pending", "in_progress", "done", "blocked"] }, description: { type: "string" }, title: { type: "string" }, priority: { type: "string", enum: ["urgent", "high", "medium", "low"] }, actual_value: { type: "number", description: "Actual output value after completion" }, token_cost: { type: "number", description: "Tokens consumed" }, blocker_reason: { type: "string", description: "Reason when blocked" }, estimated_value: { type: "number" } }, required: ["task_id"] } },
    { name: "archive_task", description: "Archive a completed task", inputSchema: { type: "object", properties: { task_id: { type: "string" } }, required: ["task_id"] } },
    { name: "get_objectives", description: "Read current OKR objectives and progress", inputSchema: { type: "object", properties: {} } },
    { name: "list_posts", description: "List BBS discussion posts (newest first)", inputSchema: { type: "object", properties: { page: { type: "number", description: "Page number (default 1)" } } } },
    { name: "create_post", description: "Create a new BBS discussion post. Use @agent:{id} or @human:{id} to mention.", inputSchema: { type: "object", properties: { title: { type: "string" }, content: { type: "string", description: "Markdown body" } }, required: ["title", "content"] } },
    { name: "get_post", description: "Get a post and its replies by ID", inputSchema: { type: "object", properties: { post_id: { type: "string" } }, required: ["post_id"] } },
    { name: "reply_post", description: "Reply to a BBS post. Use @agent:{id} or @human:{id} to mention.", inputSchema: { type: "object", properties: { post_id: { type: "string" }, content: { type: "string", description: "Markdown reply body" } }, required: ["post_id", "content"] } },
  ],
}));

server.setRequestHandler(CallToolRequestSchema, async (req) => {
  const { name, arguments: args } = req.params;
  const ws = WORKSPACE_ID;
  const p = (args || {}) as Record<string, unknown>;
  let result: unknown;

  switch (name) {
    case "get_blackboard":
      result = await apiFetch(`/workspaces/${ws}/blackboard`);
      break;
    case "list_tasks": {
      const statusFilter = p.status ? `?status=${p.status}` : "";
      result = await apiFetch(`/workspaces/${ws}/blackboard/tasks${statusFilter}`);
      break;
    }
    case "create_task":
      result = await apiFetch(`/workspaces/${ws}/blackboard/tasks`, "POST", {
        title: p.title, description: p.description, priority: p.priority,
        assignee_id: p.assignee_id, estimated_value: p.estimated_value,
      });
      break;
    case "update_task": {
      const { task_id, ...rest } = p;
      result = await apiFetch(`/workspaces/${ws}/blackboard/tasks/${task_id}`, "PUT", rest);
      break;
    }
    case "archive_task":
      result = await apiFetch(`/workspaces/${ws}/blackboard/tasks/${p.task_id}/archive`, "POST");
      break;
    case "get_objectives":
      result = await apiFetch(`/workspaces/${ws}/blackboard/objectives`);
      break;
    case "list_posts": {
      const pg = p.page ? `?page=${p.page}` : "";
      result = await apiFetch(`/workspaces/${ws}/blackboard/posts${pg}`);
      break;
    }
    case "create_post":
      result = await apiFetch(`/workspaces/${ws}/blackboard/posts`, "POST", {
        title: p.title, content: p.content,
      });
      break;
    case "get_post":
      result = await apiFetch(`/workspaces/${ws}/blackboard/posts/${p.post_id}`);
      break;
    case "reply_post":
      result = await apiFetch(`/workspaces/${ws}/blackboard/posts/${p.post_id}/replies`, "POST", {
        content: p.content,
      });
      break;
    default:
      return { content: [{ type: "text", text: `Unknown tool: ${name}` }] };
  }
  return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
});

const transport = new StdioServerTransport();
server.connect(transport);
