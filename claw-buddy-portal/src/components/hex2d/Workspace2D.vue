<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSvgZoom } from '@/composables/useSvgZoom'
import { axialToWorld, hexPolygonPoints, HEX_SIZE } from '@/composables/useHexLayout'
import type { AgentBrief } from '@/stores/workspace'

const props = defineProps<{
  agents: AgentBrief[]
  autoSummary: string
  manualNotes: string
  selectedAgentId: string | null
  selectedHex: { q: number, r: number } | null
}>()

const emit = defineEmits<{
  (e: 'hex-click', payload: { q: number, r: number, type: 'empty' | 'agent' | 'blackboard', agentId?: string }): void
  (e: 'agent-dblclick', id: string): void
  (e: 'agent-hover', id: string | null): void
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const { transformStr, zoomIn, zoomOut, resetView, panBy } = useSvgZoom(svgRef, { minZoom: 0.3, maxZoom: 3 })

defineExpose({ zoomIn, zoomOut, resetView, panBy })

const hoveredId = ref<string | null>(null)

const SCALE = 60
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

const emptyHexes = computed(() => {
  const occupied = new Set<string>()
  occupied.add('0:0')
  for (const a of props.agents) occupied.add(`${a.hex_q}:${a.hex_r}`)
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
          :fill="selectedHex?.q === hex.q && selectedHex?.r === hex.r ? '#60a5fa11' : 'transparent'"
          :stroke="selectedHex?.q === hex.q && selectedHex?.r === hex.r ? '#60a5fa' : 'transparent'"
          :stroke-width="selectedHex?.q === hex.q && selectedHex?.r === hex.r ? 2 : 0"
          class="hover-empty-hex"
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
          中央黑板
        </text>
        <text x="0" y="-2" text-anchor="middle" fill="#9ca3af" font-size="9">
          {{ autoSummary?.slice(0, 24) || '暂无摘要' }}{{ (autoSummary?.length ?? 0) > 24 ? '...' : '' }}
        </text>
        <text x="0" y="16" text-anchor="middle" fill="#6b7280" font-size="8">
          {{ manualNotes?.slice(0, 30) || '点击编辑备注' }}{{ (manualNotes?.length ?? 0) > 30 ? '...' : '' }}
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
            'animate-hex-thinking': agent.sse_connected && (agent.status === 'thinking' || agent.status === 'pending'),
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
          y="0"
          text-anchor="middle"
          :fill="agent.sse_connected ? 'white' : '#9ca3af'"
          font-size="11"
          font-weight="500"
        >
          {{ agent.display_name || agent.name }}
        </text>
      </g>

      <!-- Selected hex highlight for agents -->
      <g
        v-if="selectedHex && agents.some(a => a.hex_q === selectedHex!.q && a.hex_r === selectedHex!.r)"
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
</style>
