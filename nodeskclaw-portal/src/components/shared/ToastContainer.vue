<script setup lang="ts">
import { useToast } from '@/composables/useToast'
import { CircleCheck, CircleX, Info, TriangleAlert, X } from 'lucide-vue-next'

const { toasts, dismiss } = useToast()

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
    <div class="fixed top-4 left-1/2 -translate-x-1/2 z-9999 flex flex-col items-center gap-2 pointer-events-none">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          :class="[
            'pointer-events-auto flex items-start gap-2.5 px-4 py-2.5 rounded-lg border shadow-lg backdrop-blur-sm',
            'text-sm font-medium min-w-[200px] max-w-[380px]',
            colorMap[t.type],
            t.leaving ? 'toast-leave-active' : '',
          ]"
        >
          <component :is="iconMap[t.type]" class="w-4 h-4 shrink-0 mt-0.5" />
          <div class="flex-1 flex flex-col gap-1">
            <span class="wrap-break-word">{{ t.message }}</span>
            <button
              v-if="t.action"
              class="text-xs underline opacity-70 hover:opacity-100 text-left transition-opacity"
              @click="t.action.onClick(); dismiss(t.id)"
            >
              {{ t.action.label }}
            </button>
          </div>
          <button
            class="shrink-0 opacity-50 hover:opacity-100 transition-opacity"
            @click="dismiss(t.id)"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(-100%);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}
.toast-move {
  transition: transform 0.3s ease;
}
</style>
