<script setup lang="ts">
import { X, Plus, MessageSquare, ExternalLink, Trash2, PenSquare } from 'lucide-vue-next'

defineProps<{
  open: boolean
  hexType: 'empty' | 'agent' | 'blackboard'
  hexPosition: { q: number, r: number }
  agentInfo?: { id: string, name: string }
  chatSidebarOpen?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'action', name: string): void
}>()
</script>

<template>
  <Transition name="slide-up">
    <div
      v-if="open"
      class="fixed bottom-0 -translate-x-1/2 z-40 w-60 bg-card border border-border shadow-2xl rounded-t-xl transition-[left] duration-300"
      :style="{ left: chatSidebarOpen ? 'calc(50% - 200px)' : '50%' }"
    >
      <div class="flex items-center justify-between px-4 py-2.5 border-b border-border/50">
        <span class="text-sm font-medium text-foreground">
          <template v-if="hexType === 'empty'">
            空工位
          </template>
          <template v-else-if="hexType === 'agent'">
            {{ agentInfo?.name || 'Agent' }}
          </template>
          <template v-else>
            中央黑板
          </template>
        </span>
        <button
          class="p-1 rounded hover:bg-muted transition-colors"
          @click="emit('close')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <div class="flex flex-col gap-0.5 px-2 py-2">
        <!-- Empty hex actions -->
        <template v-if="hexType === 'empty'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'add-agent')"
          >
            <Plus class="w-4 h-4 text-primary" />
            <span>添加 Agent 到此工位</span>
          </button>
        </template>

        <!-- Agent hex actions -->
        <template v-else-if="hexType === 'agent'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'open-chat')"
          >
            <MessageSquare class="w-4 h-4 text-primary" />
            <span>打开对话</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'view-detail')"
          >
            <ExternalLink class="w-4 h-4 text-muted-foreground" />
            <span>查看详情</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors text-sm"
            @click="emit('action', 'remove-agent')"
          >
            <Trash2 class="w-4 h-4" />
            <span>移除</span>
          </button>
        </template>

        <!-- Blackboard actions -->
        <template v-else>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'edit-blackboard')"
          >
            <PenSquare class="w-4 h-4 text-primary" />
            <span>编辑黑板</span>
          </button>
        </template>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active {
  transition: transform 0.25s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  transform: translateY(100%);
}
</style>
