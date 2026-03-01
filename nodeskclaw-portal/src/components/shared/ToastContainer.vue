<script setup lang="ts">
import { useToast } from '@/composables/useToast'
import { X } from 'lucide-vue-next'

const { toasts, remove } = useToast()

const typeClasses: Record<string, string> = {
  success: 'bg-green-600 text-white',
  error: 'bg-red-600 text-white',
  info: 'bg-zinc-800 text-white',
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm">
      <TransitionGroup
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0 translate-x-4"
        enter-to-class="opacity-100 translate-x-0"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100 translate-x-0"
        leave-to-class="opacity-0 translate-x-4"
      >
        <div
          v-for="t in toasts"
          :key="t.id"
          :class="[typeClasses[t.type], 'px-4 py-3 rounded-lg shadow-lg text-sm flex items-center justify-between gap-2']"
        >
          <div class="flex flex-col gap-1">
            <span>{{ t.message }}</span>
            <button
              v-if="t.action"
              class="text-xs underline opacity-80 hover:opacity-100 text-left"
              @click="t.action.onClick(); remove(t.id)"
            >
              {{ t.action.label }}
            </button>
          </div>
          <button class="shrink-0 opacity-70 hover:opacity-100" @click="remove(t.id)">
            <X class="w-4 h-4" />
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
