<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { X, Save, Loader2, Target, ListTodo, Users, BarChart3, FileText, Network } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'

const props = defineProps<{
  open: boolean
  workspaceId: string
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const store = useWorkspaceStore()
const activeTab = ref('tasks')
const notes = ref('')
const saving = ref(false)

const tabs = [
  { key: 'objectives', label: '目标', icon: Target },
  { key: 'tasks', label: '任务', icon: ListTodo },
  { key: 'status', label: '状态', icon: Users },
  { key: 'performance', label: '绩效', icon: BarChart3 },
  { key: 'notes', label: '笔记', icon: FileText },
  { key: 'topology', label: '拓扑', icon: Network },
]

const objectives = computed(() => store.blackboard?.objectives || [])
const tasks = computed(() => store.blackboard?.tasks || [])
const memberStatus = computed(() => store.blackboard?.member_status || [])
const performance = computed(() => store.blackboard?.performance || [])

const tasksByStatus = computed(() => {
  const groups: Record<string, unknown[]> = { todo: [], doing: [], done: [], blocked: [] }
  for (const t of tasks.value) {
    const s = (t as Record<string, unknown>).status as string || 'todo'
    if (groups[s]) groups[s].push(t)
    else groups.todo.push(t)
  }
  return groups
})

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

const statusColors: Record<string, string> = {
  running: 'bg-green-500',
  active: 'bg-green-500',
  online: 'bg-green-500',
  idle: 'bg-gray-400',
  error: 'bg-red-500',
  failed: 'bg-red-500',
  deploying: 'bg-yellow-500',
}

const priorityColors: Record<string, string> = {
  high: 'bg-red-500/20 text-red-400',
  medium: 'bg-yellow-500/20 text-yellow-400',
  low: 'bg-blue-500/20 text-blue-400',
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
          <button class="p-1 rounded hover:bg-muted" @click="emit('close')">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="flex border-b border-border px-2 shrink-0">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            class="flex items-center gap-1.5 px-3 py-2 text-sm transition-colors border-b-2"
            :class="activeTab === tab.key ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'"
            @click="activeTab = tab.key"
          >
            <component :is="tab.icon" class="w-4 h-4" />
            {{ tab.label }}
          </button>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 min-h-0">
          <!-- Objectives Tab -->
          <div v-if="activeTab === 'objectives'" class="space-y-3">
            <div v-if="!objectives.length" class="text-sm text-muted-foreground">暂无目标</div>
            <div
              v-for="obj in objectives"
              :key="(obj as Record<string, unknown>).id as string"
              class="bg-muted rounded-lg p-4"
            >
              <h4 class="font-medium text-sm">{{ (obj as Record<string, unknown>).title }}</h4>
              <div v-if="(obj as Record<string, unknown>).key_results" class="mt-2 space-y-1.5">
                <div
                  v-for="(kr, i) in (obj as Record<string, unknown>).key_results as unknown[]"
                  :key="i"
                  class="flex items-center gap-2"
                >
                  <div class="flex-1 text-xs text-muted-foreground">{{ (kr as Record<string, unknown>).desc }}</div>
                  <div class="w-24 bg-background rounded-full h-1.5">
                    <div
                      class="bg-primary h-1.5 rounded-full"
                      :style="{
                        width: `${Math.min(100, ((kr as Record<string, unknown>).current as number || 0) / ((kr as Record<string, unknown>).target as number || 1) * 100)}%`
                      }"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Tasks Tab (Kanban) -->
          <div v-if="activeTab === 'tasks'" class="grid grid-cols-4 gap-3 min-h-[300px]">
            <div v-for="(col, status) in tasksByStatus" :key="status" class="flex flex-col">
              <div class="text-xs font-medium text-muted-foreground uppercase mb-2">{{ status }} ({{ col.length }})</div>
              <div class="flex-1 space-y-2">
                <div
                  v-for="task in col"
                  :key="(task as Record<string, unknown>).id as string"
                  class="bg-muted rounded-lg p-2.5 text-xs"
                >
                  <div class="font-medium mb-1">{{ (task as Record<string, unknown>).title }}</div>
                  <div class="flex items-center gap-1.5">
                    <span
                      v-if="(task as Record<string, unknown>).priority"
                      class="px-1.5 py-0.5 rounded text-[10px]"
                      :class="priorityColors[(task as Record<string, unknown>).priority as string] || ''"
                    >
                      {{ (task as Record<string, unknown>).priority }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Status Tab -->
          <div v-if="activeTab === 'status'" class="space-y-2">
            <div v-if="!memberStatus.length" class="text-sm text-muted-foreground">暂无成员状态</div>
            <div
              v-for="member in memberStatus"
              :key="(member as Record<string, unknown>).id as string"
              class="flex items-center gap-3 bg-muted rounded-lg p-3"
            >
              <div
                class="w-2 h-2 rounded-full"
                :class="statusColors[(member as Record<string, unknown>).status as string] || 'bg-gray-400'"
              />
              <div class="flex-1">
                <div class="text-sm font-medium">{{ (member as Record<string, unknown>).name || (member as Record<string, unknown>).id }}</div>
                <div class="text-xs text-muted-foreground">{{ (member as Record<string, unknown>).type }} - {{ (member as Record<string, unknown>).status }}</div>
              </div>
              <div class="text-xs text-muted-foreground">
                {{ (member as Record<string, unknown>).last_activity ? '活跃' : '' }}
              </div>
            </div>
          </div>

          <!-- Performance Tab -->
          <div v-if="activeTab === 'performance'" class="space-y-3">
            <div v-if="!performance.length" class="text-sm text-muted-foreground">暂无绩效数据</div>
            <div
              v-for="perf in performance"
              :key="(perf as Record<string, unknown>).member_id as string"
              class="bg-muted rounded-lg p-3"
            >
              <div class="text-sm font-medium mb-2">{{ (perf as Record<string, unknown>).member_id }}</div>
              <div
                v-for="(metric, i) in ((perf as Record<string, unknown>).metrics as unknown[] || [])"
                :key="i"
                class="flex items-center justify-between text-xs"
              >
                <span class="text-muted-foreground">{{ (metric as Record<string, unknown>).name }}</span>
                <span>{{ (metric as Record<string, unknown>).value }} / {{ (metric as Record<string, unknown>).target }}</span>
              </div>
            </div>
          </div>

          <!-- Notes Tab -->
          <div v-if="activeTab === 'notes'" class="space-y-4">
            <div>
              <h3 class="text-sm font-medium text-muted-foreground mb-2">自动摘要</h3>
              <div class="bg-muted rounded-lg p-3 text-sm whitespace-pre-wrap min-h-[60px]">
                {{ store.blackboard?.auto_summary || '暂无自动摘要...' }}
              </div>
            </div>
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

          <!-- Topology Tab -->
          <div v-if="activeTab === 'topology'" class="space-y-3">
            <div class="text-sm text-muted-foreground">
              拓扑监控数据将在消息流量积累后显示。
            </div>
            <div v-if="store.topology" class="bg-muted rounded-lg p-3 text-xs">
              <div>节点: {{ store.topology.nodes.length }}</div>
              <div>连接: {{ store.topology.edges.length }}</div>
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 px-5 py-3 border-t border-border shrink-0">
          <button
            class="px-4 py-2 text-sm rounded-lg bg-muted hover:bg-muted/80 transition-colors"
            @click="emit('close')"
          >
            关闭
          </button>
          <button
            v-if="activeTab === 'notes'"
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
