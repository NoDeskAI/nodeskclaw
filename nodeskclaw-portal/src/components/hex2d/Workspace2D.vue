<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSvgZoom } from '@/composables/useSvgZoom'
import { axialToWorld, hexPolygonPoints, HEX_SIZE } from '@/composables/useHexLayout'
import { useTopologyBFS } from '@/composables/useTopologyBFS'
import { useFlowAnimation2D } from '@/composables/useFlowAnimation'
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

const props = defineProps<{
  agents: AgentBrief[]
  blackboardContent: string
  selectedAgentId: string | null
  selectedHex: { q: number, r: number } | null
  topologyNodes?: TopologyNode[]
  topologyEdges?: TopologyEdge[]
  messageFlowStats?: MessageFlowPair[]
  isMovingHex?: boolean
  movingHexSource?: { q: number, r: number } | null
}>()

const emit = defineEmits<{
  (e: 'hex-click', payload: { q: number, r: number, type: 'empty' | 'agent' | 'blackboard' | 'corridor' | 'human', agentId?: string, entityId?: string }): void
  (e: 'agent-dblclick', id: string): void
  (e: 'agent-hover', id: string | null): void
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const { transformStr, zoomIn, zoomOut, resetView, panBy, focusOnPosition } = useSvgZoom(svgRef, { minZoom: 0.3, maxZoom: 3 })

function focusOnHex(q: number, r: number) {
  const { x, y } = axialToWorld(q, r)
  focusOnPosition(x * SCALE, y * SCALE)
}

const SCALE = 60

const storeNodes = computed(() => (props.topologyNodes || []) as StoreTopologyNode[])
const storeEdges = computed(() => props.topologyEdges || [] as TopologyEdge[])
const { findPath, findReachableEndpoints } = useTopologyBFS(storeNodes, storeEdges)
const { particles, pulses, triggerFlow, getParticlePosition, dispose: disposeAnim } = useFlowAnimation2D(SCALE)

function triggerMessageFlow(sourceInstanceId: string, target: string) {
  const nodes = props.topologyNodes || []
  const sourceNode = nodes.find(n => n.entity_id === sourceInstanceId)
  if (!sourceNode) return

  if (target.startsWith('agent:')) {
    const targetName = target.slice(6)
    const targetNode = nodes.find(n => n.node_type === 'agent' && n.display_name?.toLowerCase() === targetName.toLowerCase())
    if (targetNode) {
      const path = findPath(sourceNode.hex_q, sourceNode.hex_r, targetNode.hex_q, targetNode.hex_r)
      if (path) triggerFlow(path)
    }
  } else if (target.startsWith('human:')) {
    const targetId = target.slice(6)
    const targetNode = nodes.find(n => n.node_type === 'human' && n.entity_id === targetId)
    if (targetNode) {
      const path = findPath(sourceNode.hex_q, sourceNode.hex_r, targetNode.hex_q, targetNode.hex_r)
      if (path) triggerFlow(path)
    }
  } else if (target === 'broadcast') {
    const endpoints = findReachableEndpoints(sourceNode.hex_q, sourceNode.hex_r)
    for (const ep of endpoints) {
      const path = findPath(sourceNode.hex_q, sourceNode.hex_r, ep.q, ep.r)
      if (path) triggerFlow(path)
    }
  }
}

onUnmounted(() => disposeAnim())

defineExpose({ zoomIn, zoomOut, resetView, panBy, focusOnHex, triggerMessageFlow })

const hoveredId = ref<string | null>(null)

const HEX_RADIUS = HEX_SIZE * SCALE * 0.85
const BB_RADIUS = HEX_RADIUS * 1.15
const GRID_RANGE = 8

const EDGE_X1 = -0.866 * HEX_RADIUS
const EDGE_Y1 = -0.5 * HEX_RADIUS
const EDGE_X2 = 0
const EDGE_Y2 = -HEX_RADIUS
const EDGE_MX = (EDGE_X1 + EDGE_X2) / 2
const EDGE_MY = (EDGE_Y1 + EDGE_Y2) / 2

const agentPositions = computed(() =>
  props.agents.map((a) => {
    const { x, y } = axialToWorld(a.hex_q, a.hex_r)
    return { ...a, px: x * SCALE, py: y * SCALE }
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

const honeycombGrid = computed(() => {
  const lines: string[] = []
  const r = HEX_SIZE * SCALE * 0.95
  for (let q = -GRID_RANGE; q <= GRID_RANGE; q++) {
    for (let row = -GRID_RANGE; row <= GRID_RANGE; row++) {
      if (Math.abs(q) + Math.abs(row) + Math.abs(-q - row) > GRID_RANGE * 2) continue
      const { x, y } = axialToWorld(q, row)
      const cx = x * SCALE
      const cy = y * SCALE
      for (let i = 0; i < 6; i++) {
        const a1 = (Math.PI / 3) * i - Math.PI / 6
        const a2 = (Math.PI / 3) * ((i + 1) % 6) - Math.PI / 6
        lines.push(`M${cx + r * Math.cos(a1)},${cy + r * Math.sin(a1)}L${cx + r * Math.cos(a2)},${cy + r * Math.sin(a2)}`)
      }
    }
  }
  return lines.join(' ')
})

function hexPoints(cx: number, cy: number): string {
  return hexPolygonPoints(cx, cy, HEX_RADIUS)
}

function bbHexPoints(): string {
  return hexPolygonPoints(0, 0, BB_RADIUS)
}

const corridorNodes = computed(() =>
  (props.topologyNodes || [])
    .filter(n => n.node_type === 'corridor')
    .map(n => {
      const { x, y } = axialToWorld(n.hex_q, n.hex_r)
      return { ...n, px: x * SCALE, py: y * SCALE }
    })
)

const humanNodes = computed(() =>
  (props.topologyNodes || [])
    .filter(n => n.node_type === 'human')
    .map(n => {
      const { x, y } = axialToWorld(n.hex_q, n.hex_r)
      return { ...n, px: x * SCALE, py: y * SCALE, color: (n.extra?.display_color as string) || '#f59e0b' }
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
      })
    }
    return { ...ch, arms }
  })
})

function corridorHexPoints(cx: number, cy: number): string {
  return hexPolygonPoints(cx, cy, CORRIDOR_RADIUS)
}

function humanHexPoints(cx: number, cy: number): string {
  return hexPolygonPoints(cx, cy, HUMAN_RADIUS)
}

const heatLines = computed(() => {
  const stats = props.messageFlowStats
  if (!stats || stats.length === 0) return []
  const maxCount = Math.max(...stats.map(s => s.count))
  if (maxCount === 0) return []
  return stats.map(s => {
    const [sq, sr] = s.sender_hex_key.split(',').map(Number)
    const [rq, rr] = s.receiver_hex_key.split(',').map(Number)
    const from = axialToWorld(sq, sr)
    const to = axialToWorld(rq, rr)
    const ratio = s.count / maxCount
    return {
      key: s.sender_hex_key + '-' + s.receiver_hex_key,
      x1: from.x * SCALE,
      y1: from.y * SCALE,
      x2: to.x * SCALE,
      y2: to.y * SCALE,
      width: 1 + 4 * ratio,
      opacity: 0.15 + 0.45 * ratio,
    }
  })
})

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
      const { x, y } = axialToWorld(q, r)
      hexes.push({ q, r, px: x * SCALE, py: y * SCALE })
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

      <!-- Heatmap overlay -->
      <g class="heat-layer" v-if="heatLines.length">
        <line
          v-for="hl in heatLines"
          :key="hl.key"
          :x1="hl.x1" :y1="hl.y1" :x2="hl.x2" :y2="hl.y2"
          stroke="#a78bfa"
          :stroke-width="hl.width"
          :opacity="hl.opacity"
          stroke-linecap="round"
        />
      </g>

      <!-- Empty hex clickable areas -->
      <g
        v-for="hex in emptyHexes"
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
        class="cursor-pointer bb-hex"
        @click.stop="emit('hex-click', { q: 0, r: 0, type: 'blackboard' })"
        @pointerenter="hoveredId = '__blackboard__'"
        @pointerleave="hoveredId = null"
      >
        <polygon
          v-if="selectedHex?.q === 0 && selectedHex?.r === 0"
          :points="bbHexPoints()"
          fill="none"
          stroke="#60a5fa"
          stroke-width="3"
          opacity="0.8"
          class="animate-selected-ring"
        />
        <polygon
          :points="bbHexPoints()"
          :fill="hoveredId === '__blackboard__' ? '#1e1e3a' : '#141428'"
          stroke="#a78bfa"
          stroke-width="1.5"
          opacity="0.9"
          filter="url(#bb-glow)"
        />
        <polygon
          :points="bbHexPoints()"
          fill="none"
          stroke="#a78bfa"
          stroke-width="0.5"
          opacity="0.3"
          stroke-dasharray="4,4"
          class="animate-bb-ring"
        />
        <text x="0" y="-20" text-anchor="middle" fill="#a78bfa" font-size="11" font-weight="600">
          {{ t('workspaceView.bbTitle') }}
        </text>
        <text x="0" y="-2" text-anchor="middle" fill="#9ca3af" font-size="9">
          {{ blackboardContent?.slice(0, 24) || t('workspaceView.bbNoSummary') }}{{ (blackboardContent?.length ?? 0) > 24 ? '...' : '' }}
        </text>
        <text x="0" y="16" text-anchor="middle" fill="#6b7280" font-size="8">
          {{ blackboardContent?.slice(24, 54) || '' }}{{ (blackboardContent?.length ?? 0) > 54 ? '...' : '' }}
        </text>
      </g>

      <!-- Agent hexes -->
      <g
        v-for="agent in agentPositions"
        :key="agent.instance_id"
        class="cursor-pointer transition-transform"
        :transform="`translate(${agent.px}, ${agent.py}) ${hoveredId === agent.instance_id ? 'scale(1.08)' : ''}`"
        @click.stop="emit('hex-click', { q: agent.hex_q, r: agent.hex_r, type: 'agent', agentId: agent.instance_id })"
        @dblclick="emit('agent-dblclick', agent.instance_id)"
        @pointerenter="hoveredId = agent.instance_id; emit('agent-hover', agent.instance_id)"
        @pointerleave="hoveredId = null; emit('agent-hover', null)"
      >
        <!-- Selection highlight ring -->
        <polygon
          v-if="props.selectedAgentId === agent.instance_id"
          :points="hexPoints(0, 0)"
          fill="none"
          stroke="#60a5fa"
          stroke-width="3.5"
          opacity="0.8"
          class="animate-selected-ring"
        />
        <polygon
          :points="hexPoints(0, 0)"
          :fill="agent.sse_connected ? (statusColors[agent.status] || '#a78bfa') + '22' : '#55556622'"
          :stroke="agent.sse_connected ? (statusColors[agent.status] || '#a78bfa') : '#555566'"
          stroke-width="2"
          :stroke-dasharray="agent.sse_connected ? 'none' : '6,4'"
          :opacity="agent.sse_connected ? 1 : 0.6"
          :class="{
            'animate-pulse': agent.sse_connected && (agent.status === 'running' || agent.status === 'active'),
            'animate-hex-thinking': agent.sse_connected && (agent.status === 'thinking' || agent.status === 'pending' || agent.status === 'learning'),
          }"
        />
        <!-- Status text along upper-left edge (inside hex) -->
        <text
          :x="EDGE_MX" :y="EDGE_MY"
          :transform="`rotate(-30, ${EDGE_MX}, ${EDGE_MY})`"
          text-anchor="middle"
          dominant-baseline="middle"
          dy="5"
          :fill="agent.sse_connected ? (statusColors[agent.status] || '#a78bfa') : '#6b7280'"
          font-size="7"
        >
          {{ agent.sse_connected ? agent.status : 'disconnected' }}
        </text>
        <text
          :y="agent.label ? -4 : 0"
          text-anchor="middle"
          :fill="agent.sse_connected ? 'white' : '#9ca3af'"
          font-size="11"
          font-weight="500"
        >
          {{ agent.display_name || agent.name }}
        </text>
        <text
          v-if="agent.label"
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
        class="cursor-pointer"
        :transform="`translate(${ch.px}, ${ch.py})`"
        @click.stop="emit('hex-click', { q: ch.hex_q, r: ch.hex_r, type: 'corridor', entityId: ch.entity_id })"
      >
        <polygon
          :points="corridorHexPoints(0, 0)"
          fill="transparent"
          stroke="none"
        />
        <template v-for="(arm, i) in ch.arms" :key="i">
          <line
            :x1="arm.x1a" :y1="arm.y1a" :x2="arm.x2a" :y2="arm.y2a"
            stroke="#06b6d4" :stroke-width="RAIL_WIDTH_2D" stroke-linecap="round" opacity="0.7"
          />
          <line
            :x1="arm.x1b" :y1="arm.y1b" :x2="arm.x2b" :y2="arm.y2b"
            stroke="#06b6d4" :stroke-width="RAIL_WIDTH_2D" stroke-linecap="round" opacity="0.7"
          />
        </template>
        <circle cx="0" cy="0" :r="JUNCTION_R_2D" fill="#06b6d4" opacity="0.6" />
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
        class="cursor-pointer"
        :transform="`translate(${hh.px}, ${hh.py})`"
        @click.stop="emit('hex-click', { q: hh.hex_q, r: hh.hex_r, type: 'human', entityId: hh.entity_id })"
      >
        <polygon
          :points="humanHexPoints(0, 0)"
          :fill="(hh.color || '#f59e0b') + '22'"
          :stroke="hh.color || '#f59e0b'"
          stroke-width="2"
          opacity="0.9"
        />
        <text y="-4" text-anchor="middle" :fill="hh.color || '#f59e0b'" font-size="14">
          &#9775;
        </text>
        <text y="12" text-anchor="middle" fill="#d4d4d8" font-size="8" font-weight="500">
          {{ hh.display_name || 'Human' }}
        </text>
      </g>

      <!-- Message flow animation particles -->
      <g class="flow-anim-layer">
        <circle
          v-for="p in particles"
          :key="p.id"
          :cx="getParticlePosition(p).x"
          :cy="getParticlePosition(p).y"
          r="4"
          :fill="p.color"
          :opacity="1 - p.progress * 0.5"
        />
      </g>

      <!-- Hex pulse on message arrival -->
      <g class="pulse-layer">
        <template v-for="pulse in pulses" :key="pulse.key">
          <circle
            :cx="axialToWorld(Number(pulse.key.split(',')[0]), Number(pulse.key.split(',')[1])).x * SCALE"
            :cy="axialToWorld(Number(pulse.key.split(',')[0]), Number(pulse.key.split(',')[1])).y * SCALE"
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
        v-if="selectedHex && !isMovingHex && agents.some(a => a.hex_q === selectedHex!.q && a.hex_r === selectedHex!.r)"
        :transform="`translate(${axialToWorld(selectedHex!.q, selectedHex!.r).x * SCALE}, ${axialToWorld(selectedHex!.q, selectedHex!.r).y * SCALE})`"
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
        v-if="isMovingHex && movingHexSource"
        :transform="`translate(${axialToWorld(movingHexSource.q, movingHexSource.r).x * SCALE}, ${axialToWorld(movingHexSource.q, movingHexSource.r).y * SCALE})`"
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
