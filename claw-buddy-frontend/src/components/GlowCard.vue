<script setup lang="ts">
/**
 * 发光边框卡片 — 左边框颜色随 status 变化，hover 时发光。
 * 参考 Vibecraft 的 glow 效果。
 */
withDefaults(defineProps<{
  status?: 'running' | 'warning' | 'error' | 'default'
}>(), {
  status: 'default',
})

const colorMap: Record<string, string> = {
  running: '#4ade80',
  warning: '#fbbf24',
  error: '#f87171',
  default: '#a78bfa',
}
</script>

<template>
  <div
    class="relative rounded-lg bg-card border border-border p-4 transition-all duration-150 hover:border-opacity-20"
    :style="{
      borderLeftWidth: '3px',
      borderLeftColor: colorMap[status],
      '--glow-color': colorMap[status],
    }"
  >
    <slot />
  </div>
</template>
