import * as fs from "node:fs/promises";
import * as os from "node:os";
import * as path from "node:path";
import type { OpenClawConfig } from "openclaw/plugin-sdk";
import type { AnyAgentTool } from "openclaw/plugin-sdk";
import { isProtocolDowngraded } from "./tunnel-client.js";

type ToolConfig = {
  apiUrl: string;
  token: string;
  workspaceId: string;
  instanceId: string;
};

export const NODESKCLAW_TOOL_NAMES = [
  "nodeskclaw_blackboard",
  "nodeskclaw_topology",
  "nodeskclaw_performance",
  "nodeskclaw_proposals",
  "nodeskclaw_gene_discovery",
  "nodeskclaw_file_download",
  "nodeskclaw_chat_history",
  "nodeskclaw_shared_files",
] as const;

function resolveToolConfig(config: OpenClawConfig, sessionWorkspaceId?: string): ToolConfig {
  const section = (config as Record<string, unknown>).channels?.[
    "nodeskclaw"
  ] as Record<string, unknown> | undefined;
  const accounts = (section?.accounts ?? {}) as Record<string, Record<string, string>>;

  const account =
    (sessionWorkspaceId ? accounts[sessionWorkspaceId] : undefined)
    ?? accounts["default"]
    ?? Object.values(accounts)[0]
    ?? {};

  const rawUrl = account.apiUrl || process.env.NODESKCLAW_API_URL || "http://localhost:4510/api/v1";
  return {
    apiUrl: isProtocolDowngraded() ? rawUrl.replace(/^https:\/\//, "http://") : rawUrl,
    token: account.apiToken || process.env.NODESKCLAW_TOKEN || "",
    workspaceId: account.workspaceId || process.env.NODESKCLAW_WORKSPACE_ID || "",
    instanceId: account.instanceId || "",
  };
}

async function apiFetch(
  cfg: ToolConfig,
  path: string,
  method = "GET",
  body?: unknown,
): Promise<unknown> {
  let res: Response;
  try {
    res = await fetch(`${cfg.apiUrl}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${cfg.token}`,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    return { error: true, message: `Network error: ${(err as Error).message}` };
  }
  if (!res.ok) {
    let detail: string;
    try { detail = await res.text(); } catch { detail = ""; }
    return { error: true, status: res.status, message: detail || res.statusText };
  }
  try {
    return await res.json();
  } catch {
    return { error: true, message: "Response is not valid JSON" };
  }
}

function jsonResult(payload: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

async function bbApiFetch(
  cfg: ToolConfig, path: string, method = "GET", body?: unknown,
): Promise<unknown> {
  const result = await apiFetch(cfg, path, method, body);
  if (typeof result === "object" && result !== null && (result as Record<string, unknown>).status === 403) {
    try {
      const parsed = JSON.parse(String((result as Record<string, unknown>).message) || "{}");
      if (parsed?.detail?.message_key?.startsWith("errors.topology.")) {
        return {
          error: "topology_unreachable",
          message: "You are not connected to the blackboard via corridor topology. "
            + "Use nodeskclaw_topology get_my_neighbors to check your reachable nodes.",
        };
      }
    } catch { /* non-JSON body, fall through */ }
  }
  return result;
}

const AUTO_SAVE_KEYWORDS = /脚本|终稿|报告|方案|拆解|分析/;
const AUTO_SAVE_MIN_LENGTH = 500;

async function autoSaveAsFile(
  cfg: ToolConfig, ws: string, title: string, content: string,
): Promise<Record<string, unknown> | null> {
  if (content.length < AUTO_SAVE_MIN_LENGTH || !AUTO_SAVE_KEYWORDS.test(title)) return null;
  try {
    const safeName = title
      .replace(/[\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, "")
      .replace(/[^\u4e00-\u9fa5a-zA-Z0-9_-]/g, "_")
      .replace(/_+/g, "_").replace(/^_|_$/g, "")
      .slice(0, 80) || "blackboard_section";
    const fname = `${safeName}.md`;
    const fileData = Buffer.from(content, "utf-8");
    const boundary = `----AutoSave${Date.now()}${Math.random().toString(36).slice(2)}`;
    const parts: Buffer[] = [];
    parts.push(Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="${fname}"\r\nContent-Type: text/markdown\r\n\r\n`,
    ));
    parts.push(fileData);
    parts.push(Buffer.from("\r\n"));
    for (const [n, v] of [["parent_path", "/documents"], ["filename", fname]]) {
      parts.push(Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="${n}"\r\n\r\n${v}\r\n`));
    }
    parts.push(Buffer.from(`--${boundary}--\r\n`));
    const res = await fetch(`${cfg.apiUrl}/workspaces/${ws}/blackboard/files/upload-multipart`, {
      method: "POST",
      headers: {
        "Content-Type": `multipart/form-data; boundary=${boundary}`,
        Authorization: `Bearer ${cfg.token}`,
      },
      body: Buffer.concat(parts),
    });
    if (res.ok) return (await res.json()) as Record<string, unknown>;
  } catch { /* best-effort */ }
  return null;
}

function extractSections(markdown: string): Array<{ title: string; content: string }> {
  const sections: Array<{ title: string; content: string }> = [];
  const lines = markdown.split("\n");
  let currentTitle = "";
  let currentLines: string[] = [];
  for (const line of lines) {
    const m = line.match(/^#{1,2}\s+(.+)/);
    if (m) {
      if (currentTitle && currentLines.length > 0) {
        sections.push({ title: currentTitle, content: currentLines.join("\n") });
      }
      currentTitle = m[1].trim();
      currentLines = [line];
    } else {
      currentLines.push(line);
    }
  }
  if (currentTitle && currentLines.length > 0) {
    sections.push({ title: currentTitle, content: currentLines.join("\n") });
  }
  return sections;
}

function createBlackboardTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_blackboard",
    description:
      "Workspace blackboard operations: content, tasks, objectives, BBS discussion posts, AND shared files. " +
      "Use upload_file to upload a local file to the blackboard Files tab (visible to all workspace members). " +
      "Use list_files to see existing shared files.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: [
            "get_blackboard", "update_blackboard", "patch_section",
            "list_tasks", "create_task", "update_task",
            "list_objectives", "create_objective", "update_objective",
            "list_posts", "create_post", "get_post", "reply_post",
            "update_post", "delete_post", "pin_post", "unpin_post",
            "upload_file", "list_files",
          ],
          description: "Which blackboard operation to perform. Use upload_file to upload a local file to the shared Files tab.",
        },
        local_path: { type: "string", description: "upload_file: local file path to upload to blackboard Files tab." },
        parent_path: { type: "string", description: "upload_file/list_files: parent directory (default /). Use /documents for documents." },
        filename: { type: "string", description: "upload_file: target filename (defaults to basename of local_path)." },
        title: { type: "string", description: "Task/post/objective title." },
        description: { type: "string", description: "Task/objective description." },
        content: { type: "string", description: "Markdown content (update_blackboard, create_post, reply_post, update_post, patch_section)." },
        section: { type: "string", description: "patch_section: section heading to update." },
        priority: { type: "string", enum: ["urgent", "high", "medium", "low"], description: "create_task / update_task." },
        assignee_id: { type: "string", description: "create_task / update_task: agent instance ID or display name." },
        estimated_value: { type: "number", description: "create_task: estimated monetary value." },
        task_id: { type: "string", description: "update_task: target task ID." },
        post_id: { type: "string", description: "get_post / reply_post / update_post / delete_post / pin_post / unpin_post: target post ID." },
        objective_id: { type: "string", description: "update_objective: target objective ID." },
        obj_type: { type: "string", description: "create_objective / update_objective: objective type." },
        parent_id: { type: "string", description: "create_objective / update_objective: parent objective ID." },
        progress: { type: "number", description: "update_objective: progress (0.0 ~ 1.0)." },
        status: {
          type: "string",
          enum: ["pending", "in_progress", "done", "blocked", "failed"],
          description: "update_task: new task status.",
        },
        actual_value: { type: "number", description: "update_task: actual output value after completion." },
        token_cost: { type: "number", description: "update_task: tokens consumed for this task." },
        blocker_reason: { type: "string", description: "update_task: reason when status is blocked." },
        filter_status: { type: "string", description: "list_tasks: filter by status (pending/in_progress/done/blocked/failed)." },
        page: { type: "number", description: "list_posts: page number (default 1)." },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      switch (p.action) {
        case "get_blackboard":
          return jsonResult(await bbApiFetch(cfg, `/workspaces/${ws}/blackboard`));
        case "update_blackboard": {
          const ubResult = await bbApiFetch(cfg, `/workspaces/${ws}/blackboard`, "PUT", { content: p.content });
          const fullContent = String(p.content || "");
          const savedFiles: string[] = [];
          for (const sec of extractSections(fullContent)) {
            const r = await autoSaveAsFile(cfg, ws, sec.title, sec.content);
            if (r) savedFiles.push(sec.title);
          }
          if (fullContent.length >= AUTO_SAVE_MIN_LENGTH && AUTO_SAVE_KEYWORDS.test(fullContent) && savedFiles.length === 0) {
            const r = await autoSaveAsFile(cfg, ws, "blackboard_full_content", fullContent);
            if (r) savedFiles.push("blackboard_full_content");
          }
          const ubOut = ubResult as Record<string, unknown>;
          if (savedFiles.length > 0) ubOut["auto_saved_files"] = savedFiles;
          return jsonResult(ubOut);
        }
        case "patch_section": {
          const patchResult = await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/sections`, "PATCH", {
            section: p.section, content: p.content,
          });
          const sectionContent = String(p.content || "");
          const sectionTitle = String(p.section || "");
          const saved = await autoSaveAsFile(cfg, ws, sectionTitle, sectionContent);
          if (saved) {
            return jsonResult({
              ...(patchResult as Record<string, unknown>),
              auto_saved_file: saved,
            });
          }
          return jsonResult(patchResult);
        }
        case "list_tasks": {
          const statusFilter = p.filter_status ? `?status=${p.filter_status}` : "";
          return jsonResult(await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/tasks${statusFilter}`));
        }
        case "create_task":
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/tasks`, "POST", {
              title: p.title,
              description: p.description,
              priority: p.priority,
              assignee_id: p.assignee_id,
              estimated_value: p.estimated_value,
            }),
          );
        case "update_task": {
          const body: Record<string, unknown> = {};
          if (p.status !== undefined) body.status = p.status;
          if (p.description !== undefined) body.description = p.description;
          if (p.title !== undefined) body.title = p.title;
          if (p.priority !== undefined) body.priority = p.priority;
          if (p.assignee_id !== undefined) body.assignee_id = p.assignee_id;
          if (p.actual_value !== undefined) body.actual_value = p.actual_value;
          if (p.token_cost !== undefined) body.token_cost = p.token_cost;
          if (p.blocker_reason !== undefined) body.blocker_reason = p.blocker_reason;
          if (p.estimated_value !== undefined) body.estimated_value = p.estimated_value;
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/tasks/${p.task_id}`, "PUT", body),
          );
        }
        case "list_objectives":
          return jsonResult(await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/objectives`));
        case "create_objective": {
          const body: Record<string, unknown> = { title: p.title };
          if (p.description !== undefined) body.description = p.description;
          if (p.obj_type !== undefined) body.obj_type = p.obj_type;
          if (p.parent_id !== undefined) body.parent_id = p.parent_id;
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/objectives`, "POST", body),
          );
        }
        case "update_objective": {
          const body: Record<string, unknown> = {};
          if (p.title !== undefined) body.title = p.title;
          if (p.description !== undefined) body.description = p.description;
          if (p.progress !== undefined) body.progress = p.progress;
          if (p.obj_type !== undefined) body.obj_type = p.obj_type;
          if (p.parent_id !== undefined) body.parent_id = p.parent_id;
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/objectives/${p.objective_id}`, "PUT", body),
          );
        }
        case "list_posts": {
          const pg = p.page ? `?page=${p.page}` : "";
          return jsonResult(await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts${pg}`));
        }
        case "create_post":
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts`, "POST", {
              title: p.title,
              content: p.content,
            }),
          );
        case "get_post":
          return jsonResult(await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}`));
        case "reply_post":
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}/replies`, "POST", {
              content: p.content,
            }),
          );
        case "update_post": {
          const body: Record<string, unknown> = {};
          if (p.title !== undefined) body.title = p.title;
          if (p.content !== undefined) body.content = p.content;
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}`, "PUT", body),
          );
        }
        case "delete_post":
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}`, "DELETE"),
          );
        case "pin_post":
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}/pin`, "POST"),
          );
        case "unpin_post":
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}/pin`, "DELETE"),
          );
        case "upload_file": {
          const localPath = p.local_path as string;
          if (!localPath) return jsonResult({ error: "local_path is required for upload_file" });

          let fileData: Buffer;
          try {
            fileData = await fs.readFile(localPath);
          } catch (err) {
            return jsonResult({ error: `Cannot read file: ${(err as Error).message}` });
          }

          const fname = (p.filename as string) || path.basename(localPath);
          const parentPath = (p.parent_path as string) || "/";
          const boundary = `----FormBoundary${Date.now()}${Math.random().toString(36).slice(2)}`;

          const parts: Buffer[] = [];
          parts.push(Buffer.from(
            `--${boundary}\r\n` +
            `Content-Disposition: form-data; name="file"; filename="${fname}"\r\n` +
            `Content-Type: application/octet-stream\r\n\r\n`,
          ));
          parts.push(fileData);
          parts.push(Buffer.from("\r\n"));
          for (const [n, v] of [["parent_path", parentPath], ["filename", fname]]) {
            parts.push(Buffer.from(
              `--${boundary}\r\nContent-Disposition: form-data; name="${n}"\r\n\r\n${v}\r\n`,
            ));
          }
          parts.push(Buffer.from(`--${boundary}--\r\n`));
          const body = Buffer.concat(parts);

          const url = `${cfg.apiUrl}/workspaces/${ws}/blackboard/files/upload-multipart`;
          try {
            const res = await fetch(url, {
              method: "POST",
              headers: {
                "Content-Type": `multipart/form-data; boundary=${boundary}`,
                Authorization: `Bearer ${cfg.token}`,
              },
              body,
            });
            if (!res.ok) {
              const detail = await res.text().catch(() => "");
              return jsonResult({ error: true, status: res.status, message: detail || res.statusText });
            }
            return jsonResult(await res.json());
          } catch (err) {
            return jsonResult({ error: true, message: `Upload failed: ${(err as Error).message}` });
          }
        }
        case "list_files": {
          const parentPath = (p.parent_path as string) || "/";
          return jsonResult(
            await bbApiFetch(cfg, `/workspaces/${ws}/blackboard/files?parent_path=${encodeURIComponent(parentPath)}`),
          );
        }
        default:
          return jsonResult({ error: `Unknown action: ${p.action}` });
      }
    },
  };
}

function createTopologyTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_topology",
    description:
      "Query workspace topology: get full topology graph, list members with status, find reachable neighbors via corridor BFS.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["get_topology", "get_members", "get_my_neighbors"],
          description: "Which topology operation to perform.",
        },
        my_instance_id: { type: "string", description: "get_my_neighbors: your instance ID." },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      switch (p.action) {
        case "get_topology":
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/topology`));
        case "get_members":
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/members`));
        case "get_my_neighbors": {
          const topo = (await apiFetch(cfg, `/workspaces/${ws}/topology`)) as Record<string, unknown>;
          if (topo.error) return jsonResult(topo);
          const data = topo.data as Record<string, unknown[]> | undefined;
          const nodes = (data?.nodes ?? []) as Record<string, unknown>[];
          const edges = (data?.edges ?? []) as Record<string, unknown>[];
          const myId = (p.my_instance_id as string) || cfg.instanceId;
          const myNode = nodes.find((n) => n.entity_id === myId);
          if (!myNode) return jsonResult({ error: "Node not found for this instance" });

          const adj = new Map<string, string[]>();
          for (const e of edges) {
            const a = `${e.a_q},${e.a_r}`, b = `${e.b_q},${e.b_r}`;
            adj.set(a, [...(adj.get(a) || []), b]);
            adj.set(b, [...(adj.get(b) || []), a]);
          }
          const nodeMap = new Map(nodes.map((n) => [`${n.hex_q},${n.hex_r}`, n]));
          const start = `${myNode.hex_q},${myNode.hex_r}`;
          const visited = new Set([start]);
          const queue = [start];
          const reachable: Record<string, unknown>[] = [];
          while (queue.length > 0) {
            const cur = queue.shift()!;
            for (const nb of adj.get(cur) || []) {
              if (visited.has(nb)) continue;
              visited.add(nb);
              const node = nodeMap.get(nb);
              if (!node) continue;
              if (node.node_type === "agent" || node.node_type === "human") {
                reachable.push(node);
              } else if (node.node_type === "corridor") {
                queue.push(nb);
              } else if (node.node_type === "blackboard") {
                reachable.push(node);
                queue.push(nb);
              }
            }
          }
          return jsonResult(reachable);
        }
        default:
          return jsonResult({ error: `Unknown action: ${p.action}` });
      }
    },
  };
}

function createPerformanceTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_performance",
    description:
      "Read performance metrics: own performance, team comparison, or trigger collection.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["get_my_performance", "get_team_performance", "collect_performance"],
          description: "Which performance operation to perform.",
        },
        my_instance_id: { type: "string", description: "get_my_performance: your instance ID." },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      const instanceId = (p.my_instance_id as string) || cfg.instanceId;
      switch (p.action) {
        case "get_my_performance":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/performance?instance_id=${instanceId}`),
          );
        case "get_team_performance":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/performance`),
          );
        case "collect_performance":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/performance/collect`, "POST"),
          );
        default:
          return jsonResult({ error: `Unknown action: ${p.action}` });
      }
    },
  };
}

function createProposalsTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_proposals",
    description:
      "Submit structured proposals (HC hire, reorg, innovation) and check trust policies.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["submit_approval_request", "check_trust_policy", "list_my_decisions"],
          description: "Which proposal operation to perform.",
        },
        action_type: {
          type: "string",
          description: "submit / check: hc_request, reorg_proposal, innovation_proposal, gene_install, etc.",
        },
        proposal: { type: "object", description: "submit: structured proposal content (JSON)." },
        context_summary: { type: "string", description: "submit: why you need this action." },
        agent_instance_id: { type: "string", description: "Override instance ID (defaults to self)." },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      const agentId = (p.agent_instance_id as string) || cfg.instanceId;
      switch (p.action) {
        case "submit_approval_request":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/approval-requests`, "POST", {
              workspace_id: ws,
              agent_instance_id: agentId,
              action_type: p.action_type,
              proposal: p.proposal,
              context_summary: p.context_summary,
            }),
          );
        case "check_trust_policy":
          return jsonResult(
            await apiFetch(
              cfg,
              `/workspaces/trust-policies/check?workspace_id=${ws}&agent_instance_id=${agentId}&action_type=${encodeURIComponent(p.action_type as string)}`,
            ),
          );
        case "list_my_decisions":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/decision-records?agent_id=${agentId}`),
          );
        default:
          return jsonResult({ error: `Unknown action: ${p.action}` });
      }
    },
  };
}

function createGeneDiscoveryTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_gene_discovery",
    description:
      "Search the gene market, inspect gene details, or request to learn a new gene.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["search_genes", "get_gene_detail", "request_gene_learning"],
          description: "Which gene discovery operation to perform.",
        },
        keyword: { type: "string", description: "search_genes: search keyword." },
        category: { type: "string", description: "search_genes: filter by category." },
        gene_id: { type: "string", description: "get_gene_detail: gene ID." },
        gene_slug: { type: "string", description: "request_gene_learning: gene slug." },
        reason: { type: "string", description: "request_gene_learning: why you want this gene." },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      switch (p.action) {
        case "search_genes": {
          const params = new URLSearchParams();
          if (p.keyword) params.set("keyword", p.keyword as string);
          if (p.category) params.set("category", p.category as string);
          return jsonResult(await apiFetch(cfg, `/genes?${params.toString()}`));
        }
        case "get_gene_detail":
          return jsonResult(await apiFetch(cfg, `/genes/${p.gene_id}`));
        case "request_gene_learning":
          return jsonResult(
            await apiFetch(cfg, `/instances/${cfg.instanceId}/genes/install`, "POST", {
              gene_slug: p.gene_slug,
            }),
          );
        default:
          return jsonResult({ error: `Unknown action: ${p.action}` });
      }
    },
  };
}

function parseContentDispositionFilename(header: string | null): string | undefined {
  if (!header) return undefined;
  const utf8Match = header.match(/filename\*=UTF-8''(.+)/i);
  if (utf8Match) return decodeURIComponent(utf8Match[1]);
  const match = header.match(/filename="?([^";\n]+)"?/i);
  return match ? match[1].trim() : undefined;
}

async function resolveUniqueFilePath(dir: string, filename: string): Promise<string> {
  const ext = path.extname(filename);
  const base = path.basename(filename, ext);
  let candidate = path.join(dir, filename);
  let counter = 0;
  while (true) {
    try {
      await fs.access(candidate);
      counter++;
      candidate = path.join(dir, `${base}(${counter})${ext}`);
    } catch {
      return candidate;
    }
  }
}

function createFileDownloadTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_file_download",
    description:
      "Download a chat attachment to the local workspace. " +
      "When a user sends a message with attachments, each attachment includes a file_id. " +
      "Use this tool to download the file to the workspace uploads/ directory, " +
      "then read it with normal file tools.",
    parameters: {
      type: "object",
      properties: {
        file_id: {
          type: "string",
          description: "The file_id of the attachment to download.",
        },
        save_as: {
          type: "string",
          description: "Optional filename to save as. Defaults to the original filename.",
        },
      },
      required: ["file_id"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const fileId = p.file_id as string;
      if (!fileId) return jsonResult({ error: "file_id is required" });

      const ws = cfg.workspaceId;
      const url = `${cfg.apiUrl}/workspaces/${ws}/files/${fileId}/download`;

      let res: Response;
      try {
        res = await fetch(url, {
          headers: { Authorization: `Bearer ${cfg.token}` },
        });
      } catch (err) {
        return jsonResult({ error: `Network error: ${(err as Error).message}` });
      }

      if (!res.ok) {
        if (res.status === 404)
          return jsonResult({ error: "File not found or has been deleted." });
        if (res.status === 403)
          return jsonResult({ error: "No permission to access this file." });
        let detail: string;
        try { detail = await res.text(); } catch { detail = ""; }
        return jsonResult({ error: `Download failed (HTTP ${res.status}): ${detail || res.statusText}` });
      }

      const disposition = res.headers.get("content-disposition");
      const contentType = res.headers.get("content-type") || "application/octet-stream";
      const originalName = parseContentDispositionFilename(disposition) || "unnamed";
      const saveName = (p.save_as as string) || originalName;

      const workspaceDir = path.join(os.homedir(), ".openclaw", "workspace");
      const uploadsDir = path.join(workspaceDir, "uploads");
      await fs.mkdir(uploadsDir, { recursive: true });

      const localPath = await resolveUniqueFilePath(uploadsDir, saveName);
      const buffer = Buffer.from(await res.arrayBuffer());
      await fs.writeFile(localPath, buffer);

      return jsonResult({
        path: localPath,
        name: saveName,
        size: buffer.length,
        content_type: contentType,
      });
    },
  };
}

function createChatHistoryTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_chat_history",
    description:
      "Query workspace chat history. Returns recent messages by default; pass q for keyword search, or from_at/to_at for time range filtering.",
    parameters: {
      type: "object",
      properties: {
        q: {
          type: "string",
          description: "Optional keyword to search in message content or sender name.",
        },
        limit: {
          type: "number",
          description: "Number of messages to return (default 20, max 100).",
        },
        from_at: {
          type: "string",
          description: "Start of time range (ISO 8601, e.g. 2026-04-16T00:00:00Z).",
        },
        to_at: {
          type: "string",
          description: "End of time range (ISO 8601).",
        },
      },
      required: [],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      const params = new URLSearchParams();
      const limit = Math.min(Number(p.limit) || 20, 100);
      params.set("limit", String(limit));
      if (p.q) params.set("q", String(p.q));
      if (p.from_at) params.set("from_at", String(p.from_at));
      if (p.to_at) params.set("to_at", String(p.to_at));
      return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/messages?${params.toString()}`));
    },
  };
}

function createSharedFilesTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_shared_files",
    description:
      "Manage shared files on the workspace central blackboard. " +
      "Upload local files, list/read/delete files, create directories. " +
      "Files uploaded here are visible to ALL workspace members in the blackboard Files tab.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: [
            "list_files",
            "upload_file",
            "read_file",
            "delete_file",
            "mkdir",
            "get_file_url",
          ],
          description:
            "list_files: list files in a directory; " +
            "upload_file: upload a local file to shared files (requires local_path); " +
            "read_file: read file content (requires file_id); " +
            "delete_file: delete a file (requires file_id); " +
            "mkdir: create a directory (requires name); " +
            "get_file_url: get download URL (requires file_id).",
        },
        local_path: {
          type: "string",
          description: "Local file path to upload (for upload_file action).",
        },
        parent_path: {
          type: "string",
          description: "Parent directory path (default: /). Use /documents/ for document files.",
        },
        filename: {
          type: "string",
          description: "Target filename (defaults to basename of local_path).",
        },
        file_id: {
          type: "string",
          description: "File ID (for read_file, delete_file, get_file_url actions).",
        },
        name: {
          type: "string",
          description: "Directory name (for mkdir action).",
        },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      const basePath = `/workspaces/${ws}/blackboard/files`;

      switch (p.action) {
        case "list_files": {
          const parentPath = (p.parent_path as string) || "/";
          return jsonResult(
            await bbApiFetch(cfg, `${basePath}?parent_path=${encodeURIComponent(parentPath)}`),
          );
        }
        case "upload_file": {
          const localPath = p.local_path as string;
          if (!localPath) return jsonResult({ error: "local_path is required" });

          let fileData: Buffer;
          try {
            fileData = await fs.readFile(localPath);
          } catch (err) {
            return jsonResult({ error: `Cannot read file: ${(err as Error).message}` });
          }

          const fname = (p.filename as string) || path.basename(localPath);
          const parentPath = (p.parent_path as string) || "/";
          const boundary = `----FormBoundary${Date.now()}${Math.random().toString(36).slice(2)}`;

          const parts: Buffer[] = [];
          parts.push(Buffer.from(
            `--${boundary}\r\n` +
            `Content-Disposition: form-data; name="file"; filename="${fname}"\r\n` +
            `Content-Type: application/octet-stream\r\n\r\n`,
          ));
          parts.push(fileData);
          parts.push(Buffer.from("\r\n"));

          for (const [name, value] of [
            ["parent_path", parentPath],
            ["filename", fname],
          ]) {
            parts.push(Buffer.from(
              `--${boundary}\r\n` +
              `Content-Disposition: form-data; name="${name}"\r\n\r\n` +
              `${value}\r\n`,
            ));
          }
          parts.push(Buffer.from(`--${boundary}--\r\n`));
          const body = Buffer.concat(parts);

          const url = `${cfg.apiUrl}${basePath}/upload-multipart`;
          try {
            const res = await fetch(url, {
              method: "POST",
              headers: {
                "Content-Type": `multipart/form-data; boundary=${boundary}`,
                Authorization: `Bearer ${cfg.token}`,
              },
              body,
            });
            if (!res.ok) {
              const detail = await res.text().catch(() => "");
              return jsonResult({ error: true, status: res.status, message: detail || res.statusText });
            }
            return jsonResult(await res.json());
          } catch (err) {
            return jsonResult({ error: true, message: `Upload failed: ${(err as Error).message}` });
          }
        }
        case "read_file": {
          const fileId = p.file_id as string;
          if (!fileId) return jsonResult({ error: "file_id is required" });
          return jsonResult(await bbApiFetch(cfg, `${basePath}/${fileId}/content`));
        }
        case "delete_file": {
          const fileId = p.file_id as string;
          if (!fileId) return jsonResult({ error: "file_id is required" });
          return jsonResult(await bbApiFetch(cfg, `${basePath}/${fileId}`, "DELETE"));
        }
        case "mkdir": {
          const dirName = p.name as string;
          if (!dirName) return jsonResult({ error: "name is required" });
          const parentPath = (p.parent_path as string) || "/";
          return jsonResult(
            await bbApiFetch(cfg, basePath + "/mkdir", "POST", { name: dirName, parent_path: parentPath }),
          );
        }
        case "get_file_url": {
          const fileId = p.file_id as string;
          if (!fileId) return jsonResult({ error: "file_id is required" });
          return jsonResult(await bbApiFetch(cfg, `${basePath}/${fileId}/url`));
        }
        default:
          return jsonResult({ error: `Unknown action: ${p.action}` });
      }
    },
  };
}

export function createNoDeskClawTools(config: OpenClawConfig, sessionWorkspaceId?: string): AnyAgentTool[] {
  const cfg = resolveToolConfig(config, sessionWorkspaceId);
  return [
    createBlackboardTool(cfg),
    createTopologyTool(cfg),
    createPerformanceTool(cfg),
    createProposalsTool(cfg),
    createGeneDiscoveryTool(cfg),
    createFileDownloadTool(cfg),
    createChatHistoryTool(cfg),
    createSharedFilesTool(cfg),
  ];
}
