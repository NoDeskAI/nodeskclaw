<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, Loader2, ChevronRight, CheckCircle2, XCircle, Circle, ArrowLeft, AlertTriangle } from 'lucide-vue-next'
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { useWorkspaceStore, type WorkspaceTemplateDetail } from '@/stores/workspace'
import { useClusterStore } from '@/stores/cluster'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useToast } from '@/composables/useToast'
import CustomSelect from '@/components/shared/CustomSelect.vue'
import Workspace2D from '@/components/hex2d/Workspace2D.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
  agentSelectableKey,
} from '@/utils/templateTopology'
import {
  agentIndicesWithIssues,
  initialAgentPositions,
  positionsPayload,
  selectedLayoutAgents,
  type TemplateLayoutCheckResult,
} from '@/utils/templateDeployLayout'

const props = defineProps<{
  open: boolean
  templateId?: string | null
  resumeDeployId?: string | null
}>()

const emit = defineEmits<{
  'update:open': [v: boolean]
  done: [workspaceId: string]
  loadError: []
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
const phase = ref<'form' | 'layout' | 'progress'>('form')
const deployId = ref<string | null>(null)
const workspaceIdRef = ref<string | null>(null)
const agentRows = ref<Array<{ display_name: string; status: string; error?: string }>>([])
const overallMessage = ref('')
const finalStatus = ref<'success' | 'partial_success' | 'failed' | null>(null)
const finalDone = computed(() => finalStatus.value !== null)

const clusterOptions = computed(() =>
  (clusterStore.clusters || []).map((c) => ({
    value: c.id,
    label: c.name,
  })),
)

const filteredClusters = computed(() => {
  const specs = templateDetail.value?.agent_specs
  const first = specs?.[0] as { compute_provider?: string } | undefined
  const cp = first?.compute_provider
  if (!cp) return clusterOptions.value
  return (clusterStore.clusters || [])
    .filter((c) => c.compute_provider === cp)
    .map((c) => ({ value: c.id, label: c.name }))
})

const deploySelectedKeys = ref<Set<string>>(new Set())
const deploySelectedCount = computed(() =>
  countAgentKeysInSelection((templateDetail.value?.agent_specs || []) as Record<string, unknown>[], deploySelectedKeys.value)
)
const layoutPositions = ref<Map<number, { q: number; r: number }>>(new Map())
const selectedLayoutAgentIndex = ref<number | null>(null)
const layoutCheck = ref<TemplateLayoutCheckResult | null>(null)
const layoutChecking = ref(false)
const selectedAgentIndices = computed(() => {
  const specs = (templateDetail.value?.agent_specs || []) as Record<string, unknown>[]
  return keysToSelectedIndices(specs, deploySelectedKeys.value)
})
const selectedAgentIndexSet = computed(() => new Set(selectedAgentIndices.value))
const excludedCorridorCoords = computed(() => {
  const topo = templateDetail.value?.topology_snapshot as { nodes?: Record<string, unknown>[] } | undefined
  return keysToExcludedCorridorCoords(topo, deploySelectedKeys.value)
})
const layoutPositionPayload = computed(() => positionsPayload(selectedAgentIndices.value, layoutPositions.value))
const layoutInvalidAgentIndices = computed(() =>
  layoutCheck.value ? agentIndicesWithIssues(layoutCheck.value.issues) : new Set<number>()
)
const layoutInvalidKeys = computed(() =>
  new Set([...layoutInvalidAgentIndices.value].map(index => agentSelectableKey(index)))
)
const layoutSelectedKeys = computed(() => {
  const keys = new Set<string>()
  for (const index of selectedAgentIndices.value) keys.add(agentSelectableKey(index))
  for (const key of deploySelectedKeys.value) {
    if (!key.startsWith('agent:')) keys.add(key)
  }
  return keys
})
const layoutAgents = computed(() =>
  selectedLayoutAgents(
    (templateDetail.value?.agent_specs || []) as Record<string, unknown>[],
    selectedAgentIndices.value,
    layoutPositions.value,
  )
)
const canStartDeploy = computed(() =>
  !!workspaceName.value.trim()
  && !!clusterId.value
  && selectedAgentIndices.value.length > 0
  && layoutCheck.value?.can_deploy === true
  && layoutPositionPayload.value.length === selectedAgentIndices.value.length
)

const DONE_STATUSES = new Set(['success', 'failed', 'add_workspace_failed'])
const progressTotal = computed(() => agentRows.value.length)
const progressDone = computed(() => agentRows.value.filter(r => DONE_STATUSES.has(r.status)).length)
const progressPercent = computed(() =>
  progressTotal.value > 0 ? Math.round((progressDone.value / progressTotal.value) * 100) : 0
)

const progressBarClass = computed(() => {
  switch (finalStatus.value) {
    case 'success': return 'bg-green-500'
    case 'partial_success': return 'bg-amber-500'
    case 'failed': return 'bg-red-500'
    default: return 'bg-primary'
  }
})

const progressLabel = computed(() => {
  switch (finalStatus.value) {
    case 'success': return t('deployFromTemplate.progressDone')
    case 'partial_success': return t('deployFromTemplate.progressPartial')
    case 'failed': return t('deployFromTemplate.progressFailed')
    default: return t('deployFromTemplate.progressTitle', { done: progressDone.value, total: progressTotal.value })
  }
})

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

const layoutTopoNodes = computed(() =>
  topoNodes.value.filter((node) => node.node_type !== 'agent' && (
    node.node_type !== 'corridor' || deploySelectedKeys.value.has(`${node.hex_q},${node.hex_r}`)
  ))
)

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
  finalStatus.value = null
  submitting.value = false
  selectedSpecIndex.value = null
  deploySelectedKeys.value = new Set()
  layoutPositions.value = new Map()
  selectedLayoutAgentIndex.value = null
  layoutCheck.value = null
  layoutChecking.value = false
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
      const ok = await loadDeployState(props.resumeDeployId)
      if (!ok) return
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
        layoutPositions.value = initialAgentPositions(specs as Record<string, unknown>[])
        selectedLayoutAgentIndex.value = specs.length > 0 ? 0 : null
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

async function loadDeployState(id: string): Promise<boolean> {
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
      finalStatus.value = st
    }
    return true
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('deployFromTemplate.resumeFailed')))
    emit('loadError')
    close()
    return false
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
          const st = data.status || 'success'
          if (st === 'success') {
            for (let j = 0; j < agentRows.value.length; j++) {
              if (!DONE_STATUSES.has(agentRows.value[j].status)) {
                agentRows.value[j] = { ...agentRows.value[j], status: 'success' }
              }
            }
          } else if (st === 'failed') {
            for (let j = 0; j < agentRows.value.length; j++) {
              if (!DONE_STATUSES.has(agentRows.value[j].status)) {
                agentRows.value[j] = { ...agentRows.value[j], status: 'failed', error: data.error }
              }
            }
          }
          if (data.error) overallMessage.value = data.error
          finalStatus.value = st
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

async function runLayoutCheck() {
  if (!props.templateId) return
  layoutChecking.value = true
  try {
    layoutCheck.value = await store.checkWorkspaceTemplateDeployLayout(
      props.templateId,
      selectedAgentIndices.value,
      excludedCorridorCoords.value.length > 0 ? excludedCorridorCoords.value : undefined,
      layoutPositionPayload.value,
    )
  } catch (e) {
    layoutCheck.value = null
    toast.error(resolveApiErrorMessage(e, t('deployFromTemplate.layoutCheckFailed')))
  } finally {
    layoutChecking.value = false
  }
}

async function enterLayoutConfirm() {
  if (!props.templateId || !workspaceName.value.trim() || !clusterId.value || deploySelectedCount.value === 0) return
  if (!selectedAgentIndexSet.value.has(selectedLayoutAgentIndex.value ?? -1)) {
    selectedLayoutAgentIndex.value = selectedAgentIndices.value[0] ?? null
  }
  await runLayoutCheck()
  phase.value = 'layout'
}

function handleLayoutAgentClick(key: string) {
  if (!key.startsWith('agent:')) return
  const index = Number(key.slice('agent:'.length))
  if (Number.isInteger(index) && selectedAgentIndexSet.value.has(index)) {
    selectedLayoutAgentIndex.value = index
  }
}

async function handleLayoutHexClick(payload: { q: number; r: number; type: string }) {
  if (payload.type !== 'empty' || selectedLayoutAgentIndex.value === null) return
  const next = new Map(layoutPositions.value)
  next.set(selectedLayoutAgentIndex.value, { q: payload.q, r: payload.r })
  layoutPositions.value = next
  await runLayoutCheck()
}

function issueTextForAgent(index: number): string {
  const issue = layoutCheck.value?.issues.find(item => item.agent_index === index)
  return issue?.message || ''
}

async function startDeploy() {
  if (!props.templateId || !canStartDeploy.value) return
  submitting.value = true
  try {
    await runLayoutCheck()
    if (!canStartDeploy.value) return
    const indices = selectedAgentIndices.value
    const out = await store.deployWorkspaceFromTemplate(
      props.templateId,
      workspaceName.value.trim(),
      clusterId.value,
      indices,
      excludedCorridorCoords.value.length > 0 ? excludedCorridorCoords.value : undefined,
      layoutPositionPayload.value,
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
        <div
          class="bg-card rounded-xl shadow-2xl w-full border border-border max-h-[90vh] flex flex-col"
          :class="phase === 'layout' ? 'max-w-5xl' : 'max-w-md'"
        >
          <div class="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
            <h3 class="text-sm font-semibold">{{ t('deployFromTemplate.title') }}</h3>
            <Button variant="unstyled" size="unstyled" type="button" class="p-1 rounded hover:bg-muted" @click="close">
              <X class="w-4 h-4" />
            </Button>
          </div>

          <div v-if="loadingDetail" class="flex justify-center py-12">
            <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
          </div>

          <div v-else-if="phase === 'form' && templateDetail" class="px-5 py-4 space-y-4 overflow-y-auto">
            <div class="space-y-1">
              <label class="text-xs font-medium text-muted-foreground">{{ t('deployFromTemplate.workspaceName') }}</label>
              <Input
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
                  selectable-key-mode="agent-id"
                  :selected-keys="deploySelectedKeys"
                  :selectable-types="['agent', 'corridor']"
                  @toggle-node="handleDeployTopoToggle"
                />
              </div>
            </div>

            <div class="flex justify-end gap-2 pt-2">
              <Button variant="unstyled" size="unstyled" type="button" class="px-4 py-2 text-sm rounded-lg hover:bg-muted" @click="close">
                {{ t('deployFromTemplate.cancel') }}
              </Button>
              <Button variant="unstyled" size="unstyled"
                type="button"
                class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground disabled:opacity-50"
                :disabled="submitting || !workspaceName.trim() || !clusterId || deploySelectedCount === 0"
                @click="enterLayoutConfirm"
              >
                <Loader2 v-if="submitting" class="w-4 h-4 animate-spin inline mr-1" />
                {{ t('deployFromTemplate.confirmPositions') }}
              </Button>
            </div>
          </div>

          <div v-else-if="phase === 'layout' && templateDetail" class="px-5 py-4 space-y-4 overflow-y-auto">
            <div class="flex items-center justify-between gap-3">
              <Button variant="unstyled" size="unstyled" type="button" class="inline-flex items-center gap-1.5 px-2 py-1.5 text-xs rounded-lg hover:bg-muted" @click="phase = 'form'">
                <ArrowLeft class="w-3.5 h-3.5" />
                {{ t('deployFromTemplate.backToSelection') }}
              </Button>
              <div class="text-xs text-muted-foreground">
                {{ t('deployFromTemplate.selectedCount', { n: selectedAgentIndices.length }) }}
              </div>
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4 min-h-[480px]">
              <div class="rounded-lg border border-border overflow-hidden bg-[#0a0a1a] min-h-[480px]">
                <Workspace2D
                  :agents="layoutAgents"
                  blackboard-content=""
                  :selected-agent-id="null"
                  :selected-hex="null"
                  :topology-nodes="layoutTopoNodes"
                  :topology-edges="topoEdges"
                  :selectable="true"
                  selectable-key-mode="agent-id"
                  :selected-keys="layoutSelectedKeys"
                  :selectable-types="['agent']"
                  :invalid-keys="layoutInvalidKeys"
                  :active-key="selectedLayoutAgentIndex !== null ? agentSelectableKey(selectedLayoutAgentIndex) : null"
                  :allow-selectable-empty-hex-click="true"
                  @toggle-node="handleLayoutAgentClick"
                  @hex-click="handleLayoutHexClick"
                />
              </div>

              <aside class="space-y-3">
                <div class="rounded-lg border border-border p-3 space-y-2">
                  <p class="text-xs font-medium text-muted-foreground">{{ t('deployFromTemplate.positionList') }}</p>
                  <div class="space-y-1.5 max-h-[300px] overflow-y-auto">
                    <button
                      v-for="index in selectedAgentIndices"
                      :key="index"
                      type="button"
                      class="w-full text-left px-2.5 py-2 rounded-lg border text-xs transition-colors"
                      :class="[
                        selectedLayoutAgentIndex === index ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted/50',
                        layoutInvalidAgentIndices.has(index) ? 'border-red-400/70 bg-red-500/10' : '',
                      ]"
                      @click="selectedLayoutAgentIndex = index"
                    >
                      <div class="flex items-center justify-between gap-2">
                        <span class="font-medium truncate">
                          {{ (templateDetail.agent_specs?.[index]?.display_name as string) || (templateDetail.agent_specs?.[index]?.label as string) || `Agent ${index + 1}` }}
                        </span>
                        <span class="text-muted-foreground shrink-0">
                          <template v-if="layoutPositions.get(index)">
                            ({{ layoutPositions.get(index)?.q }}, {{ layoutPositions.get(index)?.r }})
                          </template>
                          <template v-else>{{ t('deployFromTemplate.notPlaced') }}</template>
                        </span>
                      </div>
                      <p v-if="issueTextForAgent(index)" class="mt-1 text-[11px] text-red-400">
                        {{ issueTextForAgent(index) }}
                      </p>
                    </button>
                  </div>
                </div>

                <div v-if="layoutCheck && !layoutCheck.can_deploy" class="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-300 space-y-1.5">
                  <div class="flex items-center gap-1.5 font-medium">
                    <AlertTriangle class="w-3.5 h-3.5" />
                    {{ t('deployFromTemplate.layoutBlocked') }}
                  </div>
                  <p>{{ t('deployFromTemplate.layoutBlockedHint') }}</p>
                </div>
                <div v-else class="rounded-lg border border-border p-3 text-xs text-muted-foreground">
                  {{ layoutChecking ? t('deployFromTemplate.layoutChecking') : t('deployFromTemplate.layoutReady') }}
                </div>
              </aside>
            </div>

            <div class="flex justify-end gap-2 pt-2">
              <Button variant="unstyled" size="unstyled" type="button" class="px-4 py-2 text-sm rounded-lg hover:bg-muted" @click="close">
                {{ t('deployFromTemplate.cancel') }}
              </Button>
              <Button variant="unstyled" size="unstyled"
                type="button"
                class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground disabled:opacity-50"
                :disabled="submitting || layoutChecking || !canStartDeploy"
                @click="startDeploy"
              >
                <Loader2 v-if="submitting || layoutChecking" class="w-4 h-4 animate-spin inline mr-1" />
                {{ t('deployFromTemplate.startWithCount', { n: deploySelectedCount }) }}
              </Button>
            </div>
          </div>

          <div v-else-if="phase === 'progress'" class="px-5 py-4 space-y-4 overflow-y-auto flex-1">
            <div class="space-y-2">
              <div class="flex items-center justify-between text-xs">
                <span class="font-medium">
                  {{ progressLabel }}
                </span>
                <span class="text-muted-foreground">{{ finalDone ? 100 : progressPercent }}%</span>
              </div>
              <div class="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500 ease-out"
                  :class="progressBarClass"
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
            <p v-if="finalStatus === 'failed' && overallMessage" class="text-xs text-red-400 px-1">
              {{ overallMessage }}
            </p>

            <Button variant="unstyled" size="unstyled"
              v-if="finalStatus && finalStatus !== 'failed' && workspaceIdRef"
              type="button"
              class="w-full px-4 py-2.5 text-sm rounded-lg bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors"
              @click="enterWorkspace"
            >
              {{ t('deployFromTemplate.enterWorkspace') }}
            </Button>
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
            <Button variant="unstyled" size="unstyled" type="button" class="p-1 rounded hover:bg-muted" @click="closeSpecDetail">
              <X class="w-4 h-4" />
            </Button>
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
