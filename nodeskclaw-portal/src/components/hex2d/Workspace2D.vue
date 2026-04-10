<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSvgZoom } from '@/composables/useSvgZoom'
import { axialToWorld, hexVertices, HEX_SIZE } from '@/composables/useHexLayout'
import { useTopologyBFS } from '@/composables/useTopologyBFS'
import { useFlowAnimation2D } from '@/composables/useFlowAnimation'
import { heatColor } from '@/composables/useHeatGradient'
import type { AgentBrief, MessageFlowPair, TopologyNode as StoreTopologyNode, TopologyEdge } from '@/stores/workspace'

const { t } = useI18n()

interface TopologyNode {
  hex_q: number
  hex_r: number
  node_type: 'agent' | 'blackboard' | 'corridor' | 'human'
  entity_id?: string
  display_name?: string
  extra?: Record<string, unknown>
  color?: string
}

interface PerfSummary {
  totalTasks: number
  completedTasks: number
  totalTokenCost: number
  totalValueCreated: number
}

const props = withDefaults(defineProps<{
  agents: AgentBrief[]
  blackboardContent: string
  selectedAgentId: string | null
  selectedHex: { q: number, r: number } | null
  topologyNodes?: TopologyNode[]
  topologyEdges?: TopologyEdge[]
  messageFlowStats?: MessageFlowPair[]
  isMovingHex?: boolean
  movingHexSource?: { q: number, r: number } | null
  perfSummary?: PerfSummary | null
  perfLoading?: boolean
  selectable?: boolean
  selectedKeys?: Set<string>
  selectableTypes?: string[]
}>(), {
  selectable: false,
  selectableTypes: () => ['agent'],
})

function formatK(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(Math.round(n))
}

const emit = defineEmits<{
  (e: 'hex-click', payload: { q: number, r: number, type: 'empty' | 'agent' | 'blackboard' | 'corridor' | 'human', agentId?: string, entityId?: string }): void
  (e: 'agent-dblclick', id: string): void
  (e: 'agent-hover', id: string | null): void
  (e: 'toggle-node', key: string): void
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const { transformStr, zoomIn, zoomOut, resetView, panBy, focusOnPosition } = useSvgZoom(svgRef, { minZoom: 0.3, maxZoom: 3 })

function focusOnHex(q: number, r: number) {
  const pos = worldPos(q, r)
  focusOnPosition(pos.px, pos.py)
}

const SCALE = 60

function worldPos(q: number, r: number): { px: number; py: number } {
  const { x, y } = axialToWorld(q, r)
  return { px: x * SCALE, py: y * SCALE }
}

function hexPointsStr(cx: number, cy: number, size: number): string {
  return hexVertices(cx, cy, size)
    .map(([vx, vy]) => `${vx},${vy}`)
    .join(' ')
}

const storeNodes = computed(() => (props.topologyNodes || []) as StoreTopologyNode[])
const storeEdges = computed(() => props.topologyEdges || [] as TopologyEdge[])
const { findPath, findReachableEndpoints } = useTopologyBFS(storeNodes, storeEdges)

const animState = useFlowAnimation2D(SCALE, 1)
const particles = computed(() => animState.particles.value)
const pulses = computed(() => animState.pulses.value)

function triggerMessageFlow(sourceInstanceId: string, target: string) {
  const nodes = props.topologyNodes || []
  const sourceNode = nodes.find(n => n.entity_id === sourceInstanceId)
  if (!sourceNode) return

  if (target.startsWith('agent:')) {
    const targetName = target.slice(6)
    const targetNode = nodes.find(n => n.node_type === 'agent' && n.display_name?.toLowerCase() === targetName.toLowerCase())
    if (targetNode) {
      const path = findPath(sourceNode.hex_q, sourceNode.hex_r, targetNode.hex_q, targetNode.hex_r)
      if (path) animState.triggerFlow(path)
    }
  } else if (target.startsWith('human:')) {
    const targetId = target.slice(6)
    const targetNode = nodes.find(n => n.node_type === 'human' && n.entity_id === targetId)
    if (targetNode) {
      const path = findPath(sourceNode.hex_q, sourceNode.hex_r, targetNode.hex_q, targetNode.hex_r)
      if (path) animState.triggerFlow(path)
    }
  } else if (target === 'broadcast') {
    const endpoints = findReachableEndpoints(sourceNode.hex_q, sourceNode.hex_r)
    for (const ep of endpoints) {
      const path = findPath(sourceNode.hex_q, sourceNode.hex_r, ep.q, ep.r)
      if (path) animState.triggerFlow(path)
    }
  }
}

onUnmounted(() => animState.dispose())

function flashRefresh() {
  const svg = svgRef.value
  if (!svg) return
  svg.style.transition = 'opacity 0.2s ease'
  svg.style.opacity = '0.4'
  setTimeout(() => {
    svg.style.opacity = '1'
    setTimeout(() => { svg.style.transition = '' }, 200)
  }, 200)
}

defineExpose({ zoomIn, zoomOut, resetView, panBy, focusOnHex, triggerMessageFlow, flashRefresh })

const hoveredId = ref<string | null>(null)

const HEX_RADIUS = HEX_SIZE * SCALE * 0.85
const BB_RADIUS = HEX_RADIUS * 1.15
const GRID_RANGE = 8

const HEX_CELL_W = Math.sqrt(3) * HEX_RADIUS
const HEX_CELL_H = 2 * HEX_RADIUS

const EDGE_X1 = -0.866 * HEX_RADIUS
const EDGE_Y1 = -0.5 * HEX_RADIUS
const EDGE_X2 = 0
const EDGE_Y2 = -HEX_RADIUS
const EDGE_MX = (EDGE_X1 + EDGE_X2) / 2
const EDGE_MY = (EDGE_Y1 + EDGE_Y2) / 2

const agentPositions = computed(() =>
  props.agents.map((a) => {
    const pos = worldPos(a.hex_q, a.hex_r)
    return { ...a, px: pos.px, py: pos.py }
  }),
)

const statusColors: Record<string, string> = {
  running: '#4ade80',
  learning: '#60a5fa',
  active: '#4ade80',
  thinking: '#fbbf24',
  pending: '#fbbf24',
  idle: '#6b7280',
  error: '#f87171',
  failed: '#f87171',
  restarting: '#f97316',
  deploying: '#f97316',
  updating: '#f97316',
  creating: '#f97316',
}

function getAgentColor(agent: AgentBrief): string {
  return agent.theme_color || statusColors[agent.status] || '#a78bfa'
}

function isNodeSelected(q: number, r: number): boolean {
  if (!props.selectable || !props.selectedKeys) return true
  return props.selectedKeys.has(`${q},${r}`)
}

function isAgentSelected(agent: { hex_q: number; hex_r: number }): boolean {
  return isNodeSelected(agent.hex_q, agent.hex_r)
}

function handleAgentClick(agent: AgentBrief) {
  if (props.selectable) {
    emit('toggle-node', `${agent.hex_q},${agent.hex_r}`)
  } else {
    emit('hex-click', { q: agent.hex_q, r: agent.hex_r, type: 'agent', agentId: agent.instance_id })
  }
}

const honeycombGrid = computed(() => {
  const lines: string[] = []
  const r = HEX_SIZE * SCALE * 0.95
  for (let q = -GRID_RANGE; q <= GRID_RANGE; q++) {
    for (let row = -GRID_RANGE; row <= GRID_RANGE; row++) {
      if (Math.abs(q) + Math.abs(row) + Math.abs(-q - row) > GRID_RANGE * 2) continue
      const pos = worldPos(q, row)
      for (let i = 0; i < 6; i++) {
        const a1 = (Math.PI / 3) * i - Math.PI / 6
        const a2 = (Math.PI / 3) * ((i + 1) % 6) - Math.PI / 6
        lines.push(`M${pos.px + r * Math.cos(a1)},${pos.py + r * Math.sin(a1)}L${pos.px + r * Math.cos(a2)},${pos.py + r * Math.sin(a2)}`)
      }
    }
  }
  return lines.join(' ')
})

function hexPoints(cx: number, cy: number): string {
  return hexPointsStr(cx, cy, HEX_RADIUS)
}

function bbHexPoints(): string {
  return hexPointsStr(0, 0, BB_RADIUS)
}

const corridorNodes = computed(() =>
  (props.topologyNodes || [])
    .filter(n => n.node_type === 'corridor')
    .map(n => {
      const pos = worldPos(n.hex_q, n.hex_r)
      return { ...n, px: pos.px, py: pos.py }
    })
)

const humanNodes = computed(() =>
  (props.topologyNodes || [])
    .filter(n => n.node_type === 'human')
    .map(n => {
      const pos = worldPos(n.hex_q, n.hex_r)
      return { ...n, px: pos.px, py: pos.py, color: (n.extra?.display_color as string) || '#f59e0b' }
    })
)

const CORRIDOR_RADIUS = HEX_RADIUS * 0.65
const HUMAN_RADIUS = HEX_RADIUS * 0.75

const AXIAL_DIRS: [number, number][] = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]
const ARM_LEN_2D = HEX_SIZE * 0.88 * Math.sqrt(3) / 2 * SCALE
const RAIL_GAP_2D = 7
const RAIL_WIDTH_2D = 2.5
const JUNCTION_R_2D = 4

const DIR_UNITS_2D: [number, number][] = AXIAL_DIRS.map(([dq, dr]) => {
  const { x, y } = axialToWorld(dq, dr)
  const len = Math.sqrt(x * x + y * y)
  return [x / len, y / len] as [number, number]
})

const HALF_GAP_2D = (RAIL_GAP_2D + RAIL_WIDTH_2D) / 2
const START_OFFSET_2D = JUNCTION_R_2D + 2

interface RailArm {
  x1a: number; y1a: number; x2a: number; y2a: number
  x1b: number; y1b: number; x2b: number; y2b: number
  neighborKey: string
}

const corridorPaths = computed(() => {
  const occupied = new Set<string>()
  occupied.add('0:0')
  for (const a of props.agents) occupied.add(`${a.hex_q}:${a.hex_r}`)
  for (const n of corridorNodes.value) occupied.add(`${n.hex_q}:${n.hex_r}`)
  for (const n of humanNodes.value) occupied.add(`${n.hex_q}:${n.hex_r}`)

  return corridorNodes.value.map(ch => {
    const arms: RailArm[] = []
    for (let i = 0; i < 6; i++) {
      const [dq, dr] = AXIAL_DIRS[i]
      if (!occupied.has(`${ch.hex_q + dq}:${ch.hex_r + dr}`)) continue
      const [dx, dy] = DIR_UNITS_2D[i]
      const endX = dx * ARM_LEN_2D
      const endY = dy * ARM_LEN_2D
      const perpX = -dy
      const perpY = dx
      arms.push({
        x1a: dx * START_OFFSET_2D + perpX * HALF_GAP_2D,
        y1a: dy * START_OFFSET_2D + perpY * HALF_GAP_2D,
        x2a: endX + perpX * HALF_GAP_2D,
        y2a: endY + perpY * HALF_GAP_2D,
        x1b: dx * START_OFFSET_2D - perpX * HALF_GAP_2D,
        y1b: dy * START_OFFSET_2D - perpY * HALF_GAP_2D,
        x2b: endX - perpX * HALF_GAP_2D,
        y2b: endY - perpY * HALF_GAP_2D,
        neighborKey: `${ch.hex_q + dq},${ch.hex_r + dr}`,
      })
    }
    return { ...ch, arms }
  })
})

function corridorHexPoints(cx: number, cy: number): string {
  return hexPointsStr(cx, cy, CORRIDOR_RADIUS)
}

function humanHexPoints(cx: number, cy: number): string {
  return hexPointsStr(cx, cy, HUMAN_RADIUS)
}

function axialDirIndex(dq: number, dr: number): number {
  return AXIAL_DIRS.findIndex(([aq, ar]) => aq === dq && ar === dr)
}

const edgeHeatMap = computed(() => {
  const stats = props.messageFlowStats
  if (!stats?.length) return new Map<string, number>()
  const raw = new Map<string, number>()
  for (const s of stats) {
    const [sq, sr] = s.sender_hex_key.split(',').map(Number)
    const [rq, rr] = s.receiver_hex_key.split(',').map(Number)
    const path = findPath(sq, sr, rq, rr)
    if (!path || path.length < 2) continue
    for (let i = 0; i < path.length - 1; i++) {
      const a = path[i], b = path[i + 1]
      const fwd = `${a.q},${a.r}>${b.q},${b.r}`
      const bwd = `${b.q},${b.r}>${a.q},${a.r}`
      raw.set(fwd, (raw.get(fwd) || 0) + s.count)
      raw.set(bwd, (raw.get(bwd) || 0) + s.count)
    }
  }
  const maxVal = Math.max(...raw.values(), 1)
  const normalized = new Map<string, number>()
  for (const [k, v] of raw) normalized.set(k, v / maxVal)
  return normalized
})

const agentDirHeat = computed(() => {
  const stats = props.messageFlowStats
  if (!stats?.length) return new Map<string, number[]>()
  const raw = new Map<string, number[]>()
  for (const s of stats) {
    const [sq, sr] = s.sender_hex_key.split(',').map(Number)
    const [rq, rr] = s.receiver_hex_key.split(',').map(Number)
    const path = findPath(sq, sr, rq, rr)
    if (!path || path.length < 2) continue
    const senderKey = `${sq},${sr}`
    if (!raw.has(senderKey)) raw.set(senderKey, [0, 0, 0, 0, 0, 0])
    const sDir = axialDirIndex(path[1].q - path[0].q, path[1].r - path[0].r)
    if (sDir >= 0) raw.get(senderKey)![sDir] += s.count

    const receiverKey = `${rq},${rr}`
    if (!raw.has(receiverKey)) raw.set(receiverKey, [0, 0, 0, 0, 0, 0])
    const last = path.length - 1
    const rDir = axialDirIndex(path[last - 1].q - path[last].q, path[last - 1].r - path[last].r)
    if (rDir >= 0) raw.get(receiverKey)![rDir] += s.count
  }
  const allMax = Math.max(...[...raw.values()].flatMap(v => v), 1)
  const normalized = new Map<string, number[]>()
  for (const [k, arr] of raw) normalized.set(k, arr.map(v => v / allMax))
  return normalized
})

const HEAT_EDGE_RADIUS = HEX_RADIUS * 1.08

function getArmColor(ch: { hex_q: number; hex_r: number }, arm: RailArm): string {
  const heat = edgeHeatMap.value.get(`${ch.hex_q},${ch.hex_r}>${arm.neighborKey}`) || 0
  return heat > 0 ? heatColor(heat) : '#06b6d4'
}

function getArmOpacity(ch: { hex_q: number; hex_r: number }, arm: RailArm): number {
  const heat = edgeHeatMap.value.get(`${ch.hex_q},${ch.hex_r}>${arm.neighborKey}`) || 0
  return heat > 0 ? 0.7 + 0.3 * heat : 0.7
}

function getJunctionColor(ch: { hex_q: number; hex_r: number; arms: RailArm[] }): string {
  let maxHeat = 0
  for (const arm of ch.arms) {
    const h = edgeHeatMap.value.get(`${ch.hex_q},${ch.hex_r}>${arm.neighborKey}`) || 0
    if (h > maxHeat) maxHeat = h
  }
  return maxHeat > 0 ? heatColor(maxHeat) : '#06b6d4'
}

function agentHeatEdges(agent: { hex_q: number; hex_r: number }) {
  const dirHeats = agentDirHeat.value.get(`${agent.hex_q},${agent.hex_r}`)
  const verts = hexVertices(0, 0, HEAT_EDGE_RADIUS)
  return Array.from({ length: 6 }, (_, i) => {
    const [x1, y1] = verts[i]
    const [x2, y2] = verts[(i + 1) % 6]
    return { x1, y1, x2, y2, heat: dirHeats ? dirHeats[i] : 0 }
  })
}

const emptyHexes = computed(() => {
  const occupied = new Set<string>()
  occupied.add('0:0')
  for (const a of props.agents) occupied.add(`${a.hex_q}:${a.hex_r}`)
  for (const n of corridorNodes.value) occupied.add(`${n.hex_q}:${n.hex_r}`)
  for (const n of humanNodes.value) occupied.add(`${n.hex_q}:${n.hex_r}`)
  const hexes: { q: number, r: number, px: number, py: number }[] = []
  for (let q = -GRID_RANGE; q <= GRID_RANGE; q++) {
    for (let r = -GRID_RANGE; r <= GRID_RANGE; r++) {
      if (Math.abs(q) + Math.abs(r) + Math.abs(-q - r) > GRID_RANGE * 2) continue
      if (occupied.has(`${q}:${r}`)) continue
      const pos = worldPos(q, r)
      hexes.push({ q, r, px: pos.px, py: pos.py })
    }
  }
  return hexes
})
</script>

<template>
  <svg
    ref="svgRef"
    class="w-full h-full"
    viewBox="-400 -300 800 600"
    preserveAspectRatio="xMidYMid meet"
    @contextmenu.prevent
  >
    <defs>
      <radialGradient id="grid-fade" cx="50%" cy="50%" r="50%">
        <stop offset="0%" stop-color="white" stop-opacity="1" />
        <stop offset="70%" stop-color="white" stop-opacity="0.6" />
        <stop offset="100%" stop-color="white" stop-opacity="0" />
      </radialGradient>
      <mask id="grid-mask">
        <rect x="-500" y="-400" width="1000" height="800" fill="url(#grid-fade)" />
      </mask>
      <filter id="bb-glow">
        <feGaussianBlur stdDeviation="6" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
      <clipPath id="hex-clip">
        <polygon :points="hexPointsStr(0, 0, HEX_RADIUS)" />
      </clipPath>
      <filter id="heat-glow">
        <feGaussianBlur stdDeviation="2" result="blur" />
        <feMerge>
          <feMergeNode in="blur" />
          <feMergeNode in="SourceGraphic" />
        </feMerge>
      </filter>
    </defs>

    <g :transform="transformStr">
      <!-- Honeycomb grid -->
      <path
        :d="honeycombGrid"
        fill="none"
        stroke="#4ac8e8"
        stroke-width="0.5"
        opacity="0.18"
        mask="url(#grid-mask)"
      />

      <!-- Empty hex clickable areas -->
      <g
        v-for="hex in emptyHexes"
        v-if="!selectable"
        :key="`empty-${hex.q}-${hex.r}`"
        class="cursor-pointer"
        :transform="`translate(${hex.px}, ${hex.py})`"
        @click.stop="emit('hex-click', { q: hex.q, r: hex.r, type: 'empty' })"
      >
        <polygon
          :points="hexPoints(0, 0)"
          :fill="isMovingHex ? '#4ade8018' : selectedHex?.q === hex.q && selectedHex?.r === hex.r ? '#60a5fa11' : 'transparent'"
          :stroke="isMovingHex ? '#4ade80' : selectedHex?.q === hex.q && selectedHex?.r === hex.r ? '#60a5fa' : 'transparent'"
          :stroke-width="isMovingHex ? 1.5 : selectedHex?.q === hex.q && selectedHex?.r === hex.r ? 2 : 0"
          :stroke-dasharray="isMovingHex ? '4,3' : 'none'"
          :class="isMovingHex ? 'move-target-hex' : 'hover-empty-hex'"
        />
      </g>

      <!-- Blackboard hex at center (q=0, r=0) -->
      <g
        :class="selectable ? 'cursor-default' : 'cursor-pointer bb-hex'"
        @click.stop="selectable || emit('hex-click', { q: 0, r: 0, type: 'blackboard' })"
        @pointerenter="selectable || (hoveredId = '__blackboard__')"
        @pointerleave="selectable || (hoveredId = null)"
      >
        <polygon
          v-if="!selectable && selectedHex?.q === 0 && selectedHex?.r === 0"
          :points="bbHexPoints()"
          fill="none"
          stroke="#60a5fa"
          stroke-width="3"
          opacity="0.8"
          class="animate-selected-ring"
        />
        <polygon
          :points="bbHexPoints()"
          :fill="!selectable && hoveredId === '__blackboard__' ? '#1e1e3a' : '#141428'"
          stroke="#a78bfa"
          stroke-width="1.5"
          opacity="0.9"
          filter="url(#bb-glow)"
        />
        <polygon
          v-if="!selectable"
          :points="bbHexPoints()"
          fill="none"
          stroke="#a78bfa"
          stroke-width="0.5"
          opacity="0.3"
          stroke-dasharray="4,4"
          class="animate-bb-ring"
        />
        <text x="0" :y="selectable ? 0 : -20" text-anchor="middle" fill="#a78bfa" font-size="11" font-weight="600">
          {{ t('workspaceView.bbTitle') }}
        </text>
        <template v-if="!selectable">
          <text v-if="perfSummary" x="0" y="-2" text-anchor="middle" fill="#9ca3af" font-size="9">
            {{ t('workspaceView.bbInputLine', { done: perfSummary.completedTasks, tasks: perfSummary.totalTasks }) }}
          </text>
          <text v-else-if="!perfLoading" x="0" y="-2" text-anchor="middle" fill="#9ca3af" font-size="9">
            {{ blackboardContent?.slice(0, 24) || t('workspaceView.bbNoSummary') }}{{ (blackboardContent?.length ?? 0) > 24 ? '...' : '' }}
          </text>
          <text v-if="perfSummary" x="0" y="16" text-anchor="middle" fill="#6b7280" font-size="8">
            {{ t('workspaceView.bbOutputLine', { value: formatK(perfSummary.totalValueCreated) }) }}
          </text>
          <text v-else-if="!perfLoading" x="0" y="16" text-anchor="middle" fill="#6b7280" font-size="8">
            {{ blackboardContent?.slice(24, 54) || '' }}{{ (blackboardContent?.length ?? 0) > 54 ? '...' : '' }}
          </text>
        </template>
      </g>

      <!-- Agent hexes -->
      <g
        v-for="agent in agentPositions"
        :key="agent.instance_id"
        class="cursor-pointer transition-transform"
        :transform="`translate(${agent.px}, ${agent.py}) ${!selectable && hoveredId === agent.instance_id ? 'scale(1.08)' : ''}`"
        :opacity="selectable && !isAgentSelected(agent) ? 0.25 : 1"
        @click.stop="handleAgentClick(agent)"
        @dblclick="selectable || emit('agent-dblclick', agent.instance_id)"
        @pointerenter="selectable || (hoveredId = agent.instance_id, emit('agent-hover', agent.instance_id))"
        @pointerleave="selectable || (hoveredId = null, emit('agent-hover', null))"
      >
        <!-- Selection highlight ring -->
        <polygon
          v-if="!selectable && props.selectedAgentId === agent.instance_id"
          :points="hexPoints(0, 0)"
          fill="none"
          stroke="#60a5fa"
          stroke-width="3.5"
          opacity="0.8"
          class="animate-selected-ring"
        />
        <polygon
          :points="hexPoints(0, 0)"
          :fill="selectable ? (getAgentColor(agent) + '22') : (agent.sse_connected ? getAgentColor(agent) + '22' : '#55556622')"
          :stroke="selectable ? getAgentColor(agent) : (agent.sse_connected ? getAgentColor(agent) : '#555566')"
          stroke-width="2"
          :stroke-dasharray="selectable ? 'none' : (agent.sse_connected ? 'none' : '6,4')"
          :opacity="selectable ? 1 : (agent.sse_connected ? 1 : 0.6)"
          :class="{
            'animate-pulse': !selectable && agent.sse_connected && (agent.status === 'running' || agent.status === 'active'),
            'animate-hex-thinking': !selectable && agent.sse_connected && (agent.status === 'thinking' || agent.status === 'pending' || agent.status === 'learning'),
          }"
        />
        <!-- Red strikethrough for deselected agents -->
        <line
          v-if="selectable && !isAgentSelected(agent)"
          :x1="-HEX_RADIUS * 0.7" :y1="0"
          :x2="HEX_RADIUS * 0.7" :y2="0"
          stroke="#ef4444" stroke-width="3" stroke-linecap="round"
          class="pointer-events-none"
        />
        <!-- Directional heat edges -->
        <template v-if="!selectable" v-for="(edge, ei) in agentHeatEdges(agent)" :key="'heat-' + ei">
          <line v-if="edge.heat > 0"
            :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
            :stroke="heatColor(edge.heat)" :stroke-width="3"
            :opacity="0.4 + 0.6 * edge.heat"
            stroke-linecap="round" filter="url(#heat-glow)"
          />
        </template>
        <!-- Status text along upper-left edge (inside hex) -->
        <text
          v-if="!selectable"
          :x="EDGE_MX" :y="EDGE_MY"
          :transform="`rotate(-30, ${EDGE_MX}, ${EDGE_MY})`"
          text-anchor="middle"
          dominant-baseline="middle"
          dy="5"
          :fill="agent.sse_connected ? getAgentColor(agent) : '#6b7280'"
          font-size="7"
        >
          {{ agent.sse_connected ? agent.status : 'disconnected' }}
        </text>
        <text
          :y="agent.label && !selectable ? -4 : 0"
          text-anchor="middle"
          :fill="selectable ? 'white' : (agent.sse_connected ? 'white' : '#9ca3af')"
          font-size="11"
          font-weight="500"
        >
          {{ agent.display_name || agent.name }}
        </text>
        <text
          v-if="agent.label && !selectable"
          y="10"
          text-anchor="middle"
          fill="#9ca3af"
          font-size="8"
        >
          {{ agent.label }}
        </text>
      </g>

      <!-- Corridor dual-rail paths -->
      <g
        v-for="ch in corridorPaths"
        :key="'corridor-' + ch.entity_id"
        :class="selectable && selectableTypes.includes('corridor') ? 'cursor-pointer' : selectable ? 'cursor-default' : 'cursor-pointer transition-transform'"
        :transform="`translate(${ch.px}, ${ch.py}) ${!selectable && hoveredId === 'corridor-' + ch.entity_id ? 'scale(1.06)' : ''}`"
        :opacity="selectable && !isNodeSelected(ch.hex_q, ch.hex_r) ? 0.2 : 1"
        @click.stop="selectable && selectableTypes.includes('corridor') ? emit('toggle-node', `${ch.hex_q},${ch.hex_r}`) : selectable ? undefined : emit('hex-click', { q: ch.hex_q, r: ch.hex_r, type: 'corridor', entityId: ch.entity_id })"
        @pointerenter="selectable || (hoveredId = 'corridor-' + ch.entity_id)"
        @pointerleave="selectable || (hoveredId = null)"
      >
        <polygon
          :points="corridorHexPoints(0, 0)"
          fill="transparent"
          stroke="none"
        />
        <template v-for="(arm, i) in ch.arms" :key="i">
          <line
            :x1="arm.x1a" :y1="arm.y1a" :x2="arm.x2a" :y2="arm.y2a"
            :stroke="getArmColor(ch, arm)" :stroke-width="RAIL_WIDTH_2D" stroke-linecap="round" :opacity="getArmOpacity(ch, arm)"
          />
          <line
            :x1="arm.x1b" :y1="arm.y1b" :x2="arm.x2b" :y2="arm.y2b"
            :stroke="getArmColor(ch, arm)" :stroke-width="RAIL_WIDTH_2D" stroke-linecap="round" :opacity="getArmOpacity(ch, arm)"
          />
        </template>
        <circle cx="0" cy="0" :r="JUNCTION_R_2D" :fill="getJunctionColor(ch)" opacity="0.6" />
        <line
          v-if="selectable && !isNodeSelected(ch.hex_q, ch.hex_r)"
          :x1="-CORRIDOR_RADIUS * 0.7" :y1="0"
          :x2="CORRIDOR_RADIUS * 0.7" :y2="0"
          stroke="#ef4444" stroke-width="3" stroke-linecap="round"
          class="pointer-events-none"
        />
        <text
          v-if="ch.display_name"
          :y="-CORRIDOR_RADIUS - 6"
          text-anchor="middle"
          fill="#06b6d4"
          font-size="9"
          font-weight="600"
        >
          {{ ch.display_name }}
        </text>
      </g>

      <!-- Human hexes -->
      <g
        v-for="hh in humanNodes"
        :key="'human-' + hh.entity_id"
        :class="selectable ? 'cursor-default' : 'cursor-pointer transition-transform'"
        :transform="`translate(${hh.px}, ${hh.py}) ${!selectable && hoveredId === 'human-' + hh.entity_id ? 'scale(1.06)' : ''}`"
        @click.stop="selectable || emit('hex-click', { q: hh.hex_q, r: hh.hex_r, type: 'human', entityId: hh.entity_id })"
        @pointerenter="selectable || (hoveredId = 'human-' + hh.entity_id)"
        @pointerleave="selectable || (hoveredId = null)"
      >
        <polygon
          :points="humanHexPoints(0, 0)"
          :fill="(hh.color || '#f59e0b') + '22'"
          :stroke="hh.color || '#f59e0b'"
          stroke-width="2"
          opacity="0.9"
        />
        <text y="4" text-anchor="middle" :fill="hh.color || '#f59e0b'" font-size="10" font-weight="500">
          {{ hh.display_name }}
        </text>
      </g>

      <!-- Message flow animation particles -->
      <g v-if="!selectable" class="flow-anim-layer">
        <circle
          v-for="p in particles"
          :key="p.id"
          :cx="animState.getParticlePosition(p).x"
          :cy="animState.getParticlePosition(p).y"
          r="4"
          :fill="p.color"
          :opacity="1 - p.progress * 0.5"
        />
      </g>

      <!-- Hex pulse on message arrival -->
      <g v-if="!selectable" class="pulse-layer">
        <template v-for="pulse in pulses" :key="pulse.key">
          <circle
            :cx="worldPos(Number(pulse.key.split(',')[0]), Number(pulse.key.split(',')[1])).px"
            :cy="worldPos(Number(pulse.key.split(',')[0]), Number(pulse.key.split(',')[1])).py"
            :r="HEX_RADIUS * 0.6"
            fill="none"
            stroke="#a78bfa"
            stroke-width="2"
            class="animate-hex-pulse"
          />
        </template>
      </g>

      <!-- Selected hex highlight for agents -->
      <g
        v-if="!selectable && selectedHex && !isMovingHex && agents.some(a => a.hex_q === selectedHex!.q && a.hex_r === selectedHex!.r)"
        :transform="`translate(${worldPos(selectedHex!.q, selectedHex!.r).px}, ${worldPos(selectedHex!.q, selectedHex!.r).py})`"
      >
        <polygon
          :points="hexPoints(0, 0)"
          fill="none"
          stroke="#60a5fa"
          stroke-width="3"
          opacity="0.8"
          class="animate-selected-ring"
        />
      </g>

      <!-- Move mode: source hex pulsing highlight -->
      <g
        v-if="!selectable && isMovingHex && movingHexSource"
        :transform="`translate(${worldPos(movingHexSource.q, movingHexSource.r).px}, ${worldPos(movingHexSource.q, movingHexSource.r).py})`"
      >
        <polygon
          :points="hexPoints(0, 0)"
          fill="none"
          stroke="#f59e0b"
          stroke-width="3"
          class="animate-move-source"
        />
      </g>

    </g>
  </svg>
</template>

<style scoped>
@keyframes hex-thinking {
  0%, 100% { stroke-dashoffset: 0; }
  50% { stroke-dashoffset: 20; }
}
.animate-hex-thinking {
  stroke-dasharray: 10, 5;
  animation: hex-thinking 1.5s ease-in-out infinite;
}

@keyframes bb-ring-rotate {
  0% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: 48; }
}
.animate-bb-ring {
  animation: bb-ring-rotate 8s linear infinite;
}

@keyframes selected-ring-pulse {
  0%, 100% { opacity: 0.8; stroke-width: 3.5; }
  50% { opacity: 0.4; stroke-width: 2.5; }
}
.animate-selected-ring {
  animation: selected-ring-pulse 1.5s ease-in-out infinite;
}

.bb-hex {
  transition: transform 0.2s ease;
}
.bb-hex:hover {
  transform: scale(1.04);
}

.hover-empty-hex {
  transition: fill 0.15s ease, stroke 0.15s ease;
}
.hover-empty-hex:hover {
  fill: #4ac8e808;
  stroke: #4ac8e8;
  stroke-width: 1;
}

@keyframes move-source-pulse {
  0%, 100% { opacity: 0.9; stroke-width: 3.5; }
  50% { opacity: 0.4; stroke-width: 2; }
}
.animate-move-source {
  animation: move-source-pulse 1s ease-in-out infinite;
}

@keyframes hex-pulse {
  0% { r: 10; opacity: 0.8; }
  100% { r: 30; opacity: 0; }
}
.animate-hex-pulse {
  animation: hex-pulse 0.5s ease-out forwards;
}

.move-target-hex {
  transition: fill 0.15s ease, stroke 0.15s ease;
}
.move-target-hex:hover {
  fill: #4ade8030;
  stroke: #4ade80;
  stroke-width: 2.5;
  stroke-dasharray: none;
}
</style>
