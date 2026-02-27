<script setup lang="ts">
import type { AgentBrief } from '@/stores/workspace'

defineProps<{
  agent: AgentBrief | null
  x?: number
  y?: number
}>()

const statusLabels: Record<string, string> = {
  running: '运行中', active: '活跃', thinking: '思考中', learning: '学习中',
  pending: '等待中', idle: '空闲', error: '错误', failed: '失败',
  restarting: '重启中', deploying: '部署中', updating: '更新中', creating: '创建中',
}
</script>

<template>
  <Transition name="fade">
    <div
      v-if="agent"
      class="absolute z-50 px-3 py-2 rounded-lg bg-card/95 border border-border shadow-xl backdrop-blur-md text-xs pointer-events-none"
      :style="{ left: `${(x ?? 0) + 16}px`, top: `${(y ?? 0) - 10}px` }"
    >
      <div class="font-semibold text-foreground">
        {{ agent.display_name || agent.name }}
      </div>
      <div class="text-muted-foreground mt-0.5">
        状态: {{ statusLabels[agent.status] || agent.status }}
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
