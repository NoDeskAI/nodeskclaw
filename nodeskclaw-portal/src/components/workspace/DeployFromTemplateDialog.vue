<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, Loader2, ChevronRight, CheckCircle2, XCircle, Circle } from 'lucide-vue-next'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { useWorkspaceStore, type WorkspaceTemplateDetail } from '@/stores/workspace'
import { useClusterStore } from '@/stores/cluster'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useToast } from '@/composables/useToast'
import CustomSelect from '@/components/shared/CustomSelect.vue'
import Workspace2D from '@/components/hex2d/Workspace2D.vue'
import {
  buildTopoNodes,
  buildTopoEdges,
  buildMockAgents,
  specGeneSlugs as _specGeneSlugs,
  specLlmProviders as _specLlmProviders,
  resourceSummary as _resourceSummary,
  specGeneCount as _specGeneCount,
  allSelectableKeys,
  countAgentKeysInSelection,
  keysToSelectedIndices,
  keysToExcludedCorridorCoords,
} from '@/utils/templateTopology'

const props = defineProps<{
  open: boolean
  templateId?: string | null
  resumeDeployId?: string | null
}>()

const emit = defineEmits<{
  'update:open': [v: boolean]
  done: [workspaceId: string]
}>()

const { t } = useI18n()
const store = useWorkspaceStore()
const clusterStore = useClusterStore()
const toast = useToast()

const templateDetail = ref<WorkspaceTemplateDetail | null>(null)
const loadingDetail = ref(false)
const workspaceName = ref('')
const clusterId = ref<string | null>(null)
const submitting = ref(false)
const phase = ref<'form' | 'progress'>('form')
const deployId = ref<string | null>(null)
const workspaceIdRef = ref<string | null>(null)
const agentRows = ref<Array<{ display_name: string; status: string; error?: string }>>([])
const overallMessage = ref('')
const finalDone = ref(false)

const clusterOptions = computed(() =>
  (clusterStore.clusters || []).map((c) => ({
    value: c.id,
    label: `${c.name} (${c.compute_provider})`,
  })),
)

const filteredClusters = computed(() => {
  const specs = templateDetail.value?.agent_specs
  const first = specs?.[0] as { compute_provider?: string } | undefined
  const cp = first?.compute_provider
  if (!cp) return clusterOptions.value
  return (clusterStore.clusters || [])
    .filter((c) => c.compute_provider === cp)
    .map((c) => ({ value: c.id, label: `${c.name} (${c.compute_provider})` }))
})

const deploySelectedKeys = ref<Set<string>>(new Set())
const deploySelectedCount = computed(() =>
  countAgentKeysInSelection((templateDetail.value?.agent_specs || []) as Record<string, unknown>[], deploySelectedKeys.value)
)

const DONE_STATUSES = new Set(['success', 'failed', 'add_workspace_failed'])
const progressTotal = computed(() => agentRows.value.length)
const progressDone = computed(() => agentRows.value.filter(r => DONE_STATUSES.has(r.status)).length)
const progressPercent = computed(() =>
  progressTotal.value > 0 ? Math.round((progressDone.value / progressTotal.value) * 100) : 0
)

const statusI18nMap: Record<string, string> = {
  pending: 'deployFromTemplate.statusPending',
  deploying: 'deployFromTemplate.statusDeploying',
  gene_install: 'deployFromTemplate.statusGeneInstall',
  add_workspace: 'deployFromTemplate.statusAddWorkspace',
  success: 'deployFromTemplate.statusSuccess',
  failed: 'deployFromTemplate.statusFailed',
  add_workspace_failed: 'deployFromTemplate.statusFailed',
}

function statusLabel(status: string): string {
  const key = statusI18nMap[status]
  return key ? t(key) : status
}

function handleDeployTopoToggle(key: string) {
  const s = new Set(deploySelectedKeys.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  deploySelectedKeys.value = s
}

const selectedSpecIndex = ref<number | null>(null)
const selectedSpec = computed(() =>
  selectedSpecIndex.value !== null ? templateDetail.value?.agent_specs?.[selectedSpecIndex.value] ?? null : null
)

function openSpecDetail(index: number) {
  selectedSpecIndex.value = index
}
function closeSpecDetail() {
  selectedSpecIndex.value = null
}

const specGeneSlugs = _specGeneSlugs
const specLlmProviders = _specLlmProviders
const resourceSummary = _resourceSummary
const specGeneCount = _specGeneCount

const topoNodes = computed(() => {
  const d = templateDetail.value
  if (!d) return []
  return buildTopoNodes({
    agent_specs: (d.agent_specs || []) as Record<string, unknown>[],
    human_specs: (d.human_specs || []) as Record<string, unknown>[],
    topology_snapshot: d.topology_snapshot as { nodes?: Record<string, unknown>[]; edges?: Record<string, unknown>[] } | undefined,
  })
})

const topoEdges = computed(() => {
  const d = templateDetail.value
  if (!d) return []
  return buildTopoEdges({
    agent_specs: [],
    human_specs: [],
    topology_snapshot: d.topology_snapshot as { nodes?: Record<string, unknown>[]; edges?: Record<string, unknown>[] } | undefined,
  })
})

const deployAgents = computed(() =>
  buildMockAgents((templateDetail.value?.agent_specs || []) as Record<string, unknown>[])
)

function close() {
  emit('update:open', false)
}

function reset() {
  templateDetail.value = null
  workspaceName.value = ''
  clusterId.value = null
  phase.value = 'form'
  deployId.value = null
  workspaceIdRef.value = null
  agentRows.value = []
  overallMessage.value = ''
  finalDone.value = false
  submitting.value = false
  selectedSpecIndex.value = null
  deploySelectedKeys.value = new Set()
}

watch(
  () => props.open,
  async (v) => {
    if (!v) {
      abortSse()
      reset()
      return
    }
    await clusterStore.fetchClusters()
    if (props.resumeDeployId) {
      phase.value = 'progress'
      deployId.value = props.resumeDeployId
      await loadDeployState(props.resumeDeployId)
      startSse(props.resumeDeployId)
      return
    }
    if (props.templateId) {
      loadingDetail.value = true
      try {
        templateDetail.value = await store.fetchWorkspaceTemplateDetail(props.templateId)
        workspaceName.value = templateDetail.value.name || ''
        const specs = templateDetail.value.agent_specs || []
        agentRows.value = specs.map((s) => ({
          display_name: (s.display_name as string) || '',
          status: 'pending',
        }))
        const topo = templateDetail.value.topology_snapshot as { nodes?: Record<string, unknown>[] } | undefined
        deploySelectedKeys.value = allSelectableKeys(specs as Record<string, unknown>[], topo)
        const opts = filteredClusters.value.length ? filteredClusters.value : clusterOptions.value
        clusterId.value = opts[0]?.value ?? null
      } catch (e) {
        toast.error(resolveApiErrorMessage(e, t('deployFromTemplate.loadFailed')))
        close()
      } finally {
        loadingDetail.value = false
      }
    }
  },
)

async function loadDeployState(id: string) {
  try {
    const d = await store.fetchWorkspaceDeploy(id)
    workspaceIdRef.value = (d as { workspace_id?: string }).workspace_id ?? null
    const pd = (d as { progress_detail?: { agents?: Array<{ display_name: string; status: string; error?: string }> } }).progress_detail
    if (pd?.agents?.length) {
      agentRows.value = pd.agents.map((a) => ({
        display_name: a.display_name,
        status: a.status || 'pending',
        error: a.error,
      }))
    }
    const st = (d as { status?: string }).status
    if (st === 'success' || st === 'partial_success' || st === 'failed') {
      finalDone.value = true
    }
  } catch {
    /* ignore */
  }
}

let abortCtrl: AbortController | null = null
function abortSse() {
  abortCtrl?.abort()
  abortCtrl = null
}

function startSse(id: string) {
  abortSse()
  const token = localStorage.getItem('portal_token')
  abortCtrl = new AbortController()
  fetchEventSource(`/api/v1/workspaces/deploys/${id}/progress`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal: abortCtrl.signal,
    openWhenHidden: true,
    onmessage(ev) {
      if (ev.event !== 'workspace_deploy_progress') return
      try {
        const data = JSON.parse(ev.data)
        if (data.event === 'phase') {
          overallMessage.value = data.message || data.phase || ''
        }
        if (data.event === 'agent_progress') {
          const idx = data.index
          if (typeof idx === 'number' && agentRows.value[idx]) {
            agentRows.value[idx] = {
              ...agentRows.value[idx],
              status: data.status || agentRows.value[idx].status,
              error: data.error,
            }
          }
        }
        if (data.event === 'complete') {
          for (let j = 0; j < agentRows.value.length; j++) {
            if (!DONE_STATUSES.has(agentRows.value[j].status)) {
              agentRows.value[j] = { ...agentRows.value[j], status: 'success' }
            }
          }
          finalDone.value = true
          abortSse()
        }
      } catch {
        /* ignore */
      }
    },
    onerror() {
      /* library retries */
    },
  }).catch(() => {})
}

async function startDeploy() {
  if (!props.templateId || !workspaceName.value.trim() || !clusterId.value || deploySelectedCount.value === 0) return
  submitting.value = true
  try {
    const specs = (templateDetail.value?.agent_specs || []) as Record<string, unknown>[]
    const indices = keysToSelectedIndices(specs, deploySelectedKeys.value)
    const topo = templateDetail.value?.topology_snapshot as { nodes?: Record<string, unknown>[] } | undefined
    const excludedCorridors = keysToExcludedCorridorCoords(topo, deploySelectedKeys.value)
    const out = await store.deployWorkspaceFromTemplate(
      props.templateId,
      workspaceName.value.trim(),
      clusterId.value,
      indices,
      excludedCorridors.length > 0 ? excludedCorridors : undefined,
    )
    deployId.value = out.workspace_deploy_id
    workspaceIdRef.value = out.workspace_id
    const selectedSet = new Set(indices)
    agentRows.value = agentRows.value.filter((_, i) => selectedSet.has(i))
    phase.value = 'progress'
    startSse(out.workspace_deploy_id)
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('deployFromTemplate.startFailed')))
  } finally {
    submitting.value = false
  }
}

function enterWorkspace() {
  const wid = workspaceIdRef.value
  if (wid) emit('done', wid)
  close()
}

watch(
  () => props.resumeDeployId,
  (id) => {
    if (props.open && id) {
      deployId.value = id
      phase.value = 'progress'
    }
  },
)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="open"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        @click.self="close"
      >
        <div class="bg-card rounded-xl shadow-2xl w-full max-w-md border border-border max-h-[90vh] flex flex-col">
          <div class="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
            <h3 class="text-sm font-semibold">{{ t('deployFromTemplate.title') }}</h3>
            <button type="button" class="p-1 rounded hover:bg-muted" @click="close">
              <X class="w-4 h-4" />
            </button>
          </div>

          <div v-if="loadingDetail" class="flex justify-center py-12">
            <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
          </div>

          <div v-else-if="phase === 'form' && templateDetail" class="px-5 py-4 space-y-4 overflow-y-auto">
            <div class="space-y-1">
              <label class="text-xs font-medium text-muted-foreground">{{ t('deployFromTemplate.workspaceName') }}</label>
              <input
                v-model="workspaceName"
                class="w-full px-3 py-2 text-sm rounded-lg bg-muted border border-border outline-none focus:ring-1 focus:ring-primary/50"
                maxlength="128"
              />
            </div>
            <div class="space-y-1">
              <label class="text-xs font-medium text-muted-foreground">{{ t('deployFromTemplate.cluster') }}</label>
              <CustomSelect
                :model-value="clusterId"
                :options="filteredClusters.length ? filteredClusters : clusterOptions"
                :placeholder="t('deployFromTemplate.selectCluster')"
                trigger-class="w-full"
                @update:model-value="(v: string | null) => (clusterId = v)"
              />
            </div>
            <div class="rounded-lg border border-border p-3 space-y-2">
              <p class="text-xs font-medium text-muted-foreground">{{ t('deployFromTemplate.teamSummary') }}</p>
              <ul class="text-xs space-y-1 max-h-40 overflow-y-auto">
                <li
                  v-for="(row, i) in agentRows"
                  :key="i"
                  class="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors cursor-pointer"
                  @click="openSpecDetail(i)"
                >
                  <div class="flex-1 min-w-0">
                    <span class="font-medium text-foreground">{{ row.display_name }}</span>
                    <span class="text-muted-foreground ml-2">
                      {{ t('deployFromTemplate.geneCount', { n: specGeneCount((templateDetail?.agent_specs?.[i] || {}) as Record<string, unknown>) }) }}
                      <template v-if="resourceSummary((templateDetail?.agent_specs?.[i] || {}) as Record<string, unknown>)">
                        · {{ resourceSummary((templateDetail?.agent_specs?.[i] || {}) as Record<string, unknown>) }}
                      </template>
                    </span>
                  </div>
                  <ChevronRight class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                </li>
                <li v-for="(h, hi) in templateDetail.human_specs || []" :key="'h' + hi" class="px-2 py-1.5 text-muted-foreground">
                  {{ (h as { display_name?: string }).display_name }} ({{ t('deployFromTemplate.humanPlaceholder') }})
                </li>
              </ul>
            </div>

            <div v-if="topoNodes.length" class="rounded-lg border border-border overflow-hidden">
              <p class="text-xs font-medium text-muted-foreground px-3 pt-2.5 pb-1">{{ t('workspaceSettings.topoSelectHint') }}</p>
              <div class="h-[280px] bg-[#0a0a1a]">
                <Workspace2D
                  :agents="deployAgents"
                  blackboard-content=""
                  :selected-agent-id="null"
                  :selected-hex="null"
                  :topology-nodes="topoNodes"
                  :topology-edges="topoEdges"
                  :selectable="true"
                  :selected-keys="deploySelectedKeys"
                  :selectable-types="['agent', 'corridor']"
                  @toggle-node="handleDeployTopoToggle"
                />
              </div>
            </div>

            <div class="flex justify-end gap-2 pt-2">
              <button type="button" class="px-4 py-2 text-sm rounded-lg hover:bg-muted" @click="close">
                {{ t('deployFromTemplate.cancel') }}
              </button>
              <button
                type="button"
                class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground disabled:opacity-50"
                :disabled="submitting || !workspaceName.trim() || !clusterId || deploySelectedCount === 0"
                @click="startDeploy"
              >
                <Loader2 v-if="submitting" class="w-4 h-4 animate-spin inline mr-1" />
                {{ t('deployFromTemplate.startWithCount', { n: deploySelectedCount }) }}
              </button>
            </div>
          </div>

          <div v-else-if="phase === 'progress'" class="px-5 py-4 space-y-4 overflow-y-auto flex-1">
            <div class="space-y-2">
              <div class="flex items-center justify-between text-xs">
                <span class="font-medium">
                  {{ finalDone ? t('deployFromTemplate.progressDone') : t('deployFromTemplate.progressTitle', { done: progressDone, total: progressTotal }) }}
                </span>
                <span class="text-muted-foreground">{{ finalDone ? 100 : progressPercent }}%</span>
              </div>
              <div class="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500 ease-out"
                  :class="finalDone ? 'bg-green-500' : 'bg-primary'"
                  :style="{ width: `${finalDone ? 100 : Math.max(progressPercent, progressTotal > 0 ? 5 : 0)}%` }"
                />
              </div>
            </div>

            <ul class="space-y-1.5 text-xs">
              <li v-for="(row, i) in agentRows" :key="i" class="flex items-center gap-2.5 px-2 py-2 rounded-lg bg-muted/50">
                <CheckCircle2 v-if="row.status === 'success'" class="w-4 h-4 text-green-500 shrink-0" />
                <XCircle v-else-if="row.status === 'failed' || row.status === 'add_workspace_failed'" class="w-4 h-4 text-red-400 shrink-0" />
                <Loader2 v-else-if="row.status !== 'pending'" class="w-4 h-4 text-primary animate-spin shrink-0" />
                <Circle v-else class="w-4 h-4 text-muted-foreground shrink-0" />
                <div class="flex-1 min-w-0">
                  <span class="font-medium text-foreground">{{ row.display_name }}</span>
                </div>
                <span
                  class="text-[11px] shrink-0"
                  :class="row.status === 'success' ? 'text-green-500' : row.status === 'failed' || row.status === 'add_workspace_failed' ? 'text-red-400' : 'text-muted-foreground'"
                >{{ statusLabel(row.status) }}</span>
              </li>
            </ul>
            <p v-if="agentRows.some(r => r.error)" class="text-xs text-red-400 px-1">
              {{ agentRows.find(r => r.error)?.error }}
            </p>

            <button
              v-if="finalDone && workspaceIdRef"
              type="button"
              class="w-full px-4 py-2.5 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors"
              @click="enterWorkspace"
            >
              {{ t('deployFromTemplate.enterWorkspace') }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- Agent Spec Detail Sub-dialog -->
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="selectedSpec" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" @click.self="closeSpecDetail">
        <div class="bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
            <h3 class="text-sm font-semibold">{{ (selectedSpec.display_name as string) || '—' }}</h3>
            <button type="button" class="p-1 rounded hover:bg-muted" @click="closeSpecDetail">
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="px-5 py-4 space-y-4 overflow-y-auto text-xs">
            <div class="space-y-1.5">
              <p class="font-medium text-muted-foreground">{{ t('deployFromTemplate.geneList') }}</p>
              <ul v-if="specGeneSlugs(selectedSpec).length" class="space-y-0.5 text-foreground">
                <li v-for="slug in specGeneSlugs(selectedSpec)" :key="slug" class="flex items-center gap-1.5">
                  <span class="w-1 h-1 rounded-full bg-primary shrink-0" />
                  {{ slug }}
                </li>
              </ul>
              <p v-else class="text-muted-foreground">{{ t('deployFromTemplate.none') }}</p>
            </div>

            <div class="space-y-1.5">
              <p class="font-medium text-muted-foreground">{{ t('deployFromTemplate.llmConfig') }}</p>
              <div v-if="specLlmProviders(selectedSpec).length" class="space-y-1">
                <div v-for="p in specLlmProviders(selectedSpec)" :key="p.provider" class="text-foreground">
                  <span class="font-medium">{{ p.provider }}</span>
                  <span v-if="p.models.length" class="text-muted-foreground ml-1.5">{{ p.models.join(', ') }}</span>
                </div>
              </div>
              <p v-else class="text-muted-foreground">{{ t('deployFromTemplate.none') }}</p>
            </div>

            <div class="space-y-1.5">
              <p class="font-medium text-muted-foreground">{{ t('deployFromTemplate.resourceConfig') }}</p>
              <div class="grid grid-cols-3 gap-x-4 gap-y-1 text-foreground">
                <span>CPU: {{ (selectedSpec.resources as Record<string, string>)?.cpu_limit || '—' }}</span>
                <span>Mem: {{ (selectedSpec.resources as Record<string, string>)?.mem_limit || '—' }}</span>
                <span>{{ t('deployFromTemplate.storage') }}: {{ (selectedSpec.resources as Record<string, string>)?.storage_size || '—' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
