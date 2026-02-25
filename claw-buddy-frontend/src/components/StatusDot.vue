<script setup lang="ts">
/**
 * 状态指示灯 — 4 色 glow 圆点。
 */
withDefaults(defineProps<{
  status: 'running' | 'learning' | 'pending' | 'failed' | 'unknown'
  size?: 'sm' | 'md'
}>(), {
  size: 'sm',
})

const colorMap: Record<string, string> = {
  running: 'bg-[#4ade80]',
  learning: 'bg-[#60a5fa]',
  pending: 'bg-[#fbbf24]',
  failed: 'bg-[#f87171]',
  unknown: 'bg-[#666666]',
}

const glowMap: Record<string, string> = {
  running: 'shadow-[0_0_6px_#4ade80]',
  learning: 'shadow-[0_0_6px_#60a5fa]',
  pending: 'shadow-[0_0_6px_#fbbf24]',
  failed: 'shadow-[0_0_6px_#f87171]',
  unknown: '',
}

const sizeMap: Record<string, string> = {
  sm: 'w-2 h-2',
  md: 'w-3 h-3',
}
</script>

<template>
  <span
    :class="[
      'inline-block rounded-full',
      sizeMap[size],
      colorMap[status],
      glowMap[status],
      status === 'pending' || status === 'learning' ? 'animate-dot-pulse' : '',
    ]"
  />
</template>
