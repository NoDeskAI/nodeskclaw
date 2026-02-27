<script setup lang="ts">
import type { ViewMode } from '@/composables/useViewTransition'

defineProps<{ mode: ViewMode }>()
const emit = defineEmits<{ (e: 'toggle'): void }>()
</script>

<template>
  <div
    class="flex items-center gap-1 bg-card/50 border border-border rounded-full p-0.5 backdrop-blur-sm"
  >
    <button
      class="px-3 py-1 rounded-full text-xs font-medium transition-all"
      :class="mode === '3d' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
      @click="mode !== '3d' && emit('toggle')"
    >
      3D
    </button>
    <button
      class="px-3 py-1 rounded-full text-xs font-medium transition-all"
      :class="mode === '2d' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
      @click="mode !== '2d' && emit('toggle')"
    >
      2D
    </button>
  </div>
</template>
