<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { X, Save, Loader2, Pencil, Eye, Wifi, WifiOff, Circle } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { useFeature } from '@/composables/useFeature'
import { useI18n } from 'vue-i18n'
import { renderMarkdown } from '@/utils/markdown'
import TaskKanban from './TaskKanban.vue'
import ObjectivePanel from './ObjectivePanel.vue'
import RoiDashboard from './RoiDashboard.vue'
import TopologyGraph from './TopologyGraph.vue'

const props = withDefaults(defineProps<{
  open: boolean
  workspaceId: string
  embedded?: boolean
  canEdit?: boolean
}>(), { embedded: false, canEdit: true })

const emit = defineEmits<{ (e: 'close'): void }>()

const { t } = useI18n()
const store = useWorkspaceStore()
const { isEnabled: isPerformanceEnabled } = useFeature('performance_analytics')

type TabKey = 'objectives-tasks' | 'status' | 'notes-perf' | 'topology'
const activeTab = ref<TabKey>('objectives-tasks')

const tabs: { key: TabKey; labelKey: string }[] = [
  { key: 'objectives-tasks', labelKey: 'blackboard.tabObjectivesTasks' },
  { key: 'status', labelKey: 'blackboard.tabStatus' },
  { key: 'notes-perf', labelKey: 'blackboard.tabNotesPerf' },
  { key: 'topology', labelKey: 'blackboard.tabTopology' },
]

const editing = ref(false)
const draft = ref('')
const saving = ref(false)
const taskKanbanRef = ref<InstanceType<typeof TaskKanban> | null>(null)
const objectivePanelRef = ref<InstanceType<typeof ObjectivePanel> | null>(null)
const roiDashboardRef = ref<InstanceType<typeof RoiDashboard> | null>(null)

const fullContent = computed(() => store.blackboard?.content || '')

function renderMd(raw: string): string {
  if (!raw.trim()) return `<p class="text-muted-foreground text-sm">${t('blackboard.noContent')}</p>`
  return renderMarkdown(raw)
}

const notesHtml = computed(() => renderMd(fullContent.value))

const agents = computed(() => store.currentWorkspace?.agents || [])
const members = computed(() => store.members)
const topoNodes = computed(() => store.topology?.nodes || [])
const topoEdges = computed(() => store.topology?.edges || [])

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    editing.value = false
    activeTab.value = 'objectives-tasks'
  }
})

function enterEdit() {
  if (activeTab.value === 'notes-perf') {
    draft.value = fullContent.value
    editing.value = true
  }
}

async function save() {
  saving.value = true
  try {
    await store.updateBlackboard(props.workspaceId, draft.value.trim())
    editing.value = false
  } catch (e) {
    console.error('save blackboard error:', e)
  } finally {
    saving.value = false
  }
}

const canEditTab = computed(() => activeTab.value === 'notes-perf')

</script>

<template>
  <Transition :name="embedded ? '' : 'fade'">
    <div
      v-if="open"
      :class="embedded
        ? 'flex flex-col flex-1 min-h-0'
        : 'fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm'"
      @click.self="!embedded && emit('close')"
    >
      <div :class="embedded
        ? 'flex flex-col flex-1 min-h-0'
        : 'w-full max-w-[80%] mx-4 bg-card border border-border rounded-xl shadow-2xl flex flex-col h-[85vh]'">
        <div class="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
          <h2 :class="embedded ? 'text-sm font-semibold' : 'text-lg font-semibold'">{{ t('hexAction.centralBlackboard') }}</h2>
          <div class="flex items-center gap-1">
            <button
              v-if="canEditTab && !editing"
              class="p-1.5 rounded hover:bg-muted transition-colors"
              :title="t('blackboard.edit')"
              @click="enterEdit"
            >
              <Pencil class="w-4 h-4" />
            </button>
            <button
              v-if="editing"
              class="p-1.5 rounded hover:bg-muted transition-colors"
              :title="t('blackboard.preview')"
              @click="editing = false"
            >
              <Eye class="w-4 h-4" />
            </button>
            <button v-if="!embedded" class="p-1.5 rounded hover:bg-muted transition-colors" @click="emit('close')">
              <X class="w-5 h-5" />
            </button>
          </div>
        </div>

        <div class="flex border-b border-border px-2 shrink-0">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="flex items-center gap-1.5 px-3 py-2 text-sm transition-colors border-b-2"
            :class="activeTab === tab.key
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'"
            @click="activeTab = tab.key; editing = false"
          >
            {{ t(tab.labelKey) }}
          </button>
        </div>

        <div :class="['flex-1 min-h-0', activeTab === 'topology' ? 'overflow-hidden' : 'overflow-y-auto px-5 py-4']">

          <template v-if="activeTab === 'objectives-tasks'">
            <div class="space-y-6">
              <ObjectivePanel ref="objectivePanelRef" :workspace-id="workspaceId" />
              <TaskKanban ref="taskKanbanRef" :workspace-id="workspaceId" />
              <RoiDashboard v-if="isPerformanceEnabled" ref="roiDashboardRef" :workspace-id="workspaceId" />
            </div>
          </template>

          <template v-if="activeTab === 'status'">
            <div v-if="agents.length === 0 && members.length === 0" class="text-muted-foreground text-sm">
              {{ t('blackboard.noMembers') }}
            </div>
            <div v-else class="space-y-4">
              <div v-if="agents.length > 0">
                <h3 class="text-sm font-medium mb-2 text-muted-foreground">AI 员工</h3>
                <div class="space-y-1.5">
                  <div
                    v-for="agent in agents"
                    :key="agent.instance_id"
                    class="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/50"
                  >
                    <div class="flex items-center gap-2">
                      <Circle class="w-2.5 h-2.5" :class="agent.status === 'running' ? 'text-green-500 fill-green-500' : 'text-muted-foreground fill-muted-foreground'" />
                      <span class="text-sm">{{ agent.display_name || agent.name }}</span>
                    </div>
                    <div class="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{{ agent.status }}</span>
                      <Wifi v-if="agent.sse_connected" class="w-3.5 h-3.5 text-green-500" />
                      <WifiOff v-else class="w-3.5 h-3.5 text-muted-foreground" />
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="members.length > 0">
                <h3 class="text-sm font-medium mb-2 text-muted-foreground">{{ t('blackboard.humanMembers') }}</h3>
                <div class="space-y-1.5">
                  <div
                    v-for="m in members"
                    :key="m.user_id"
                    class="flex items-center justify-between px-3 py-2 rounded-lg bg-muted/50"
                  >
                    <span class="text-sm">{{ m.user_name }}</span>
                    <span class="text-xs text-muted-foreground">{{ m.role }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <template v-if="activeTab === 'notes-perf'">
            <div v-if="editing">
              <textarea
                v-model="draft"
                rows="18"
                class="w-full bg-muted rounded-lg p-4 text-sm font-mono resize-none outline-none focus:ring-1 focus:ring-primary/50 min-h-[300px]"
                :placeholder="t('blackboard.editPlaceholder')"
              />
            </div>
            <div v-else class="prose prose-sm prose-invert max-w-none" v-html="notesHtml" />
          </template>

          <template v-if="activeTab === 'topology'">
            <div v-if="topoNodes.length === 0" class="px-5 py-4 text-muted-foreground text-sm">
              {{ t('blackboard.noTopology') }}
            </div>
            <TopologyGraph v-else :nodes="topoNodes" :edges="topoEdges" />
          </template>

        </div>

        <div v-if="editing" class="flex justify-end gap-2 px-5 py-3 border-t border-border shrink-0">
          <button
            class="px-4 py-2 text-sm rounded-lg bg-muted hover:bg-muted/80 transition-colors"
            @click="editing = false"
          >
            {{ t('blackboard.cancel') }}
          </button>
          <button
            class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-2 disabled:opacity-50"
            :disabled="saving"
            @click="save"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ t('blackboard.save') }}
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
