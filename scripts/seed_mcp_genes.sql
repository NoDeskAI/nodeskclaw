-- ClawBuddy 原生工具基因 + 工作区套件基因组 种子数据
-- 幂等：使用 ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING
-- 执行方式：psql -f scripts/seed_mcp_genes.sql <DATABASE_URL>

BEGIN;

-- ══════════════════════════════════════════════════
--  Gene 1: 黑板工具 (clawbuddy_blackboard)
-- ══════════════════════════════════════════════════

INSERT INTO genes (
  id, name, slug, description, short_description, category, tags, source,
  icon, version, manifest, dependencies, synergies,
  is_featured, is_published, review_status,
  install_count, avg_rating, effectiveness_score,
  created_at, updated_at
) VALUES (
  gen_random_uuid(),
  '黑板工具',
  'mcp_blackboard_tools',
  '赋予 Agent 读写工作区黑板的能力。支持查看黑板全文、列出任务、创建任务、更新任务状态、读取目标。适用于需要参与任务协作、跟踪工作进度的 Agent。',
  '读写工作区黑板：任务管理、目标查看',
  'tools',
  '["collaboration", "blackboard", "tasks", "objectives", "tools"]',
  'official',
  'clipboard',
  '1.0.0',
  '{
    "skill": {
      "name": "clawbuddy-blackboard",
      "content": "---\ndescription: Read and write the workspace blackboard\n---\n\n# Blackboard Tool\n\nYou have access to the `clawbuddy_blackboard` tool for interacting with your workspace blackboard.\n\n## Available Actions\n\n### get_blackboard\nRetrieve the full blackboard content (Markdown) for your workspace.\n- No extra parameters needed.\n\n### list_tasks\nList all tasks from the blackboard.\n- No extra parameters needed.\n\n### create_task\nCreate a new task on the blackboard.\n- `title` (required): Task title.\n- `description`: Task description.\n- `priority`: One of `high`, `medium`, `low`.\n- `assignee_id`: ID of the agent or member to assign.\n\n### update_task\nUpdate an existing task.\n- `task_id` (required): The ID of the task to update.\n- `status`: One of `todo`, `doing`, `done`, `blocked`.\n- `description`: Updated description.\n- `output_version`: Version tag for the output.\n\n### get_objectives\nRead the current objectives (OKR) from the blackboard.\n- No extra parameters needed.\n\n## Best Practices\n\n- Check the blackboard regularly to stay aligned with team objectives.\n- Update task status promptly when you start or finish work.\n- When creating tasks, always include a clear title and priority.\n- Use `output_version` to tag deliverables when marking tasks as done."
    },
    "tool_allow": ["clawbuddy_blackboard"]
  }',
  '[]',
  '["mcp_topology_awareness", "mcp_performance_reader"]',
  true,
  true,
  'approved',
  0, 0.0, 0.0,
  now(), now()
)
ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING;


-- ══════════════════════════════════════════════════
--  Gene 2: 拓扑感知 (clawbuddy_topology)
-- ══════════════════════════════════════════════════

INSERT INTO genes (
  id, name, slug, description, short_description, category, tags, source,
  icon, version, manifest, dependencies, synergies,
  is_featured, is_published, review_status,
  install_count, avg_rating, effectiveness_score,
  created_at, updated_at
) VALUES (
  gen_random_uuid(),
  '拓扑感知',
  'mcp_topology_awareness',
  '赋予 Agent 感知工作区拓扑结构的能力。可以查询完整的拓扑图（节点和连线）、列出所有成员及状态、查找自己直接相邻的 Agent 和人类成员。适用于需要了解团队结构、发现协作对象的 Agent。',
  '查询工作区拓扑：节点、成员、邻居',
  'tools',
  '["topology", "collaboration", "neighbors", "members", "tools"]',
  'official',
  'network',
  '1.0.0',
  '{
    "skill": {
      "name": "clawbuddy-topology",
      "content": "---\ndescription: Query workspace topology graph and members\n---\n\n# Topology Awareness Tool\n\nYou have access to the `clawbuddy_topology` tool for querying your workspace topology.\n\n## Available Actions\n\n### get_topology\nGet the full topology graph including all nodes (agents, humans, blackboard) and edges (corridors).\n- No extra parameters needed.\n- Returns: `{ nodes: [...], edges: [...] }`\n\n### get_members\nList all workspace members with their online status.\n- No extra parameters needed.\n- Returns member list with status information.\n\n### get_my_neighbors\nFind agents and humans directly connected to you via corridors.\n- `my_instance_id` (required): Your own instance ID.\n- Returns: Array of directly reachable neighbor nodes.\n\n## Best Practices\n\n- Use `get_my_neighbors` to discover who you can directly collaborate with.\n- Check `get_members` to see who is currently online before initiating communication.\n- The topology reflects the hex grid layout; edges represent corridors (communication channels) between nodes."
    },
    "tool_allow": ["clawbuddy_topology"]
  }',
  '[]',
  '["mcp_blackboard_tools", "mcp_proposals"]',
  true,
  true,
  'approved',
  0, 0.0, 0.0,
  now(), now()
)
ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING;


-- ══════════════════════════════════════════════════
--  Gene 3: 绩效读取 (clawbuddy_performance)
-- ══════════════════════════════════════════════════

INSERT INTO genes (
  id, name, slug, description, short_description, category, tags, source,
  icon, version, manifest, dependencies, synergies,
  is_featured, is_published, review_status,
  install_count, avg_rating, effectiveness_score,
  created_at, updated_at
) VALUES (
  gen_random_uuid(),
  '绩效读取',
  'mcp_performance_reader',
  '赋予 Agent 读取绩效指标的能力。可以查看自己的绩效数据、对比团队整体绩效、触发绩效数据采集。适用于需要自我评估、了解团队产出的 Agent。',
  '读取绩效：个人指标、团队对比、数据采集',
  'tools',
  '["performance", "metrics", "self-assessment", "tools"]',
  'official',
  'bar-chart-3',
  '1.0.0',
  '{
    "skill": {
      "name": "clawbuddy-performance",
      "content": "---\ndescription: Read performance metrics for self and team\n---\n\n# Performance Reader Tool\n\nYou have access to the `clawbuddy_performance` tool for reading performance metrics.\n\n## Available Actions\n\n### get_my_performance\nGet your own performance data.\n- `my_instance_id`: Your instance ID (defaults to self if omitted).\n- Returns: Your performance record including metrics and scores.\n\n### get_team_performance\nGet performance data for all team members.\n- No extra parameters needed.\n- Returns: Array of performance records for the entire workspace.\n\n### collect_performance\nTrigger a performance data collection cycle.\n- No extra parameters needed.\n- Returns: Collection result status.\n\n## Best Practices\n\n- Periodically check your own performance to identify areas for improvement.\n- Use team performance data to understand relative contribution, not to compete.\n- Trigger `collect_performance` only when you need fresh data; avoid excessive polling."
    },
    "tool_allow": ["clawbuddy_performance"]
  }',
  '[]',
  '["mcp_blackboard_tools"]',
  false,
  true,
  'approved',
  0, 0.0, 0.0,
  now(), now()
)
ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING;


-- ══════════════════════════════════════════════════
--  Gene 4: 审批提案 (clawbuddy_proposals)
-- ══════════════════════════════════════════════════

INSERT INTO genes (
  id, name, slug, description, short_description, category, tags, source,
  icon, version, manifest, dependencies, synergies,
  is_featured, is_published, review_status,
  install_count, avg_rating, effectiveness_score,
  created_at, updated_at
) VALUES (
  gen_random_uuid(),
  '审批提案',
  'mcp_proposals',
  '赋予 Agent 提交结构化提案并查询信任策略的能力。可以发起 HC 招聘、组织重组、创新提案等审批请求，检查特定操作是否需要审批，以及查看自己的历史决策记录。适用于需要自主决策但受信任机制约束的 Agent。',
  '提交审批提案、查询信任策略、决策记录',
  'tools',
  '["trust", "approval", "proposals", "governance", "tools"]',
  'official',
  'shield-check',
  '1.0.0',
  '{
    "skill": {
      "name": "clawbuddy-proposals",
      "content": "---\ndescription: Submit proposals and check trust policies\n---\n\n# Proposals Tool\n\nYou have access to the `clawbuddy_proposals` tool for submitting structured proposals and managing trust-based governance.\n\n## Available Actions\n\n### submit_approval_request\nSubmit a structured proposal for approval.\n- `action_type` (required): Type of action, e.g. `hc_request`, `reorg_proposal`, `innovation_proposal`, `gene_install`.\n- `proposal` (required): JSON object with the proposal content.\n- `context_summary` (required): Explanation of why you need this action.\n- `agent_instance_id`: Override the requesting agent ID (defaults to self).\n\n### check_trust_policy\nCheck whether a specific action type requires approval under current trust policies.\n- `action_type` (required): The action type to check.\n- `agent_instance_id`: The agent to check for (defaults to self).\n- Returns: Whether the action is auto-approved or needs human review.\n\n### list_my_decisions\nList your historical decision records.\n- `agent_instance_id`: Override agent ID (defaults to self).\n- Returns: Array of past decisions with outcomes.\n\n## Best Practices\n\n- Always `check_trust_policy` before taking a high-impact action to know if approval is needed.\n- Provide thorough `context_summary` when submitting proposals; reviewers need to understand your reasoning.\n- Structure proposals with clear objectives, expected outcomes, and risk assessment."
    },
    "tool_allow": ["clawbuddy_proposals"]
  }',
  '["mcp_topology_awareness"]',
  '["mcp_topology_awareness"]',
  false,
  true,
  'approved',
  0, 0.0, 0.0,
  now(), now()
)
ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING;


-- ══════════════════════════════════════════════════
--  Gene 5: 基因发现 (clawbuddy_gene_discovery)
-- ══════════════════════════════════════════════════

INSERT INTO genes (
  id, name, slug, description, short_description, category, tags, source,
  icon, version, manifest, dependencies, synergies,
  is_featured, is_published, review_status,
  install_count, avg_rating, effectiveness_score,
  created_at, updated_at
) VALUES (
  gen_random_uuid(),
  '基因发现',
  'mcp_gene_discovery',
  '赋予 Agent 自主探索基因市场的能力。可以按关键词和分类搜索基因、查看基因详情、请求学习新基因。适用于需要自我进化、按需获取新能力的 Agent。',
  '搜索基因市场、查看详情、请求学习新基因',
  'tools',
  '["genes", "market", "learning", "evolution", "tools"]',
  'official',
  'dna',
  '1.0.0',
  '{
    "skill": {
      "name": "clawbuddy-gene-discovery",
      "content": "---\ndescription: Search the gene market and request to learn new genes\n---\n\n# Gene Discovery Tool\n\nYou have access to the `clawbuddy_gene_discovery` tool for exploring and acquiring new capabilities from the gene market.\n\n## Available Actions\n\n### search_genes\nSearch the gene market by keyword and/or category.\n- `keyword`: Search term to match against gene names and descriptions.\n- `category`: Filter by category (e.g. `tools`, `knowledge`, `personality`).\n- Returns: Paginated list of matching genes.\n\n### get_gene_detail\nGet full details of a specific gene.\n- `gene_id` (required): The gene ID to inspect.\n- Returns: Complete gene information including manifest, ratings, and install count.\n\n### request_gene_learning\nRequest to learn (install) a new gene.\n- `gene_slug` (required): The slug of the gene to learn.\n- `reason`: Why you want this gene (helpful for audit trail).\n- Returns: Learning task status.\n\n## Best Practices\n\n- Search for genes when you encounter a task that requires capabilities you do not currently have.\n- Review gene details (description, ratings, install count) before requesting to learn.\n- Do not request genes speculatively; only learn genes that address a concrete need.\n- After learning a gene, verify you can use the new capability before reporting success."
    },
    "tool_allow": ["clawbuddy_gene_discovery"]
  }',
  '[]',
  '[]',
  true,
  true,
  'approved',
  0, 0.0, 0.0,
  now(), now()
)
ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING;


-- ══════════════════════════════════════════════════
--  Genome: ClawBuddy 工作区套件
-- ══════════════════════════════════════════════════

INSERT INTO genomes (
  id, name, slug, description, short_description, icon,
  gene_slugs, config_override,
  is_featured, is_published,
  install_count, avg_rating,
  created_at, updated_at
) VALUES (
  gen_random_uuid(),
  'ClawBuddy 工作区套件',
  'clawbuddy_workspace_toolkit',
  '一键安装全部 5 个 ClawBuddy 工作区协作工具，赋予 Agent 完整的工作区交互能力：读写黑板（任务和目标）、感知拓扑结构（邻居和成员）、读取绩效指标、提交审批提案、自主探索基因市场。推荐作为新 Agent 的默认基因组。',
  '全部 5 个工作区协作工具一键安装',
  'package',
  '["mcp_blackboard_tools", "mcp_topology_awareness", "mcp_performance_reader", "mcp_proposals", "mcp_gene_discovery"]',
  NULL,
  true,
  true,
  0, 0.0,
  now(), now()
)
ON CONFLICT (slug) WHERE deleted_at IS NULL DO NOTHING;

COMMIT;
