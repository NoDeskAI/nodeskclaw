<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, inject, type Ref, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  RefreshCw, Trash2, Circle, Loader2, Copy, Check, RotateCcw, AlertTriangle,
  Wrench, Archive, CopyPlus, ChevronDown, ChevronRight, Save,
} from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { getStatusDisplay } from '@/utils/instanceStatus'
import { copyToClipboard } from '@/utils/clipboard'
import { formatDateTime, formatNumber } from '@/utils/localeFormat'
import { buildEngineInfoMap } from '@/utils/instanceFlow'

const router = useRouter()
const toast = useToast()
const { t, locale } = useI18n()

function joinNames(names: string[]): string {
  return names.join(String(locale.value).startsWith('zh') ? '、' : ', ')
}
const { confirm } = useConfirm()
const instanceId = inject<ComputedRef<string>>('instanceId')!
const instanceBasic = inject<Ref<{ name: string } | null>>('instanceBasic')!
const refreshInstanceBasic = inject<() => Promise<void>>('refreshInstanceBasic')!
const myInstanceRole = inject<Ref<string | null>>('myInstanceRole', ref(null))
const ROLE_LEVEL: Record<string, number> = { viewer: 10, user: 20, editor: 30, admin: 40 }
const canEdit = computed(() => (ROLE_LEVEL[myInstanceRole.value ?? ''] ?? 0) >= ROLE_LEVEL.editor)
const canAdmin = computed(() => (ROLE_LEVEL[myInstanceRole.value ?? ''] ?? 0) >= ROLE_LEVEL.admin)

interface InstanceDetail {
  id: string
  name: string
  status: string
  health_status?: string
  display_status?: string
  image_version: string
  ingress_domain: string | null
  namespace: string
  replicas: number
  available_replicas: number
  cpu_request: string
  cpu_limit: string
  mem_request: string
  mem_limit: string
  storage_size: string
  env_vars: Record<string, string> | null
  created_at: string
  workspaces?: { id: string; name: string }[]
  pods: { name: string; status: string; ready: boolean; restart_count: number }[]
  endpoint_url?: string | null
  compute_provider?: string
  runtime?: string
}

const instance = ref<InstanceDetail | null>(null)
const isDocker = computed(() => instance.value?.compute_provider === 'docker')

interface EngineInfo {
  name: string
  description: string
  poweredBy: string
  tags: string[]
}
const ENGINE_INFO: Record<string, EngineInfo> = buildEngineInfoMap(t)
const engineInfo = computed(() => ENGINE_INFO[instance.value?.runtime ?? 'openclaw'] ?? null)
const loading = ref(true)
const pageError = ref('')
const gatewayToken = ref('')
const tokenCopied = ref(false)
const restarting = ref(false)
const resettingToken = ref(false)
const showRestartDialog = ref(false)
const showDeleteDialog = ref(false)
const showCloneDialog = ref(false)
const deleting = ref(false)
const cloneName = ref('')
const cloning = ref(false)

async function handleBackup() {
  try {
    await api.post(`/instances/${instanceId.value}/backups`)
    toast.success(t('backup.backupSuccess'))
    router.push({ name: 'InstanceBackups', params: { id: instanceId.value } })
  } catch (e: any) {
    toast.error(e?.response?.data?.message || t('common.failed'))
  }
}

async function handleRebuild() {
  const ok = await confirm({
    title: t('backup.rebuild'),
    description: t('backup.confirmRebuild'),
  })
  if (!ok) return
  try {
    const { data } = await api.post(`/instances/${instanceId.value}/rebuild`)
    toast.success(t('backup.rebuildSuccess'))
    if (data.data?.deploy_id) {
      router.push({ name: 'DeployProgress', params: { deployId: data.data.deploy_id } })
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.message || t('common.failed'))
  }
}

async function handleClone() {
  cloning.value = true
  try {
    const { data } = await api.post(`/instances/${instanceId.value}/clone`, { name: cloneName.value.trim() })
    toast.success(t('backup.cloneSuccess'))
    showCloneDialog.value = false
    cloneName.value = ''
    if (data.data?.deploy_id) {
      router.push({ name: 'DeployProgress', params: { deployId: data.data.deploy_id } })
    }
  } catch (e: any) {
    toast.error(e?.response?.data?.message || t('common.failed'))
  } finally {
    cloning.value = false
  }
}
function formatCpu(val: string): string {
  if (val.endsWith('m')) {
    const cores = parseInt(val.slice(0, -1), 10) / 1000
    const formatted = Number.isInteger(cores)
      ? formatNumber(cores, String(locale.value))
      : formatNumber(cores, String(locale.value), { maximumFractionDigits: 2, minimumFractionDigits: 0 })
    return `${formatted} ${t('orgSettings.specsCpuUnit')}`
  }
  return `${val} ${t('orgSettings.specsCpuUnit')}`
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollTimeout: ReturnType<typeof setTimeout> | null = null

const maskedGatewayToken = computed(() => {
  const token = gatewayToken.value
  if (!token) return ''
  if (token.length <= 4) return `${token.slice(0, 1)}****${token.slice(-1)}`
  if (token.length <= 8) return `${token.slice(0, 2)}****${token.slice(-2)}`
  return `${token.slice(0, 6)}********${token.slice(-4)}`
})

function syncGatewayToken(detail: InstanceDetail | null) {
  gatewayToken.value = detail?.env_vars?.GATEWAY_TOKEN || detail?.env_vars?.OPENCLAW_GATEWAY_TOKEN || ''
}

async function copyToken() {
  const ok = await copyToClipboard(gatewayToken.value)
  if (ok) {
    tokenCopied.value = true
    toast.success(t('agentDetailDialog.tokenCopied'))
    setTimeout(() => { tokenCopied.value = false }, 2000)
  } else {
    toast.error(t('common.copyFailed'))
  }
}

onMounted(async () => {
  await fetchDetail()
  if (instance.value?.status === 'restarting') {
    restarting.value = true
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
})

function normalizeWorkspaces(data: any): { id: string; name: string }[] {
  if (Array.isArray(data?.workspaces)) return data.workspaces
  if (data?.workspace_id) return [{ id: data.workspace_id, name: data.workspace_name ?? '' }]
  return []
}

async function fetchDetail() {
  loading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    const data = res.data.data
    if (data) {
      data.workspaces = normalizeWorkspaces(data)
    }
    instance.value = data
    syncGatewayToken(instance.value)
  } catch (e: any) {
    pageError.value = e?.response?.data?.message || t('agentDetailDialog.loadFailed')
  } finally {
    loading.value = false
  }
}

async function pollOnce() {
  try {
    const res = await api.get(`/instances/${instanceId.value}`)
    const data = res.data.data
    if (data) {
      data.workspaces = normalizeWorkspaces(data)
    }
    instance.value = data
    syncGatewayToken(instance.value)
    await refreshInstanceBasic()

    if (instance.value && instance.value.status !== 'restarting') {
      stopPolling()
      restarting.value = false
      toast.success(t('agentDetailDialog.restartDone'))
    }
  } catch {
    // 轮询期间忽略网络错误
  }
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

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (pollTimeout) { clearTimeout(pollTimeout); pollTimeout = null }
}

async function handleRestart() {
  showRestartDialog.value = false
  restarting.value = true
  try {
    const res = await api.post(`/instances/${instanceId.value}/restart`)
    toast.success(res.data?.message || t('instanceDetail.restartTriggered'))
    await refreshInstanceBasic()
    startPolling()
  } catch (e: any) {
    restarting.value = false
    const msg = e?.response?.data?.message || e?.message || t('agentDetailDialog.restartFailed')
    toast.error(msg)
    console.error('[handleRestart]', e)
  }
}

async function handleResetToken() {
  if (restarting.value || resettingToken.value) return

  const ok = await confirm({
    title: t('agentDetailDialog.resetTokenConfirmTitle'),
    description: t('agentDetailDialog.resetTokenConfirmDesc'),
    confirmText: t('agentDetailDialog.resetTokenConfirmAction'),
    cancelText: t('common.cancel'),
    variant: 'danger',
  })
  if (!ok) return

  resettingToken.value = true
  try {
    const res = await api.post(`/instances/${instanceId.value}/regenerate-token`)
    const token = res.data?.data?.token || ''
    if (token) {
      gatewayToken.value = token
      if (instance.value) {
        instance.value.env_vars = {
          ...(instance.value.env_vars || {}),
          GATEWAY_TOKEN: token,
          OPENCLAW_GATEWAY_TOKEN: token,
          NODESKCLAW_TOKEN: token,
        }
      }
    }
    restarting.value = true
    toast.success(res.data?.message || t('agentDetailDialog.resetTokenSuccess'))
    await refreshInstanceBasic()
    startPolling()
  } catch (e: any) {
    toast.error(e?.response?.data?.message || t('agentDetailDialog.resetTokenFailed'))
  } finally {
    resettingToken.value = false
  }
}

async function handleDelete() {
  showDeleteDialog.value = false
  deleting.value = true
  try {
    await api.delete(`/instances/${instanceId.value}`)
    toast.success(t('agentDetailDialog.deleted'))
    router.push('/instances')
  } catch (e: any) {
    deleting.value = false
    toast.error(e?.response?.data?.message || t('agentDetailDialog.deleteFailed'))
  }
}

interface SkillItem {
  skill_name: string
  name: string
  description: string
  type: string
}

const skillEditorOpen = ref(false)
const skills = ref<SkillItem[]>([])
const activeSkill = ref('')
const skillContent = ref('')
const skillOriginal = ref('')
const skillLoading = ref(false)
const skillSaving = ref(false)
const skillDirty = computed(() => skillContent.value !== skillOriginal.value)

async function fetchSkills() {
  try {
    const res = await api.get(`/instances/${instanceId.value}/skills`)
    skills.value = (res.data?.data ?? [])
      .filter((s: any) => s.type === 'emerged')
      .map((s: any) => ({
        skill_name: s.skill_name,
        name: s.name || s.skill_name,
        description: s.description || '',
        type: s.type,
      }))
    if (skills.value.length && !activeSkill.value) {
      activeSkill.value = skills.value[0].skill_name
      await fetchSkillContent(activeSkill.value)
    }
  } catch {
    skills.value = []
  }
}

async function fetchSkillContent(name: string) {
  skillLoading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}/skills/${name}/content`)
    skillContent.value = res.data?.data?.content ?? ''
    skillOriginal.value = skillContent.value
  } catch {
    toast.error(t('instanceDetail.skillEditor.loadFailed'))
    skillContent.value = ''
    skillOriginal.value = ''
  } finally {
    skillLoading.value = false
  }
}

async function selectSkill(name: string) {
  if (name === activeSkill.value) return
  activeSkill.value = name
  await fetchSkillContent(name)
}

async function saveSkillContent() {
  if (!activeSkill.value || skillSaving.value) return
  skillSaving.value = true
  try {
    await api.put(`/instances/${instanceId.value}/skills/${activeSkill.value}/content`, {
      content: skillContent.value,
    })
    skillOriginal.value = skillContent.value
    toast.success(t('instanceDetail.skillEditor.saved'))
  } catch {
    toast.error(t('instanceDetail.skillEditor.saveFailed'))
  } finally {
    skillSaving.value = false
  }
}

function toggleSkillEditor() {
  skillEditorOpen.value = !skillEditorOpen.value
  if (skillEditorOpen.value && !skills.value.length) {
    fetchSkills()
  }
}
</script>

<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="pageError" class="text-center py-20 text-destructive">{{ pageError }}</div>

    <div v-else-if="instance" class="space-y-6">
      <!-- Access Token -->
      <div v-if="gatewayToken" class="p-4 rounded-xl border border-primary/30 bg-primary/5 space-y-3">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm font-medium">{{ t('agentDetailDialog.accessToken') }}</p>
            <p class="text-xs text-muted-foreground mt-0.5">
              {{ restarting ? t('agentDetailDialog.accessTokenRestartingHint') : t('agentDetailDialog.accessTokenHint') }}
            </p>
          </div>
          <button
            class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="restarting || resettingToken"
            @click="handleResetToken"
          >
            <Loader2 v-if="resettingToken" class="w-4 h-4 animate-spin" />
            <RotateCcw v-else class="w-4 h-4" />
            {{ resettingToken ? t('agentDetailDialog.resettingToken') : t('agentDetailDialog.resetToken') }}
          </button>
        </div>
        <div class="flex items-center gap-2 px-3 py-2 rounded-lg bg-background/60 border border-border/50">
          <span class="flex-1 text-xs font-mono break-all text-foreground/80">{{ maskedGatewayToken }}</span>
          <button
            class="shrink-0 p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
            :disabled="!gatewayToken"
            @click="copyToken"
          >
            <Check v-if="tokenCopied" class="w-3.5 h-3.5 text-green-400" />
            <Copy v-else class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <!-- 基本信息 -->
      <div class="p-4 rounded-xl border border-border bg-card">
        <h2 class="text-sm font-medium mb-3">{{ t('agentDetailDialog.basicInfo') }}</h2>
        <div class="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span class="text-muted-foreground">{{ t('agentDetailDialog.imageVersion') }}</span>
            <span class="ml-2 font-mono text-xs bg-muted px-1.5 py-0.5 rounded">{{ instance.image_version }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">{{ t('agentDetailDialog.cpu') }}</span>
            <span class="ml-2">{{ formatCpu(instance.cpu_limit) }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">{{ t('agentDetailDialog.memory') }}</span>
            <span class="ml-2">{{ instance.mem_limit }}</span>
          </div>
          <div>
            <span class="text-muted-foreground">{{ t('orgUsage.storage') }}</span>
            <span class="ml-2">{{ instance.storage_size }}</span>
          </div>
          <div v-if="instance.runtime" class="col-span-2">
            <span class="text-muted-foreground">{{ t('engine.title') }}</span>
            <span class="relative group inline-block ml-2">
              <span class="text-xs bg-muted px-1.5 py-0.5 rounded cursor-default">{{ engineInfo?.name ?? instance.runtime }}</span>
              <span
                v-if="engineInfo"
                class="invisible group-hover:visible absolute left-0 top-full mt-1.5 z-50 w-56 p-3 rounded-lg border border-border bg-popover text-popover-foreground shadow-lg text-xs"
              >
                <span class="flex items-center gap-1.5">
                  <span class="font-medium text-sm">{{ engineInfo.name }}</span>
                  <span
                    v-for="tag in engineInfo.tags"
                    :key="tag"
                    class="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary"
                  >{{ tag }}</span>
                </span>
                <span class="block mt-1 text-muted-foreground leading-relaxed">{{ engineInfo.description }}</span>
                <span class="block mt-1.5 text-[10px] text-muted-foreground/60">Powered by {{ engineInfo.poweredBy }}</span>
              </span>
            </span>
          </div>
          <div class="col-span-2">
            <span class="text-muted-foreground">{{ t('agentDetailDialog.createdAt') }}</span>
            <span class="ml-2">{{ formatDateTime(instance.created_at, String(locale)) }}</span>
          </div>
          <div class="col-span-2">
            <span class="text-muted-foreground">{{ t('instanceDetail.workStatus') }}</span>
            <span class="ml-2 inline-flex items-center gap-1.5">
              <Circle
                class="w-2 h-2 fill-current"
                :class="[
                  getStatusDisplay(instance.display_status ?? '').bgColor.replace('bg-', 'text-'),
                  getStatusDisplay(instance.display_status ?? '').pulse ? 'animate-pulse' : '',
                ]"
              />
              <span :class="getStatusDisplay(instance.display_status ?? '').color">
                {{ t('displayStatus.' + getStatusDisplay(instance.display_status ?? '').key + '_desc') }}
              </span>
              <router-link
                v-if="getStatusDisplay(instance.display_status ?? '').key === 'error'"
                :to="{ name: 'InstanceRuntime', params: { id: instance.id } }"
                class="text-xs text-primary hover:underline ml-1"
              >
                {{ t('common.runtimeStatus') }}
              </router-link>
            </span>
          </div>
          <div v-if="instance.endpoint_url" class="col-span-2">
            <span class="text-muted-foreground">{{ t('instanceDetail.endpointUrl') }}</span>
            <a
              :href="instance.endpoint_url"
              target="_blank"
              rel="noopener"
              class="ml-2 text-primary hover:underline font-mono text-xs"
            >{{ instance.endpoint_url }}</a>
          </div>
        </div>
      </div>

      <div v-if="restarting" class="p-4 rounded-xl border border-amber-500/20 bg-amber-500/5">
        <div class="flex items-center gap-2 text-sm text-amber-400">
          <Loader2 class="w-4 h-4 animate-spin" />
          {{ t('displayStatus.restarting_desc') }}
        </div>
      </div>

      <!-- 操作 -->
      <div class="flex items-center gap-3 pt-4 border-t border-border flex-wrap">
        <button
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
          @click="fetchDetail"
        >
          <RefreshCw class="w-4 h-4" />
          {{ t('agentDetailDialog.refresh') }}
        </button>
        <button
          v-if="canEdit"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-amber-500/30 text-amber-400 text-sm hover:bg-amber-500/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="restarting"
          @click="showRestartDialog = true"
        >
          <RotateCcw class="w-4 h-4" :class="restarting ? 'animate-spin' : ''" />
          {{ restarting ? t('agentDetailDialog.restarting') : t('agentDetailDialog.restart') }}
        </button>
        <button
          v-if="canEdit && instance?.status === 'running'"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
          @click="handleBackup"
        >
          <Archive class="w-4 h-4" />
          {{ t('backup.create') }}
        </button>
        <button
          v-if="canAdmin && instance?.status === 'running'"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
          @click="showCloneDialog = true"
        >
          <CopyPlus class="w-4 h-4" />
          {{ t('backup.clone') }}
        </button>
        <button
          v-if="canAdmin && (instance?.status === 'failed' || instance?.health_status === 'unhealthy')"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-amber-500/30 text-amber-400 text-sm hover:bg-amber-500/10 transition-colors"
          @click="handleRebuild"
        >
          <Wrench class="w-4 h-4" />
          {{ t('backup.rebuild') }}
        </button>
        <button
          v-if="canAdmin"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-red-500/30 text-red-400 text-sm hover:bg-red-500/10 transition-colors ml-auto disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="deleting"
          @click="showDeleteDialog = true"
        >
          <Loader2 v-if="deleting" class="w-4 h-4 animate-spin" />
          <Trash2 v-else class="w-4 h-4" />
          {{ deleting ? t('agentDetailDialog.deleting') : t('agentDetailDialog.delete') }}
        </button>
      </div>

      <!-- 角色与提示词 -->
      <div class="rounded-xl border border-border bg-card overflow-hidden">
        <button
          class="flex items-center justify-between w-full px-4 py-3 text-left hover:bg-muted/30 transition-colors"
          @click="toggleSkillEditor"
        >
          <div class="flex items-center gap-2">
            <ChevronRight v-if="!skillEditorOpen" class="w-4 h-4 text-muted-foreground" />
            <ChevronDown v-else class="w-4 h-4 text-muted-foreground" />
            <span class="text-sm font-medium">{{ t('instanceDetail.skillEditor.title') }}</span>
            <span
              v-if="skills.length"
              class="text-xs px-1.5 py-0.5 rounded-full bg-muted text-muted-foreground"
            >{{ skills.length }}</span>
          </div>
        </button>

        <div v-if="skillEditorOpen" class="border-t border-border">
          <div v-if="!skills.length && !skillLoading" class="px-4 py-8 text-center text-sm text-muted-foreground">
            {{ t('instanceDetail.skillEditor.empty') }}
          </div>
          <template v-else>
            <div class="flex gap-1 px-4 pt-3 pb-0 overflow-x-auto">
              <button
                v-for="s in skills"
                :key="s.skill_name"
                class="px-3 py-1.5 text-xs rounded-t-lg border border-b-0 transition-colors whitespace-nowrap"
                :class="s.skill_name === activeSkill
                  ? 'bg-card border-border text-foreground font-medium'
                  : 'bg-transparent border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/30'"
                @click="selectSkill(s.skill_name)"
              >{{ s.name }}</button>
            </div>

            <div class="px-4 pb-4">
              <div v-if="skillLoading" class="flex items-center justify-center py-12">
                <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
              <template v-else>
                <textarea
                  v-model="skillContent"
                  class="w-full h-80 px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono resize-y scrollbar-compact"
                  :readonly="!canEdit"
                  spellcheck="false"
                />
                <div class="flex items-center justify-between mt-2">
                  <p class="text-xs text-muted-foreground">{{ t('instanceDetail.skillEditor.restartHint') }}</p>
                  <button
                    v-if="canEdit"
                    class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    :class="skillDirty
                      ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                      : 'border border-border text-muted-foreground'"
                    :disabled="!skillDirty || skillSaving"
                    @click="saveSkillContent"
                  >
                    <Loader2 v-if="skillSaving" class="w-3.5 h-3.5 animate-spin" />
                    <Save v-else class="w-3.5 h-3.5" />
                    {{ t('instanceDetail.skillEditor.save') }}
                  </button>
                </div>
              </template>
            </div>
          </template>
        </div>
      </div>

      <!-- 克隆对话框 -->
      <Teleport to="body">
        <Transition name="fade">
          <div v-if="showCloneDialog" class="fixed inset-0 z-50 flex items-center justify-center">
            <div class="absolute inset-0 bg-black/50" @click="showCloneDialog = false" />
            <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
              <h3 class="text-base font-semibold">{{ t('backup.clone') }}</h3>
              <p class="text-sm text-muted-foreground">{{ t('backup.confirmClone') }}</p>
              <div>
                <label class="block text-sm mb-1.5">{{ t('backup.cloneNameLabel') }}</label>
                <input
                  v-model="cloneName"
                  class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
                  :placeholder="t('backup.cloneNamePlaceholder')"
                />
              </div>
              <div class="flex justify-end gap-2">
                <button
                  class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-card transition-colors"
                  @click="showCloneDialog = false"
                >{{ t('common.cancel') }}</button>
                <button
                  class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 disabled:opacity-50"
                  :disabled="!cloneName.trim() || cloning"
                  @click="handleClone"
                >
                  <Loader2 v-if="cloning" class="w-4 h-4 animate-spin inline mr-1" />
                  {{ t('backup.startClone') }}
                </button>
              </div>
            </div>
          </div>
        </Transition>
      </Teleport>
    </div>

    <!-- 重启确认弹窗 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showRestartDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showRestartDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-lg bg-amber-500/10">
                <AlertTriangle class="w-5 h-5 text-amber-400" />
              </div>
              <h3 class="text-base font-semibold">{{ t('agentDetailDialog.restartConfirmTitle') }}</h3>
            </div>
            <div class="text-sm text-muted-foreground space-y-2">
              <p>{{ t('instanceDetail.restartConfirmIntro') }}</p>
              <ul class="list-disc list-inside space-y-1 text-xs">
                <li>{{ t('instanceDetail.restartImpactProcesses') }}</li>
                <li>{{ t('instanceDetail.restartImpactAvailability') }}</li>
                <li>{{ t('instanceDetail.restartImpactTasks') }}</li>
              </ul>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showRestartDialog = false"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                class="px-4 py-2 rounded-lg bg-amber-500 text-white text-sm font-medium hover:bg-amber-600 transition-colors"
                @click="handleRestart"
              >
                {{ t('instanceDetail.confirmRestart') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showDeleteDialog" class="fixed inset-0 z-50 flex items-center justify-center">
          <div class="absolute inset-0 bg-black/50" @click="showDeleteDialog = false" />
          <div class="relative bg-card border border-border rounded-xl p-6 w-full max-w-sm shadow-lg space-y-4">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-lg bg-red-500/10">
                <AlertTriangle class="w-5 h-5 text-red-400" />
              </div>
              <h3 class="text-base font-semibold">{{ t('agentDetailDialog.deleteConfirmTitle') }}</h3>
            </div>
            <div v-if="instance?.workspaces?.length" class="text-sm text-muted-foreground space-y-2">
              <p>{{ t('instanceDetail.cannotDeleteInWorkspaces', { names: joinNames(instance.workspaces.map(w => w.name)) }) }}</p>
              <p class="text-xs">{{ t('instanceDetail.workspaces') }}:</p>
              <div class="flex flex-wrap gap-2 mt-1">
                <router-link
                  v-for="ws in instance.workspaces"
                  :key="ws.id"
                  :to="`/workspace/${ws.id}`"
                  class="text-xs text-primary hover:underline"
                >
                  {{ ws.name }}
                </router-link>
              </div>
            </div>
            <div v-else class="text-sm text-muted-foreground space-y-2">
              <p>{{ t('instanceDetail.deleteConfirmQuestion', { name: instanceBasic?.name }) }}</p>
              <ul class="list-disc list-inside space-y-1 text-xs">
                <li>{{ t(isDocker ? 'instanceDetail.deleteImpactDocker' : 'instanceDetail.deleteImpactK8s') }}</li>
                <li>{{ t('instanceDetail.deleteImpactData') }}</li>
                <li>{{ t('instanceDetail.deleteImpactIrreversible') }}</li>
              </ul>
            </div>
            <div class="flex justify-end gap-3 pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition-colors"
                @click="showDeleteDialog = false"
              >
                {{ instance?.workspaces?.length ? t('common.close') : t('common.cancel') }}
              </button>
              <button
                v-if="!instance?.workspaces?.length"
                class="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600 transition-colors"
                @click="handleDelete"
              >
                {{ t('common.delete') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
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
