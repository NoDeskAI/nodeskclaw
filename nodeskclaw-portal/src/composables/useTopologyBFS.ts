import { computed, type Ref } from 'vue'
import type { TopologyNode, TopologyEdge } from '@/stores/workspace'

export interface HexPath {
  q: number
  r: number
}

function hexKey(q: number, r: number): string {
  return `${q},${r}`
}

function buildAdjacency(edges: TopologyEdge[]): Map<string, string[]> {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    const ka = hexKey(e.a_q, e.a_r)
    const kb = hexKey(e.b_q, e.b_r)
    if (!adj.has(ka)) adj.set(ka, [])
    if (!adj.has(kb)) adj.set(kb, [])
    adj.get(ka)!.push(kb)
    adj.get(kb)!.push(ka)
  }
  return adj
}

export function useTopologyBFS(
  topologyNodes: Ref<TopologyNode[]>,
  topologyEdges: Ref<TopologyEdge[]>,
) {
  const adjacency = computed(() => buildAdjacency(topologyEdges.value))

  const nodeTypeMap = computed(() => {
    const m = new Map<string, TopologyNode['node_type']>()
    for (const n of topologyNodes.value) {
      m.set(hexKey(n.hex_q, n.hex_r), n.node_type)
    }
    return m
  })

  function findPath(fromQ: number, fromR: number, toQ: number, toR: number): HexPath[] | null {
    const adj = adjacency.value
    const types = nodeTypeMap.value
    const startKey = hexKey(fromQ, fromR)
    const endKey = hexKey(toQ, toR)

    if (startKey === endKey) return [{ q: fromQ, r: fromR }]

    const visited = new Set<string>([startKey])
    const parent = new Map<string, string>()
    const queue: string[] = [startKey]

    while (queue.length > 0) {
      const current = queue.shift()!
      const neighbors = adj.get(current) || []

      for (const neighbor of neighbors) {
        if (visited.has(neighbor)) continue
        visited.add(neighbor)
        parent.set(neighbor, current)

        if (neighbor === endKey) {
          const path: HexPath[] = []
          let cursor = endKey
          while (cursor) {
            const [q, r] = cursor.split(',').map(Number)
            path.unshift({ q, r })
            cursor = parent.get(cursor)!
          }
          return path
        }

        const nodeType = types.get(neighbor)
        if (nodeType === 'corridor' || nodeType === 'blackboard') {
          queue.push(neighbor)
        }
      }
    }

    return null
  }

  function findReachableEndpoints(fromQ: number, fromR: number): HexPath[] {
    const adj = adjacency.value
    const types = nodeTypeMap.value
    const startKey = hexKey(fromQ, fromR)
    const visited = new Set<string>([startKey])
    const queue: string[] = [startKey]
    const endpoints: HexPath[] = []

    while (queue.length > 0) {
      const current = queue.shift()!
      const neighbors = adj.get(current) || []

      for (const neighbor of neighbors) {
        if (visited.has(neighbor)) continue
        visited.add(neighbor)

        const nodeType = types.get(neighbor)
        if (nodeType === 'agent' || nodeType === 'human') {
          const [q, r] = neighbor.split(',').map(Number)
          endpoints.push({ q, r })
        } else if (nodeType === 'corridor' || nodeType === 'blackboard') {
          queue.push(neighbor)
        }
      }
    }

    return endpoints
  }

  return { findPath, findReachableEndpoints }
}
