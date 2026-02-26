<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { X, Save, Loader2, Pencil, Eye } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { marked } from 'marked'

const props = defineProps<{
  open: boolean
  workspaceId: string
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const store = useWorkspaceStore()
const editing = ref(false)
const draft = ref('')
const saving = ref(false)

const renderedHtml = computed(() => {
  const raw = store.blackboard?.content || ''
  if (!raw.trim()) return '<p class="text-muted-foreground text-sm">暂无内容</p>'
  return marked.parse(raw) as string
})

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    editing.value = false
    draft.value = store.blackboard?.content || ''
  }
})

function enterEdit() {
  draft.value = store.blackboard?.content || ''
  editing.value = true
}

async function save() {
  saving.value = true
  try {
    await store.updateBlackboard(props.workspaceId, draft.value)
    editing.value = false
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
      <div class="w-full max-w-3xl mx-4 bg-card border border-border rounded-xl shadow-2xl flex flex-col max-h-[85vh]">
        <div class="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <h2 class="text-lg font-semibold">中央黑板</h2>
          <div class="flex items-center gap-1">
            <button
              v-if="!editing"
              class="p-1.5 rounded hover:bg-muted transition-colors"
              title="编辑"
              @click="enterEdit"
            >
              <Pencil class="w-4 h-4" />
            </button>
            <button
              v-else
              class="p-1.5 rounded hover:bg-muted transition-colors"
              title="预览"
              @click="editing = false"
            >
              <Eye class="w-4 h-4" />
            </button>
            <button class="p-1.5 rounded hover:bg-muted transition-colors" @click="emit('close')">
              <X class="w-5 h-5" />
            </button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 min-h-[350px]">
          <div v-if="editing">
            <textarea
              v-model="draft"
              rows="18"
              class="w-full bg-muted rounded-lg p-4 text-sm font-mono resize-none outline-none focus:ring-1 focus:ring-primary/50 min-h-[300px]"
              placeholder="使用 Markdown 编写黑板内容..."
            />
          </div>
          <div v-else class="prose prose-sm prose-invert max-w-none" v-html="renderedHtml" />
        </div>

        <div v-if="editing" class="flex justify-end gap-2 px-5 py-3 border-t border-border shrink-0">
          <button
            class="px-4 py-2 text-sm rounded-lg bg-muted hover:bg-muted/80 transition-colors"
            @click="editing = false"
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

:deep(.prose) {
  color: hsl(var(--foreground));
}
:deep(.prose h1),
:deep(.prose h2),
:deep(.prose h3) {
  color: hsl(var(--foreground));
  margin-top: 1.25em;
  margin-bottom: 0.5em;
}
:deep(.prose h1) { font-size: 1.5em; }
:deep(.prose h2) { font-size: 1.25em; }
:deep(.prose h3) { font-size: 1.1em; }
:deep(.prose p) { margin: 0.5em 0; }
:deep(.prose ul),
:deep(.prose ol) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}
:deep(.prose li) { margin: 0.25em 0; }
:deep(.prose code) {
  background: hsl(var(--muted));
  padding: 0.15em 0.35em;
  border-radius: 0.25em;
  font-size: 0.875em;
}
:deep(.prose pre) {
  background: hsl(var(--muted));
  padding: 0.75em 1em;
  border-radius: 0.5em;
  overflow-x: auto;
  margin: 0.75em 0;
}
:deep(.prose pre code) {
  background: none;
  padding: 0;
}
:deep(.prose blockquote) {
  border-left: 3px solid hsl(var(--border));
  padding-left: 1em;
  color: hsl(var(--muted-foreground));
  margin: 0.75em 0;
}
:deep(.prose hr) {
  border-color: hsl(var(--border));
  margin: 1em 0;
}
:deep(.prose a) {
  color: hsl(var(--primary));
  text-decoration: underline;
}
:deep(.prose table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.75em 0;
}
:deep(.prose th),
:deep(.prose td) {
  border: 1px solid hsl(var(--border));
  padding: 0.4em 0.75em;
  text-align: left;
}
:deep(.prose th) {
  background: hsl(var(--muted));
  font-weight: 600;
}
</style>
