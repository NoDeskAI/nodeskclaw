import type { OpenClawConfig } from "openclaw/plugin-sdk";
import type { AnyAgentTool } from "openclaw/plugin-sdk";
import { isProtocolDowngraded } from "./tunnel-client.js";

type ToolConfig = {
  apiUrl: string;
  token: string;
  workspaceId: string;
  instanceId: string;
};

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

  const rawUrl = account.apiUrl || process.env.NODESKCLAW_API_URL || "http://localhost:8000/api/v1";
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
  const res = await fetch(`${cfg.apiUrl}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${cfg.token}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

function jsonResult(payload: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(payload, null, 2) }],
    details: payload,
  };
}

function createBlackboardTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_blackboard",
    description:
      "Workspace blackboard operations: tasks, objectives, and BBS discussion posts.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: [
            "get_blackboard", "list_tasks", "create_task", "update_task", "archive_task",
            "get_objectives",
            "list_posts", "create_post", "get_post", "reply_post",
          ],
          description: "Which blackboard operation to perform.",
        },
        title: { type: "string", description: "Task/post title (create_task, create_post)." },
        description: { type: "string", description: "Task description (create_task / update_task)." },
        content: { type: "string", description: "Post/reply body in Markdown (create_post, reply_post). Use @agent:{id} or @human:{id} to mention." },
        priority: { type: "string", enum: ["urgent", "high", "medium", "low"], description: "create_task." },
        assignee_id: { type: "string", description: "create_task: assign to agent instance ID." },
        estimated_value: { type: "number", description: "create_task: estimated monetary value." },
        task_id: { type: "string", description: "update_task / archive_task: target task ID." },
        post_id: { type: "string", description: "get_post / reply_post: target post ID." },
        status: {
          type: "string",
          enum: ["pending", "in_progress", "done", "blocked"],
          description: "update_task: new task status.",
        },
        actual_value: { type: "number", description: "update_task: actual output value after completion." },
        token_cost: { type: "number", description: "update_task: tokens consumed for this task." },
        blocker_reason: { type: "string", description: "update_task: reason when status is blocked." },
        filter_status: { type: "string", description: "list_tasks: filter by status (pending/in_progress/done/blocked)." },
        page: { type: "number", description: "list_posts: page number (default 1)." },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      switch (p.action) {
        case "get_blackboard":
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/blackboard`));
        case "list_tasks": {
          const statusFilter = p.filter_status ? `?status=${p.filter_status}` : "";
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/blackboard/tasks${statusFilter}`));
        }
        case "create_task":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/tasks`, "POST", {
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
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/tasks/${p.task_id}`, "PUT", body),
          );
        }
        case "archive_task":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/tasks/${p.task_id}/archive`, "POST"),
          );
        case "get_objectives":
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/blackboard/objectives`));
        case "list_posts": {
          const pg = p.page ? `?page=${p.page}` : "";
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/blackboard/posts${pg}`));
        }
        case "create_post":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/posts`, "POST", {
              title: p.title,
              content: p.content,
            }),
          );
        case "get_post":
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}`));
        case "reply_post":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/posts/${p.post_id}/replies`, "POST", {
              content: p.content,
            }),
          );
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
          const data = topo.data as Record<string, unknown[]> | undefined;
          const nodes = (data?.nodes ?? []) as Record<string, unknown>[];
          const edges = (data?.edges ?? []) as Record<string, unknown>[];
          const myNode = nodes.find((n) => n.entity_id === p.my_instance_id);
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
            await apiFetch(cfg, `/workspaces/${ws}/performance/collect`, "POST"),
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
              `/workspaces/trust-policies/check?workspace_id=${ws}&agent_instance_id=${agentId}&action_type=${p.action_type}`,
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

function createSharedFilesTool(cfg: ToolConfig): AnyAgentTool {
  return {
    name: "nodeskclaw_shared_files",
    description:
      "Manage shared files in the workspace blackboard: list, read, write, delete files, create directories.",
    parameters: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: ["list_files", "read_file", "write_file", "delete_file", "mkdir"],
          description: "Which file operation to perform.",
        },
        parent_path: { type: "string", description: "list_files / write_file / mkdir: directory path (default '/')." },
        file_id: { type: "string", description: "read_file / delete_file: target file ID." },
        filename: { type: "string", description: "write_file: file name." },
        content: { type: "string", description: "write_file: base64-encoded file content." },
        content_type: { type: "string", description: "write_file: MIME type (default 'application/octet-stream')." },
        name: { type: "string", description: "mkdir: directory name." },
      },
      required: ["action"],
    },
    execute: async (_toolCallId, args) => {
      const p = args as Record<string, unknown>;
      const ws = cfg.workspaceId;
      switch (p.action) {
        case "list_files": {
          const pp = p.parent_path ? `?parent_path=${encodeURIComponent(p.parent_path as string)}` : "";
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/blackboard/files${pp}`));
        }
        case "read_file":
          return jsonResult(await apiFetch(cfg, `/workspaces/${ws}/blackboard/files/${p.file_id}/content`));
        case "write_file":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/files/upload`, "POST", {
              parent_path: p.parent_path || "/",
              filename: p.filename,
              content: p.content,
              content_type: p.content_type || "application/octet-stream",
            }),
          );
        case "delete_file":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/files/${p.file_id}`, "DELETE"),
          );
        case "mkdir":
          return jsonResult(
            await apiFetch(cfg, `/workspaces/${ws}/blackboard/files/mkdir`, "POST", {
              parent_path: p.parent_path || "/",
              name: p.name,
            }),
          );
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
    createSharedFilesTool(cfg),
  ];
}
