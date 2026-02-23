<script setup lang="ts">
import { computed } from 'vue'
import { axialToWorld, hexPolygonPoints, HEX_SIZE } from '@/composables/useHexLayout'
import type { AgentBrief } from '@/stores/workspace'

const props = defineProps<{
  agents: AgentBrief[]
  color: string
}>()

const SCALE = 20

const hexes = computed(() =>
  props.agents.map((a) => {
    const { x, y } = axialToWorld(a.hex_q, a.hex_r)
    return {
      id: a.instance_id,
      cx: x * SCALE,
      cy: y * SCALE,
      status: a.status,
      points: hexPolygonPoints(x * SCALE, y * SCALE, HEX_SIZE * SCALE * 0.8),
    }
  }),
)

const statusColors: Record<string, string> = {
  running: '#4ade80', active: '#4ade80',
  thinking: '#fbbf24', pending: '#fbbf24',
  idle: '#6b7280',
  error: '#f87171', failed: '#f87171',
  restarting: '#f97316', deploying: '#f97316', updating: '#f97316', creating: '#f97316',
}
</script>

<template>
  <svg viewBox="-100 -80 200 160" class="w-full h-full opacity-60 group-hover:opacity-80 transition-opacity">
    <!-- Center blackboard hex -->
    <polygon
      :points="hexPolygonPoints(0, 0, 10)"
      :fill="color + '44'"
      :stroke="color"
      stroke-width="1"
    />

    <!-- Agent hexes -->
    <polygon
      v-for="hex in hexes"
      :key="hex.id"
      :points="hex.points"
      :fill="(statusColors[hex.status] || color) + '33'"
      :stroke="statusColors[hex.status] || color"
      stroke-width="1"
    />
  </svg>
</template>
