<script setup lang="ts">
/**
 * 实时事件时间线 — Dashboard / 通知面板使用。
 */
import type { FeedEvent } from '@/types/activity'

export type { FeedEvent }

withDefaults(defineProps<{
  events: FeedEvent[]
  maxItems?: number
}>(), {
  maxItems: 20,
})

const dotColor: Record<string, string> = {
  info: 'bg-[#60a5fa]',
  success: 'bg-[#4ade80]',
  warning: 'bg-[#fbbf24]',
  error: 'bg-[#f87171]',
}
</script>

<template>
  <div class="space-y-0">
    <div
      v-for="event in events.slice(0, maxItems)"
      :key="event.id"
      class="flex items-start gap-3 py-2 px-1 animate-fade-in-up"
    >
      <!-- 时间线圆点 -->
      <div class="mt-1.5 flex flex-col items-center">
        <span :class="['w-2 h-2 rounded-full', dotColor[event.type]]" />
        <span class="w-px flex-1 bg-border mt-1" />
      </div>
      <!-- 内容 -->
      <div class="flex-1 min-w-0">
        <p class="text-sm text-foreground truncate">{{ event.message }}</p>
        <p class="text-xs text-muted-foreground mt-0.5">{{ event.time }}</p>
      </div>
    </div>

    <div v-if="events.length === 0" class="text-sm text-muted-foreground text-center py-8">
      暂无动态
    </div>
  </div>
</template>
