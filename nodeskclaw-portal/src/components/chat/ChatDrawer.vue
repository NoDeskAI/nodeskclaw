<script setup lang="ts">
import ChatPanel from './ChatPanel.vue'
import { X, MessageSquare } from 'lucide-vue-next'

const props = defineProps<{
  open: boolean
  workspaceId: string
  workspaceName: string
}>()

const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <Transition name="slide-up">
    <div
      v-if="open"
      class="fixed inset-x-0 bottom-0 z-40 flex flex-col bg-card border-t border-border shadow-2xl"
      style="height: 50vh; max-height: 500px;"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-2 border-b border-border shrink-0">
        <div class="flex items-center gap-2">
          <MessageSquare class="w-4 h-4 text-primary" />
          <span class="text-sm font-medium">{{ workspaceName }}</span>
          <span class="text-xs text-muted-foreground">Group Chat</span>
        </div>
        <button
          class="p-1 rounded hover:bg-muted transition-colors"
          @click="emit('close')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Chat -->
      <ChatPanel
        :workspace-id="workspaceId"
        class="flex-1 min-h-0"
      />
    </div>
  </Transition>
</template>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active {
  transition: transform 0.3s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  transform: translateY(100%);
}
</style>
