<script setup lang="ts">
import { ref, watch } from 'vue'
import { X, Save, Loader2 } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  open: boolean
  workspaceId: string
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const store = useWorkspaceStore()
const notes = ref('')
const saving = ref(false)

watch(() => props.open, (isOpen) => {
  if (isOpen && store.blackboard) {
    notes.value = store.blackboard.manual_notes
  }
})

async function save() {
  saving.value = true
  try {
    await store.updateBlackboard(props.workspaceId, notes.value)
  } catch (e) {
    console.error('save blackboard error:', e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Transition name="fade">
    <div
      v-if="open"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      @click.self="emit('close')"
    >
      <div class="w-full max-w-2xl mx-4 bg-card border border-border rounded-xl shadow-2xl flex flex-col max-h-[80vh]">
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <h2 class="text-lg font-semibold">中央黑板</h2>
          <button class="p-1 rounded hover:bg-muted" @click="emit('close')">
            <X class="w-5 h-5" />
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4 min-h-0">
          <!-- Auto summary -->
          <div>
            <h3 class="text-sm font-medium text-muted-foreground mb-2">自动摘要</h3>
            <div class="bg-muted rounded-lg p-3 text-sm whitespace-pre-wrap min-h-[60px]">
              {{ store.blackboard?.auto_summary || '暂无自动摘要...' }}
            </div>
          </div>

          <!-- Manual notes -->
          <div>
            <h3 class="text-sm font-medium text-muted-foreground mb-2">手动备注</h3>
            <textarea
              v-model="notes"
              rows="8"
              class="w-full bg-muted rounded-lg p-3 text-sm resize-none outline-none focus:ring-1 focus:ring-primary/50"
              placeholder="在此添加备注..."
            />
          </div>
        </div>

        <!-- Footer -->
        <div class="flex justify-end gap-2 px-5 py-3 border-t border-border shrink-0">
          <button
            class="px-4 py-2 text-sm rounded-lg bg-muted hover:bg-muted/80 transition-colors"
            @click="emit('close')"
          >
            取消
          </button>
          <button
            class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-2 disabled:opacity-50"
            :disabled="saving"
            @click="save"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            保存
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
