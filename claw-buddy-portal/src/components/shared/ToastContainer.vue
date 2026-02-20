<script setup lang="ts">
import { useToast } from '@/composables/useToast'
import { X, CheckCircle2, AlertCircle, Info } from 'lucide-vue-next'

const { toasts, remove } = useToast()

const icons = { success: CheckCircle2, error: AlertCircle, info: Info }
const colors = {
  success: 'border-green-500/30 bg-green-500/10 text-green-400',
  error: 'border-red-500/30 bg-red-500/10 text-red-400',
  info: 'border-blue-500/30 bg-blue-500/10 text-blue-400',
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-9999 flex flex-col gap-2 w-80">
      <TransitionGroup
        enter-active-class="transition-all duration-300 ease-out"
        leave-active-class="transition-all duration-200 ease-in"
        enter-from-class="opacity-0 translate-x-8"
        enter-to-class="opacity-100 translate-x-0"
        leave-from-class="opacity-100 translate-x-0"
        leave-to-class="opacity-0 translate-x-8"
      >
        <div
          v-for="t in toasts"
          :key="t.id"
          class="flex items-start gap-2 px-4 py-3 rounded-lg border backdrop-blur-sm text-sm shadow-lg"
          :class="colors[t.type]"
        >
          <component :is="icons[t.type]" class="w-4 h-4 mt-0.5 shrink-0" />
          <span class="flex-1">{{ t.message }}</span>
          <button class="shrink-0 opacity-60 hover:opacity-100 transition-opacity" @click="remove(t.id)">
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
