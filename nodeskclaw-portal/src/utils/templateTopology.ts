import type { AgentBrief, TopologyEdge } from '@/stores/workspace'

export interface TopoNode {
  hex_q: number
  hex_r: number
  node_type: 'blackboard' | 'corridor' | 'agent' | 'human'
  entity_id: string | null
  display_name: string
  extra: Record<string, unknown>
}

interface TemplateData {
  agent_specs: Record<string, unknown>[]
  human_specs: Record<string, unknown>[]
  topology_snapshot?: {
    nodes?: Record<string, unknown>[]
    edges?: Record<string, unknown>[]
  }
}

export function buildTopoNodes(data: TemplateData): TopoNode[] {
  const nodes: TopoNode[] = []
  const snap = data.topology_snapshot
  if (snap?.nodes) {
    for (const n of snap.nodes) {
      nodes.push({
        hex_q: n.hex_q as number,
        hex_r: n.hex_r as number,
        node_type: (n.node_type as TopoNode['node_type']) || 'corridor',
        entity_id: null,
        display_name: (n.display_name as string) || '',
        extra: {},
      })
    }
  }
  for (const s of data.agent_specs) {
    nodes.push({
      hex_q: s.hex_q as number,
      hex_r: s.hex_r as number,
      node_type: 'agent',
      entity_id: null,
      display_name: (s.display_name as string) || (s.label as string) || '',
      extra: {},
    })
  }
  for (const h of data.human_specs) {
    nodes.push({
      hex_q: h.hex_q as number,
      hex_r: h.hex_r as number,
      node_type: 'human',
      entity_id: null,
      display_name: (h.display_name as string) || '',
      extra: {},
    })
  }
  return nodes
}

export function buildTopoEdges(data: TemplateData): TopologyEdge[] {
  const snap = data.topology_snapshot
  if (!snap?.edges) return []
  return (snap.edges as Record<string, unknown>[]).map(e => ({
    a_q: e.a_q as number,
    a_r: e.a_r as number,
    b_q: e.b_q as number,
    b_r: e.b_r as number,
    auto_created: (e.auto_created as boolean) ?? false,
    direction: e.direction as TopologyEdge['direction'],
  }))
}

export function buildMockAgents(agentSpecs: Record<string, unknown>[]): AgentBrief[] {
  return agentSpecs.map((s, i) => ({
    instance_id: `tpl-${i}`,
    name: (s.display_name as string) || (s.label as string) || '',
    display_name: (s.display_name as string) || null,
    label: (s.label as string) || null,
    slug: null,
    status: 'idle',
    hex_q: s.hex_q as number,
    hex_r: s.hex_r as number,
    sse_connected: false,
    theme_color: null,
  }))
}

export function specGeneSlugs(spec: Record<string, unknown>): string[] {
  const s = spec.gene_slugs
  return Array.isArray(s) ? s : []
}

export function specGeneCount(spec: Record<string, unknown>): number {
  return specGeneSlugs(spec).length
}

export function specLlmProviders(spec: Record<string, unknown>): Array<{ provider: string; models: string[] }> {
  const raw = spec.llm_providers
  if (!Array.isArray(raw)) return []
  return raw.map((p: Record<string, unknown>) => ({
    provider: (p.provider as string) || '',
    models: Array.isArray(p.models) ? p.models.map((m: unknown) => String(m)) : [],
  }))
}

export function resourceSummary(spec: Record<string, unknown>): string {
  const r = spec.resources as Record<string, string> | undefined
  if (!r) return ''
  return [r.cpu_limit || r.cpu_request, r.mem_limit || r.mem_request].filter(Boolean).join(' / ')
}

export function agentKeysFromSpecs(specs: Record<string, unknown>[]): Set<string> {
  return new Set(specs.map(s => `${s.hex_q},${s.hex_r}`))
}

export function corridorKeysFromTopoNodes(
  topoSnapshot?: { nodes?: Record<string, unknown>[] },
): Set<string> {
  if (!topoSnapshot?.nodes) return new Set()
  return new Set(
    topoSnapshot.nodes
      .filter(n => n.node_type === 'corridor')
      .map(n => `${n.hex_q},${n.hex_r}`),
  )
}

export function allSelectableKeys(
  agentSpecs: Record<string, unknown>[],
  topoSnapshot?: { nodes?: Record<string, unknown>[] },
): Set<string> {
  const keys = agentKeysFromSpecs(agentSpecs)
  for (const k of corridorKeysFromTopoNodes(topoSnapshot)) keys.add(k)
  return keys
}

export function countAgentKeysInSelection(
  agentSpecs: Record<string, unknown>[],
  selectedKeys: Set<string>,
): number {
  return agentSpecs.filter(s => selectedKeys.has(`${s.hex_q},${s.hex_r}`)).length
}

export function keysToExcludedIndices(specs: Record<string, unknown>[], selectedKeys: Set<string>): number[] {
  return specs
    .map((s, i) => ({ key: `${s.hex_q},${s.hex_r}`, i }))
    .filter(x => !selectedKeys.has(x.key))
    .map(x => x.i)
}

export function keysToSelectedIndices(specs: Record<string, unknown>[], selectedKeys: Set<string>): number[] {
  return specs
    .map((s, i) => ({ key: `${s.hex_q},${s.hex_r}`, i }))
    .filter(x => selectedKeys.has(x.key))
    .map(x => x.i)
}

export function keysToExcludedCorridorCoords(
  topoSnapshot: { nodes?: Record<string, unknown>[] } | undefined,
  selectedKeys: Set<string>,
): number[][] {
  if (!topoSnapshot?.nodes) return []
  return topoSnapshot.nodes
    .filter(n => n.node_type === 'corridor' && !selectedKeys.has(`${n.hex_q},${n.hex_r}`))
    .map(n => [n.hex_q as number, n.hex_r as number])
}
