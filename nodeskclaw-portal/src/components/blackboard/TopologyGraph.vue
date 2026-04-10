<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSvgZoom } from '@/composables/useSvgZoom'
import { axialToWorld } from '@/composables/useHexLayout'
import type { TopologyNode, TopologyEdge } from '@/stores/workspace'

const props = withDefaults(defineProps<{
  nodes: TopologyNode[]
  edges: TopologyEdge[]
  hideLegend?: boolean
  compact?: boolean
  selectable?: boolean
  selectedKeys?: Set<string>
  selectableTypes?: string[]
}>(), { hideLegend: false, compact: false, selectable: false, selectableTypes: () => ['agent'] })

const emit = defineEmits<{
  'toggle-node': [key: string]
}>()

const { t } = useI18n()
const svgRef = ref<SVGSVGElement | null>(null)
const { transformStr } = useSvgZoom(svgRef, { minZoom: 0.3, maxZoom: 4 })

const hoveredKey = ref<string | null>(null)

const SCALE = 80
const PADDING = 60

const NODE_STYLES: Record<string, { color: string; radius: number }> = {
  blackboard: { color: 'hsl(var(--primary))', radius: 18 },
  agent: { color: '#3b82f6', radius: 14 },
  human: { color: '#f59e0b', radius: 14 },
  corridor: { color: 'hsl(var(--muted-foreground))', radius: 8 },
}

const COMPACT_NODE_STYLES: Record<string, { color: string; radius: number }> = {
  blackboard: { color: '#a78bfa', radius: 26 },
  agent: { color: '#60a5fa', radius: 18 },
  human: { color: '#fbbf24', radius: 18 },
  corridor: { color: '#34d399', radius: 12 },
}

function nodeKey(q: number, r: number) {
  return `${q},${r}`
}

interface PositionedNode extends TopologyNode {
  px: number
  py: number
  key: string
}

const positionedNodes = computed<PositionedNode[]>(() =>
  props.nodes.map(n => {
    const w = axialToWorld(n.hex_q, n.hex_r)
    return { ...n, px: w.x * SCALE, py: w.y * SCALE, key: nodeKey(n.hex_q, n.hex_r) }
  }),
)

const nodeMap = computed(() => {
  const m = new Map<string, PositionedNode>()
  for (const n of positionedNodes.value) m.set(n.key, n)
  return m
})

interface PositionedEdge extends TopologyEdge {
  x1: number; y1: number; x2: number; y2: number
  keyA: string; keyB: string
}

const positionedEdges = computed<PositionedEdge[]>(() => {
  const m = nodeMap.value
  return props.edges
    .map(e => {
      const kA = nodeKey(e.a_q, e.a_r)
      const kB = nodeKey(e.b_q, e.b_r)
      const nA = m.get(kA)
      const nB = m.get(kB)
      if (!nA || !nB) return null
      return { ...e, x1: nA.px, y1: nA.py, x2: nB.px, y2: nB.py, keyA: kA, keyB: kB }
    })
    .filter((e): e is PositionedEdge => e !== null)
})

const viewBox = computed(() => {
  const ns = positionedNodes.value
  if (ns.length === 0) return '0 0 400 300'
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const n of ns) {
    if (n.px < minX) minX = n.px
    if (n.px > maxX) maxX = n.px
    if (n.py < minY) minY = n.py
    if (n.py > maxY) maxY = n.py
  }
  const w = maxX - minX || 200
  const h = maxY - minY || 150
  return `${minX - PADDING} ${minY - PADDING} ${w + PADDING * 2} ${h + PADDING * 2}`
})

const connectedKeys = computed(() => {
  if (!hoveredKey.value) return null
  const keys = new Set<string>([hoveredKey.value])
  for (const e of positionedEdges.value) {
    if (e.keyA === hoveredKey.value) keys.add(e.keyB)
    else if (e.keyB === hoveredKey.value) keys.add(e.keyA)
  }
  return keys
})

function nodeOpacity(key: string): number {
  if (!connectedKeys.value) return 1
  return connectedKeys.value.has(key) ? 1 : 0.15
}

function edgeOpacity(e: PositionedEdge): number {
  if (!connectedKeys.value) return 1
  return (connectedKeys.value.has(e.keyA) && connectedKeys.value.has(e.keyB)) ? 1 : 0.08
}

function nodeLabel(n: TopologyNode): string {
  return n.display_name || n.entity_id || ''
}

function textFill(type: string): string {
  if (props.selectable || props.compact) return nodeStyle(type).color
  return 'hsl(var(--foreground))'
}

function nodeStyle(type: string) {
  const styles = (props.compact || props.selectable) ? COMPACT_NODE_STYLES : NODE_STYLES
  return styles[type] || styles.corridor
}

function isNodeSelectable(node: PositionedNode): boolean {
  return props.selectable && props.selectableTypes.includes(node.node_type)
}

function isNodeSelected(node: PositionedNode): boolean {
  if (!props.selectable || !props.selectedKeys) return true
  if (!isNodeSelectable(node)) return true
  return props.selectedKeys.has(node.key)
}

function handleNodeClick(node: PositionedNode) {
  if (isNodeSelectable(node)) {
    emit('toggle-node', node.key)
  }
}

const visibleNodes = computed(() => {
  if (!props.compact) return positionedNodes.value
  return positionedNodes.value.filter(n => n.node_type !== 'corridor')
})

const visibleEdges = computed<PositionedEdge[]>(() => {
  if (!props.compact) return positionedEdges.value
  const m = nodeMap.value
  const adj = new Map<string, Set<string>>()
  for (const e of positionedEdges.value) {
    if (!adj.has(e.keyA)) adj.set(e.keyA, new Set())
    if (!adj.has(e.keyB)) adj.set(e.keyB, new Set())
    adj.get(e.keyA)!.add(e.keyB)
    adj.get(e.keyB)!.add(e.keyA)
  }
  const corridorKeys = new Set(
    positionedNodes.value.filter(n => n.node_type === 'corridor').map(n => n.key),
  )
  const seen = new Set<string>()
  const result: PositionedEdge[] = []
  for (const start of visibleNodes.value) {
    const queue = [start.key]
    const visited = new Set<string>([start.key])
    while (queue.length > 0) {
      const cur = queue.shift()!
      for (const nb of adj.get(cur) || []) {
        if (visited.has(nb)) continue
        visited.add(nb)
        if (corridorKeys.has(nb)) {
          queue.push(nb)
        } else {
          const ek = [start.key, nb].sort().join('|')
          if (!seen.has(ek)) {
            seen.add(ek)
            const nA = m.get(start.key)
            const nB = m.get(nb)
            if (nA && nB) {
              result.push({
                a_q: nA.hex_q, a_r: nA.hex_r,
                b_q: nB.hex_q, b_r: nB.hex_r,
                direction: 'both', auto_created: false,
                x1: nA.px, y1: nA.py, x2: nB.px, y2: nB.py,
                keyA: start.key, keyB: nb,
              })
            }
          }
        }
      }
    }
  }
  return result
})

const legendItems = computed(() => [
  { type: 'blackboard', labelKey: 'blackboard.topoBlackboardNode' },
  { type: 'agent', labelKey: 'blackboard.topoAgentNode' },
  { type: 'human', labelKey: 'blackboard.topoHumanNode' },
  { type: 'corridor', labelKey: 'blackboard.topoCorridorNode' },
])
</script>

<template>
  <div class="relative w-full h-full min-h-[300px]">
    <svg
      ref="svgRef"
      class="w-full h-full"
      :viewBox="viewBox"
      @contextmenu.prevent
    >
      <g :transform="transformStr">
        <line
          v-for="(edge, i) in visibleEdges"
          v-show="!compact || selectable"
          :key="'e-' + i"
          :x1="edge.x1"
          :y1="edge.y1"
          :x2="edge.x2"
          :y2="edge.y2"
          :stroke="selectable ? '#22d3ee' : (edge.auto_created ? 'hsl(var(--border))' : 'hsl(var(--muted-foreground))')"
          :stroke-width="selectable ? 2.5 : (edge.auto_created ? 1.5 : 2)"
          :stroke-dasharray="selectable ? 'none' : (edge.auto_created ? '6 4' : 'none')"
          :opacity="edgeOpacity(edge)"
          class="transition-opacity duration-200"
        />

        <g
          v-for="node in visibleNodes"
          :key="node.key"
          :transform="`translate(${node.px}, ${node.py})`"
          :opacity="selectable ? (isNodeSelected(node) ? 1 : 0.25) : nodeOpacity(node.key)"
          :class="['transition-opacity duration-200', isNodeSelectable(node) ? 'cursor-pointer' : (selectable ? 'cursor-default' : 'cursor-pointer')]"
          @pointerenter="hoveredKey = node.key"
          @pointerleave="hoveredKey = null"
          @click="handleNodeClick(node)"
        >
          <circle
            :r="nodeStyle(node.node_type).radius"
            :fill="nodeStyle(node.node_type).color"
            :fill-opacity="(compact || selectable) ? 0.5 : 0.15"
            :stroke="nodeStyle(node.node_type).color"
            :stroke-width="(compact || selectable) ? 2.5 : 2"
          />
          <circle
            :r="nodeStyle(node.node_type).radius * ((compact || selectable) ? 0.55 : 0.4)"
            :fill="nodeStyle(node.node_type).color"
          />
          <line
            v-if="selectable && isNodeSelectable(node) && !isNodeSelected(node)"
            :x1="-nodeStyle(node.node_type).radius"
            :y1="0"
            :x2="nodeStyle(node.node_type).radius"
            :y2="0"
            stroke="#ef4444"
            stroke-width="2.5"
            stroke-linecap="round"
            class="pointer-events-none"
          />
          <text
            :y="nodeStyle(node.node_type).radius + ((compact || selectable) ? 16 : 14)"
            text-anchor="middle"
            :fill="textFill(node.node_type)"
            :font-size="(compact || selectable) ? 13 : 11"
            :font-weight="(compact || selectable) && node.node_type === 'blackboard' ? 'bold' : 'normal'"
            class="select-none pointer-events-none"
          >{{ nodeLabel(node) }}</text>
        </g>
      </g>
    </svg>

    <div v-if="!hideLegend" class="absolute bottom-3 right-3 bg-card/90 backdrop-blur-sm border border-border rounded-lg px-3 py-2 text-xs space-y-1.5">
      <div
        v-for="item in legendItems"
        :key="item.type"
        class="flex items-center gap-2"
      >
        <span
          class="inline-block rounded-full"
          :style="{
            width: nodeStyle(item.type).radius + 'px',
            height: nodeStyle(item.type).radius + 'px',
            backgroundColor: nodeStyle(item.type).color,
            opacity: 0.8,
          }"
        />
        <span class="text-muted-foreground">{{ t(item.labelKey) }}</span>
      </div>
      <div class="border-t border-border pt-1.5 mt-1.5 space-y-1">
        <div class="flex items-center gap-2">
          <span class="inline-block w-5 border-t-2 border-[hsl(var(--muted-foreground))]" />
          <span class="text-muted-foreground">{{ t('blackboard.topoManual') }}</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="inline-block w-5 border-t-2 border-dashed border-[hsl(var(--border))]" />
          <span class="text-muted-foreground">{{ t('blackboard.topoAutoCreated') }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
