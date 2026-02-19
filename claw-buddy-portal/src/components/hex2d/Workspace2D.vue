<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSvgZoom } from '@/composables/useSvgZoom'
import { axialToWorld, hexPolygonPoints, HEX_SIZE } from '@/composables/useHexLayout'
import type { AgentBrief } from '@/stores/workspace'

const props = defineProps<{
  agents: AgentBrief[]
  autoSummary: string
  manualNotes: string
}>()

const emit = defineEmits<{
  (e: 'agent-click', id: string): void
  (e: 'agent-hover', id: string | null): void
  (e: 'blackboard-click'): void
  (e: 'add-agent-click'): void
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const { transformStr, zoomIn, zoomOut, resetView } = useSvgZoom(svgRef, { minZoom: 0.3, maxZoom: 3 })

defineExpose({ zoomIn, zoomOut, resetView })

const hoveredId = ref<string | null>(null)

const SCALE = 60
const HEX_RADIUS = HEX_SIZE * SCALE * 0.85
const BB_RADIUS = HEX_RADIUS * 1.15
const GRID_RANGE = 8

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

function nextAddPosition(): { px: number; py: number } {
  const idx = props.agents.length
  const directions: [number, number][] = [[0, -1], [-1, 0], [-1, 1], [0, 1], [1, 0], [1, -1]]
  let q = 1, r = 0, ring = 1
  const positions: [number, number][] = []
  while (positions.length <= idx) {
    for (const [dq, dr] of directions) {
      for (let s = 0; s < ring && positions.length <= idx; s++) {
        positions.push([q, r])
        q += dq; r += dr
      }
    }
    ring++; q++
  }
  if (positions.length > idx) {
    const [aq, ar] = positions[idx]
    const { x, y } = axialToWorld(aq, ar)
    return { px: x * SCALE, py: y * SCALE }
  }
  return { px: 200, py: 0 }
}

const addPos = computed(() => nextAddPosition())
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

      <!-- Blackboard hex at center (q=0, r=0) -->
      <g
        class="cursor-pointer bb-hex"
        @click="emit('blackboard-click')"
        @pointerenter="hoveredId = '__blackboard__'"
        @pointerleave="hoveredId = null"
      >
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
        @click="emit('agent-click', agent.instance_id)"
        @pointerenter="hoveredId = agent.instance_id; emit('agent-hover', agent.instance_id)"
        @pointerleave="hoveredId = null; emit('agent-hover', null)"
      >
        <polygon
          :points="hexPoints(0, 0)"
          :fill="(statusColors[agent.status] || '#a78bfa') + '22'"
          :stroke="statusColors[agent.status] || '#a78bfa'"
          stroke-width="2"
          :class="{
            'animate-pulse': agent.status === 'running' || agent.status === 'active',
            'animate-hex-thinking': agent.status === 'thinking' || agent.status === 'pending',
          }"
        />
        <text
          y="-8"
          text-anchor="middle"
          fill="white"
          font-size="11"
          font-weight="500"
        >
          {{ agent.display_name || agent.name }}
        </text>
        <text
          y="10"
          text-anchor="middle"
          :fill="statusColors[agent.status] || '#a78bfa'"
          font-size="9"
        >
          {{ agent.status }}
        </text>
      </g>

      <!-- Add agent placeholder -->
      <g
        class="cursor-pointer opacity-40 hover:opacity-70 transition-opacity"
        :transform="`translate(${addPos.px}, ${addPos.py})`"
        @click="emit('add-agent-click')"
      >
        <polygon
          :points="hexPoints(0, 0)"
          fill="none"
          stroke="#555577"
          stroke-width="2"
          stroke-dasharray="8,4"
        />
        <text y="4" text-anchor="middle" fill="#888" font-size="24" font-weight="300">+</text>
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

.bb-hex {
  transition: transform 0.2s ease;
}
.bb-hex:hover {
  transform: scale(1.04);
}
</style>
