<script setup lang="ts">
import { CircleCheck, CircleX, Info, TriangleAlert, X } from 'lucide-vue-next'
import { useNotify } from './useNotify'

const { queue, dismiss } = useNotify()

const iconMap = {
  success: CircleCheck,
  error: CircleX,
  info: Info,
  warning: TriangleAlert,
}

const colorMap: Record<string, string> = {
  success: 'text-green-400 bg-green-400/10 border-green-400/20',
  error: 'text-red-400 bg-red-400/10 border-red-400/20',
  info: 'text-blue-400 bg-blue-400/10 border-blue-400/20',
  warning: 'text-yellow-400 bg-yellow-400/10 border-yellow-400/20',
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-9999 flex flex-col gap-2 pointer-events-none">
      <TransitionGroup name="notify">
        <div
          v-for="item in queue"
          :key="item.id"
          :class="[
            'pointer-events-auto flex items-start gap-2.5 px-4 py-2.5 rounded-lg border shadow-lg backdrop-blur-sm',
            'text-sm font-medium min-w-[200px] max-w-[380px]',
            colorMap[item.type],
            item.leaving ? 'notify-leave-active' : '',
          ]"
        >
          <component :is="iconMap[item.type]" class="w-4 h-4 shrink-0 mt-0.5" />
          <span class="flex-1 break-words">{{ item.message }}</span>
          <button
            class="shrink-0 opacity-50 hover:opacity-100 transition-opacity"
            @click="dismiss(item.id)"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.notify-enter-active,
.notify-leave-active {
  transition: all 0.3s ease;
}
.notify-enter-from {
  opacity: 0;
  transform: translateX(100%);
}
.notify-leave-to {
  opacity: 0;
  transform: translateX(100%);
}
.notify-move {
  transition: transform 0.3s ease;
}
</style>
