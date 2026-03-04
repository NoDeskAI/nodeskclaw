<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ExternalLink, RefreshCw, Trash2, Circle, Loader2,
  Copy, Check, RotateCcw, AlertTriangle, X,
  Package, Zap, FileText,
} from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import type { InstanceSkillItem, InstanceGeneItem, GenomeItem } from '@/stores/gene'

const props = defineProps<{
  visible: boolean
  instanceId: string | null
}>()

const emit = defineEmits<{
  'update:visible': [value: boolean]
  navigate: []
  deleted: []
}>()

const { t } = useI18n()
const toast = useToast()
const router = useRouter()

interface InstanceDetail {
  id: string
  name: string
  status: string
  image_version: string
  ingress_domain: string | null
  namespace: string
  cpu_request: string
  cpu_limit: string
  mem_request: string
  mem_limit: string
  env_vars: Record<string, string> | null
  created_at: string
  my_role: string | null
  workspace_id: string | null
  workspace_name: string | null
  pods: { name: string; status: string; ready: boolean; restart_count: number }[]
}

const ROLE_LEVEL: Record<string, number> = { viewer: 10, user: 20, editor: 30, admin: 40 }

const instance = ref<InstanceDetail | null>(null)
const loading = ref(false)
const error = ref('')
const openclawUrl = ref('')
const urlCopied = ref(false)
const restarting = ref(false)
const showRestartConfirm = ref(false)
const showDeleteConfirm = ref(false)
const deleting = ref(false)

const skills = ref<InstanceSkillItem[]>([])
const instanceGenes = ref<InstanceGeneItem[]>([])
const appliedGenomes = ref<GenomeItem[]>([])
const genesLoading = ref(false)

const geneStatusClass: Record<string, string> = {
  installed: 'bg-green-500/10 text-green-500',
  learning: 'bg-yellow-500/10 text-yellow-500',
  learn_failed: 'bg-red-500/10 text-red-500',
  failed: 'bg-red-500/10 text-red-500',
  installing: 'bg-blue-500/10 text-blue-500',
  uninstalling: 'bg-gray-500/10 text-gray-500',
  forgetting: 'bg-amber-500/10 text-amber-500',
  forget_failed: 'bg-red-500/10 text-red-500',
  simplified: 'bg-blue-500/10 text-blue-500',
}

function getStatusClass(status: string): string {
  return geneStatusClass[status] ?? 'bg-gray-500/10 text-gray-500'
}

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    installed: t('instanceGenes.statusInstalled'),
    learning: t('instanceGenes.statusLearning'),
    learn_failed: t('instanceGenes.statusLearnFailed'),
    failed: t('instanceGenes.statusFailed'),
    installing: t('instanceGenes.statusLearning'),
    uninstalling: t('instanceGenes.statusUninstalling'),
    forgetting: t('instanceGenes.statusForgetting'),
    forget_failed: t('instanceGenes.statusForgetFailed'),
    simplified: t('instanceGenes.statusSimplified'),
  }
  return labels[status] ?? status
}

function effectivenessScore(item: InstanceSkillItem): number {
  if (item.instance_gene?.agent_self_eval != null) return item.instance_gene.agent_self_eval
  return item.gene?.effectiveness_score ?? 0
}

function genesPageHref(): string {
  if (!props.instanceId) return ''
  return router.resolve(`/instances/${props.instanceId}/genes`).href
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollTimeout: ReturnType<typeof setTimeout> | null = null

const statusColors: Record<string, string> = {
  running: 'text-green-400',
  learning: 'text-blue-400',
  deploying: 'text-yellow-400',
  restarting: 'text-amber-400',
  failed: 'text-red-400',
}

function close() {
  emit('update:visible', false)
}

async function fetchDetail() {
  if (!props.instanceId) return
  loading.value = true
  error.value = ''
  try {
    const res = await api.get(`/instances/${props.instanceId}`)
    instance.value = res.data.data
    if (instance.value?.ingress_domain && instance.value.env_vars) {
      const token = instance.value.env_vars.OPENCLAW_GATEWAY_TOKEN
      if (token) {
        openclawUrl.value = `https://${instance.value.ingress_domain}?token=${token}`
      } else {
        openclawUrl.value = ''
      }
    } else {
      openclawUrl.value = ''
    }
    if (instance.value?.status === 'restarting') {
      restarting.value = true
      startPolling()
    }
  } catch {
    error.value = t('agentDetailDialog.loadFailed')
  } finally {
    loading.value = false
  }
  fetchGenes()
}

async function fetchGenes() {
  if (!props.instanceId) return
  genesLoading.value = true
  try {
    const [skillsRes, genesRes] = await Promise.all([
      api.get(`/instances/${props.instanceId}/skills`),
      api.get(`/instances/${props.instanceId}/genes`),
    ])
    skills.value = skillsRes.data.data || []
    instanceGenes.value = genesRes.data.data || []

    const genomeIds = [...new Set(
      instanceGenes.value
        .map((g: InstanceGeneItem) => g.genome_id)
        .filter((id): id is string => !!id),
    )]
    if (genomeIds.length > 0) {
      const genomeResults = await Promise.all(
        genomeIds.map(id => api.get(`/genomes/${id}`).catch(() => null)),
      )
      appliedGenomes.value = genomeResults
        .filter(r => r?.data?.data)
        .map(r => r!.data.data)
    } else {
      appliedGenomes.value = []
    }
  } catch {
    skills.value = []
    instanceGenes.value = []
    appliedGenomes.value = []
  } finally {
    genesLoading.value = false
  }
}

async function copyUrl() {
  try {
    await navigator.clipboard.writeText(openclawUrl.value)
    urlCopied.value = true
    setTimeout(() => { urlCopied.value = false }, 2000)
  } catch { /* ignore */ }
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (pollTimeout) { clearTimeout(pollTimeout); pollTimeout = null }
}

async function pollOnce() {
  if (!props.instanceId) return
  try {
    const res = await api.get(`/instances/${props.instanceId}`)
    instance.value = res.data.data
    if (instance.value && instance.value.status !== 'restarting') {
      stopPolling()
      restarting.value = false
      toast.success(t('agentDetailDialog.restartDone'))
    }
  } catch { /* ignore */ }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollOnce, 3000)
  pollTimeout = setTimeout(() => {
    stopPolling()
    restarting.value = false
    toast.error(t('agentDetailDialog.restartTimeout'))
  }, 120_000)
}

async function handleRestart() {
  showRestartConfirm.value = false
  restarting.value = true
  try {
    await api.post(`/instances/${props.instanceId}/restart`)
    toast.success(t('agentDetailDialog.restart'))
    startPolling()
  } catch (e: any) {
    restarting.value = false
    toast.error(e?.response?.data?.message || t('agentDetailDialog.restartFailed'))
  }
}

async function handleDelete() {
  showDeleteConfirm.value = false
  deleting.value = true
  try {
    await api.delete(`/instances/${props.instanceId}`)
    toast.success(t('agentDetailDialog.deleted'))
    emit('deleted')
    close()
  } catch (e: any) {
    deleting.value = false
    toast.error(e?.response?.data?.message || t('agentDetailDialog.deleteFailed'))
  }
}

function openFullPage() {
  emit('navigate')
  close()
}

watch(() => props.visible, (val) => {
  if (val && props.instanceId) {
    instance.value = null
    openclawUrl.value = ''
    restarting.value = false
    deleting.value = false
    showRestartConfirm.value = false
    showDeleteConfirm.value = false
    skills.value = []
    instanceGenes.value = []
    appliedGenomes.value = []
    fetchDetail()
  } else {
    stopPolling()
  }
})

onUnmounted(stopPolling)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="close" />
        <div class="relative bg-card border border-border rounded-xl w-full max-w-lg shadow-lg max-h-[80vh] flex flex-col">
          <!-- Header -->
          <div class="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
            <div class="flex items-center gap-2 min-w-0">
              <template v-if="instance">
                <h3 class="font-semibold text-base truncate">{{ instance.name }}</h3>
                <span class="flex items-center gap-1 text-xs" :class="statusColors[instance.status] || 'text-zinc-400'">
                  <Circle class="w-2 h-2 fill-current" />
                  {{ instance.status }}
                </span>
              </template>
              <template v-else-if="loading">
                <Loader2 class="w-4 h-4 animate-spin text-muted-foreground" />
              </template>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <button
                v-if="instance"
                class="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                @click="openFullPage"
              >
                <ExternalLink class="w-3.5 h-3.5" />
                {{ t('agentDetailDialog.openInNewPage') }}
              </button>
              <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="close">
                <X class="w-4 h-4 text-muted-foreground" />
              </button>
            </div>
          </div>

          <!-- Body -->
          <div class="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            <!-- Loading -->
            <div v-if="loading" class="flex items-center justify-center py-12">
              <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
            </div>

            <!-- Error -->
            <div v-else-if="error" class="text-center py-12">
              <p class="text-sm text-red-400">{{ error }}</p>
              <button
                class="mt-3 px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="fetchDetail"
              >{{ t('agentDetailDialog.refresh') }}</button>
            </div>

            <template v-else-if="instance">
              <!-- OpenClaw URL -->
              <div v-if="openclawUrl" class="p-3 rounded-lg border border-primary/30 bg-primary/5 space-y-2">
                <div class="flex items-center justify-between">
                  <div>
                    <p class="text-sm font-medium">{{ t('agentDetailDialog.openclawAccess') }}</p>
                    <p class="text-xs text-muted-foreground mt-0.5">
                      {{ restarting ? t('agentDetailDialog.restarting') : t('agentDetailDialog.openclawHint') }}
                    </p>
                  </div>
                  <button
                    v-if="restarting"
                    disabled
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs cursor-not-allowed"
                  >
                    <Loader2 class="w-3.5 h-3.5 animate-spin" />
                    {{ t('agentDetailDialog.restarting') }}
                  </button>
                  <a
                    v-else
                    :href="openclawUrl"
                    target="_blank"
                    class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
                  >
                    <ExternalLink class="w-3.5 h-3.5" />
                    {{ t('agentDetailDialog.open') }}
                  </a>
                </div>
                <div class="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-background/60 border border-border/50">
                  <a
                    :href="openclawUrl"
                    target="_blank"
                    class="flex-1 text-xs font-mono truncate transition-colors"
                    :class="restarting ? 'text-muted-foreground pointer-events-none' : 'text-primary/80 hover:text-primary'"
                  >{{ openclawUrl }}</a>
                  <button
                    class="shrink-0 p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                    @click="copyUrl"
                  >
                    <Check v-if="urlCopied" class="w-3 h-3 text-green-400" />
                    <Copy v-else class="w-3 h-3" />
                  </button>
                </div>
              </div>

              <!-- Basic Info -->
              <div class="p-3 rounded-lg border border-border bg-card">
                <h4 class="text-xs font-medium text-muted-foreground mb-2">{{ t('agentDetailDialog.basicInfo') }}</h4>
                <div class="grid grid-cols-2 gap-3 text-sm">
                  <div>
                    <span class="text-muted-foreground text-xs">{{ t('agentDetailDialog.imageVersion') }}</span>
                    <span class="ml-1.5 font-mono text-xs bg-muted px-1.5 py-0.5 rounded">{{ instance.image_version }}</span>
                  </div>
                  <div>
                    <span class="text-muted-foreground text-xs">{{ t('agentDetailDialog.createdAt') }}</span>
                    <span class="ml-1.5 text-xs">{{ new Date(instance.created_at).toLocaleDateString('zh-CN') }}</span>
                  </div>
                </div>
              </div>

              <!-- Pod Status -->
              <div v-if="instance.pods?.length" class="p-3 rounded-lg border border-border bg-card">
                <h4 class="text-xs font-medium text-muted-foreground mb-2">{{ t('agentDetailDialog.podStatus') }}</h4>
                <div class="space-y-1.5">
                  <div
                    v-for="pod in instance.pods"
                    :key="pod.name"
                    class="flex items-center justify-between text-xs p-2 rounded-md bg-muted/30"
                  >
                    <div class="flex items-center gap-2">
                      <Circle
                        class="w-2 h-2 fill-current"
                        :class="pod.ready ? 'text-green-400' : 'text-yellow-400'"
                      />
                      <span class="font-mono">{{ pod.name }}</span>
                    </div>
                    <span class="text-muted-foreground">
                      {{ t('agentDetailDialog.restartCount', { count: pod.restart_count }) }}
                    </span>
                  </div>
                </div>
              </div>
              <div v-else-if="restarting" class="p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                <div class="flex items-center gap-2 text-xs text-amber-400">
                  <Loader2 class="w-3.5 h-3.5 animate-spin" />
                  {{ t('agentDetailDialog.restarting') }}
                </div>
              </div>

              <!-- Installed Genes -->
              <div class="p-3 rounded-lg border border-border bg-card">
                <div class="flex items-center justify-between mb-2">
                  <h4 class="text-xs font-medium text-muted-foreground">{{ t('agentDetailDialog.installedGenes') }}</h4>
                  <a
                    v-if="skills.length"
                    :href="genesPageHref()"
                    target="_blank"
                    class="text-xs text-primary hover:text-primary/80 transition-colors"
                  >{{ t('agentDetailDialog.viewAll') }}</a>
                </div>
                <div v-if="genesLoading" class="flex items-center justify-center py-4">
                  <Loader2 class="w-4 h-4 animate-spin text-muted-foreground" />
                </div>
                <div v-else-if="skills.length === 0" class="py-4 text-center">
                  <Package class="w-6 h-6 mx-auto mb-1.5 text-muted-foreground/50" />
                  <p class="text-xs text-muted-foreground">{{ t('agentDetailDialog.noGenes') }}</p>
                </div>
                <div v-else class="space-y-1.5">
                  <div
                    v-for="item in skills"
                    :key="item.skill_name"
                    class="p-2 rounded-md bg-muted/30"
                  >
                    <div v-if="item.type === 'hub'" class="space-y-1.5">
                      <div class="flex items-center gap-1.5 flex-wrap">
                        <span class="text-xs font-medium">{{ item.gene?.name ?? item.name }}</span>
                        <span
                          v-if="item.instance_gene"
                          class="px-1.5 py-0.5 rounded text-[10px] font-medium leading-none"
                          :class="getStatusClass(item.instance_gene.status)"
                        >{{ getStatusLabel(item.instance_gene.status) }}</span>
                        <span v-else class="px-1.5 py-0.5 rounded text-[10px] font-medium leading-none bg-green-500/10 text-green-500">
                          {{ t('instanceGenes.statusInstalled') }}
                        </span>
                      </div>
                      <div class="flex items-center gap-2">
                        <div class="flex-1 max-w-[140px]">
                          <div class="h-1 rounded-full bg-muted overflow-hidden">
                            <div
                              class="h-full rounded-full bg-primary transition-all"
                              :style="{ width: `${Math.min(100, effectivenessScore(item) * 100)}%` }"
                            />
                          </div>
                        </div>
                        <span class="text-[10px] text-muted-foreground">{{ Math.round(effectivenessScore(item) * 100) }}%</span>
                      </div>
                    </div>
                    <div v-else class="flex items-center gap-1.5 flex-wrap">
                      <span class="text-xs font-medium">{{ item.name }}</span>
                      <span class="px-1.5 py-0.5 rounded text-[10px] font-medium leading-none bg-violet-500/10 text-violet-500">
                        <Zap class="w-2.5 h-2.5 inline -mt-0.5 mr-0.5" />{{ t('instanceGenes.emerged') }}
                      </span>
                      <span class="text-[10px] text-muted-foreground ml-auto">
                        <FileText class="w-3 h-3 inline -mt-0.5 mr-0.5" />{{ t('instanceGenes.fileCount', { count: item.file_count }) }}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Applied Genomes -->
              <div v-if="appliedGenomes.length" class="p-3 rounded-lg border border-border bg-card">
                <h4 class="text-xs font-medium text-muted-foreground mb-2">{{ t('agentDetailDialog.appliedGenomes') }}</h4>
                <div class="space-y-1.5">
                  <div
                    v-for="genome in appliedGenomes"
                    :key="genome.id"
                    class="flex items-center justify-between p-2 rounded-md bg-muted/30"
                  >
                    <span class="text-xs font-medium">{{ genome.name }}</span>
                    <span class="text-[10px] text-muted-foreground">
                      {{ t('agentDetailDialog.geneCount', { count: genome.gene_slugs.length }) }}
                    </span>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <!-- Footer actions -->
          <div v-if="instance" class="flex items-center gap-2 px-5 py-3 border-t border-border shrink-0">
            <button
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-xs hover:bg-muted transition-colors"
              @click="fetchDetail"
            >
              <RefreshCw class="w-3.5 h-3.5" />
              {{ t('agentDetailDialog.refresh') }}
            </button>
            <button
              v-if="(ROLE_LEVEL[instance.my_role ?? ''] ?? 0) >= ROLE_LEVEL.editor"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-amber-500/30 text-amber-400 text-xs hover:bg-amber-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="restarting"
              @click="showRestartConfirm = true"
            >
              <RotateCcw class="w-3.5 h-3.5" :class="restarting ? 'animate-spin' : ''" />
              {{ restarting ? t('agentDetailDialog.restarting') : t('agentDetailDialog.restart') }}
            </button>
            <button
              v-if="(ROLE_LEVEL[instance.my_role ?? ''] ?? 0) >= ROLE_LEVEL.admin && !instance.workspace_id"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-red-500/30 text-red-400 text-xs hover:bg-red-500/10 transition-colors ml-auto disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="deleting"
              @click="showDeleteConfirm = true"
            >
              <Loader2 v-if="deleting" class="w-3.5 h-3.5 animate-spin" />
              <Trash2 v-else class="w-3.5 h-3.5" />
              {{ deleting ? t('agentDetailDialog.deleting') : t('agentDetailDialog.delete') }}
            </button>
          </div>
        </div>

        <!-- Restart confirm -->
        <Transition name="fade">
          <div v-if="showRestartConfirm" class="fixed inset-0 z-10 flex items-center justify-center">
            <div class="absolute inset-0" @click="showRestartConfirm = false" />
            <div class="relative bg-card border border-border rounded-xl p-5 w-full max-w-sm shadow-lg space-y-3">
              <div class="flex items-center gap-3">
                <div class="p-2 rounded-lg bg-amber-500/10">
                  <AlertTriangle class="w-5 h-5 text-amber-400" />
                </div>
                <h3 class="text-sm font-semibold">{{ t('agentDetailDialog.restartConfirmTitle') }}</h3>
              </div>
              <p class="text-xs text-muted-foreground">{{ t('agentDetailDialog.restartConfirmDesc') }}</p>
              <div class="flex justify-end gap-2 pt-1">
                <button
                  class="px-3 py-1.5 rounded-lg border border-border text-xs hover:bg-muted transition-colors"
                  @click="showRestartConfirm = false"
                >{{ t('common.cancel') }}</button>
                <button
                  class="px-3 py-1.5 rounded-lg bg-amber-500 text-white text-xs font-medium hover:bg-amber-600 transition-colors"
                  @click="handleRestart"
                >{{ t('common.confirm') }}</button>
              </div>
            </div>
          </div>
        </Transition>

        <!-- Delete confirm -->
        <Transition name="fade">
          <div v-if="showDeleteConfirm" class="fixed inset-0 z-10 flex items-center justify-center">
            <div class="absolute inset-0" @click="showDeleteConfirm = false" />
            <div class="relative bg-card border border-border rounded-xl p-5 w-full max-w-sm shadow-lg space-y-3">
              <div class="flex items-center gap-3">
                <div class="p-2 rounded-lg bg-red-500/10">
                  <AlertTriangle class="w-5 h-5 text-red-400" />
                </div>
                <h3 class="text-sm font-semibold">{{ t('agentDetailDialog.deleteConfirmTitle') }}</h3>
              </div>
              <p class="text-xs text-muted-foreground">
                {{ t('agentDetailDialog.deleteConfirmDesc', { name: instance?.name ?? '' }) }}
              </p>
              <div class="flex justify-end gap-2 pt-1">
                <button
                  class="px-3 py-1.5 rounded-lg border border-border text-xs hover:bg-muted transition-colors"
                  @click="showDeleteConfirm = false"
                >{{ t('common.cancel') }}</button>
                <button
                  class="px-3 py-1.5 rounded-lg bg-red-500 text-white text-xs font-medium hover:bg-red-600 transition-colors"
                  @click="handleDelete"
                >{{ t('common.confirm') }}</button>
              </div>
            </div>
          </div>
        </Transition>
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
