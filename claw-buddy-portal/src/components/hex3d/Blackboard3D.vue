<script setup lang="ts">
defineProps<{
  taskCount: number
  blockedCount: number
  onlineCount: number
  autoSummary: string
}>()
</script>

<template>
  <slot />
</template>
