<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import {
  Ban,
  Box,
  FileText,
  Hammer,
  Loader2,
  Plus,
  RefreshCw,
  Star,
  Trash2,
} from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import BaseTooltip from '@/components/shared/BaseTooltip.vue'

const { t } = useI18n()
const toast = useToast()

interface EngineVersion {
  id: string
  runtime: string
  version: string
  image_tag: string
  status: string
  release_notes: string | null
  is_default: boolean
  created_at: string
}

interface RuntimeOption {
  runtime_id: string
  display_name: string
  display_powered_by?: string
  order?: number
}

interface ClusterOption {
  id: string
  name: string
  status: string
  compute_provider: string
}

interface ImageBuild {
  id: string
  cluster_id: string
  runtime: string
  version: string
  image_reference: string
  source_ref: string
  status: 'pending' | 'running' | 'succeeded' | 'failed'
  log_text?: string | null
  error_message: string | null
  engine_version_id: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

const loading = ref(false)
const versions = ref<EngineVersion[]>([])
const selectedRuntime = ref('openclaw')
const runtimeOptions = ref<RuntimeOption[]>([])
const clusters = ref<ClusterOption[]>([])

const builds = ref<ImageBuild[]>([])
const buildsLoading = ref(false)
const showBuildDialog = ref(false)
const buildSubmitting = ref(false)
const buildForm = ref({ version: '', cluster_id: '', source_ref: '', release_notes: '' })
const showLogsDialog = ref(false)
const selectedBuild = ref<ImageBuild | null>(null)
const logsLoading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

const showPublishDialog = ref(false)
const publishForm = ref({ version: '', image_tag: '', release_notes: '' })
const publishing = ref(false)
const registryTags = ref<string[]>([])
const loadingTags = ref(false)
const tagDropdownOpen = ref(false)

const activeBuilds = computed(() => builds.value.filter(build => ['pending', 'running'].includes(build.status)))
const buildDisabledReason = computed(() => {
  if (clusters.value.length === 0) return t('orgSettings.imageBuildNoClusterTooltip')
  return ''
})

async function fetchRuntimeOptions() {
  try {
    const res = await api.get('/engines')
    runtimeOptions.value = res.data.data ?? []
    if (runtimeOptions.value.length > 0 && !runtimeOptions.value.some(rt => rt.runtime_id === selectedRuntime.value)) {
      selectedRuntime.value = runtimeOptions.value[0].runtime_id
    }
  } catch {
    runtimeOptions.value = []
  }
}

async function fetchClusters() {
  try {
    const res = await api.get('/image-builds/eligible-clusters')
    clusters.value = ((res.data.data ?? []) as ClusterOption[]).filter(cluster => cluster.compute_provider === 'k8s')
    if (!buildForm.value.cluster_id && clusters.value.length > 0) {
      buildForm.value.cluster_id = clusters.value[0].id
    }
  } catch {
    clusters.value = []
  }
}

function resetPublishState() {
  showPublishDialog.value = false
  publishForm.value = { version: '', image_tag: '', release_notes: '' }
  registryTags.value = []
  loadingTags.value = false
  tagDropdownOpen.value = false
}

async function fetchVersions() {
  loading.value = true
  const runtime = selectedRuntime.value
  try {
    const res = await api.get('/engine-versions', { params: { runtime } })
    if (runtime === selectedRuntime.value) {
      versions.value = res.data.data ?? []
    }
  } catch {
    if (runtime === selectedRuntime.value) versions.value = []
  } finally {
    if (runtime === selectedRuntime.value) loading.value = false
  }
}

async function fetchBuilds() {
  buildsLoading.value = true
  const runtime = selectedRuntime.value
  try {
    const res = await api.get('/image-builds', { params: { runtime } })
    if (runtime === selectedRuntime.value) builds.value = res.data.data ?? []
  } catch {
    if (runtime === selectedRuntime.value) builds.value = []
  } finally {
    if (runtime === selectedRuntime.value) buildsLoading.value = false
  }
}

async function refreshActiveBuild(build: ImageBuild) {
  try {
    const res = await api.get(`/image-builds/${build.id}`)
    const next = res.data.data as ImageBuild
    const index = builds.value.findIndex(item => item.id === build.id)
    if (index >= 0) builds.value[index] = next
    if (selectedBuild.value?.id === next.id) selectedBuild.value = next
    if (build.status !== 'succeeded' && next.status === 'succeeded') {
      toast.success(t('orgSettings.imageBuildSucceeded', { image: next.image_reference }))
      await fetchVersions()
    }
    if (build.status !== 'failed' && next.status === 'failed') {
      toast.error(next.error_message || t('orgSettings.imageBuildFailed'))
    }
  } catch {
    return
  }
}

async function pollActiveBuilds() {
  await Promise.all(activeBuilds.value.map(build => refreshActiveBuild(build)))
}

function openBuildDialog() {
  if (clusters.value.length === 0) return
  buildForm.value = {
    version: '',
    cluster_id: clusters.value[0]?.id || '',
    source_ref: '',
    release_notes: '',
  }
  showBuildDialog.value = true
}

async function handleBuild() {
  if (!buildForm.value.version.trim() || !buildForm.value.cluster_id) return
  buildSubmitting.value = true
  try {
    const res = await api.post('/image-builds', {
      runtime: selectedRuntime.value,
      version: buildForm.value.version.trim(),
      cluster_id: buildForm.value.cluster_id,
      source_ref: buildForm.value.source_ref.trim() || null,
      release_notes: buildForm.value.release_notes.trim() || null,
    })
    const build = res.data.data as ImageBuild
    builds.value = [build, ...builds.value.filter(item => item.id !== build.id)]
    showBuildDialog.value = false
    toast.success(t('orgSettings.imageBuildStarted'))
  } catch (error: unknown) {
    toast.error(resolveApiErrorMessage(error, t('orgSettings.imageBuildStartFailed')))
  } finally {
    buildSubmitting.value = false
  }
}

async function openBuildLogs(build: ImageBuild) {
  selectedBuild.value = build
  showLogsDialog.value = true
  await refreshBuildLogs()
}

async function refreshBuildLogs() {
  if (!selectedBuild.value) return
  logsLoading.value = true
  try {
    const res = await api.get(`/image-builds/${selectedBuild.value.id}/logs`)
    const next = res.data.data as ImageBuild
    selectedBuild.value = next
    const index = builds.value.findIndex(item => item.id === next.id)
    if (index >= 0) builds.value[index] = next
    if (next.status === 'succeeded') await fetchVersions()
  } catch (error: unknown) {
    toast.error(resolveApiErrorMessage(error, t('orgSettings.imageBuildLogsFailed')))
  } finally {
    logsLoading.value = false
  }
}

function clusterName(clusterId: string) {
  return clusters.value.find(cluster => cluster.id === clusterId)?.name || clusterId.slice(0, 8)
}

function buildStatusLabel(status: ImageBuild['status']) {
  return t(`orgSettings.imageBuildStatus.${status}`)
}

function buildStatusClass(status: ImageBuild['status']) {
  if (status === 'succeeded') return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
  if (status === 'failed') return 'bg-destructive/10 text-destructive'
  if (status === 'running') return 'bg-primary/10 text-primary'
  return 'bg-muted text-muted-foreground'
}

function formatDate(value: string | null) {
  if (!value) return '-'
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

async function fetchRegistryTags() {
  loadingTags.value = true
  const runtime = selectedRuntime.value
  try {
    const res = await api.get('/registry/tags', { params: { runtime } })
    const tags = (res.data.data ?? []) as { tag: string }[]
    if (runtime === selectedRuntime.value) registryTags.value = tags.map(tag => tag.tag)
  } catch {
    if (runtime === selectedRuntime.value) registryTags.value = []
  } finally {
    if (runtime === selectedRuntime.value) loadingTags.value = false
  }
}

function openPublishDialog() {
  resetPublishState()
  showPublishDialog.value = true
  fetchRegistryTags()
}

async function selectRuntime(runtimeId: string) {
  if (selectedRuntime.value === runtimeId) return
  selectedRuntime.value = runtimeId
  resetPublishState()
  showBuildDialog.value = false
  await Promise.all([fetchVersions(), fetchBuilds()])
}

function selectTag(tag: string) {
  publishForm.value.image_tag = tag
  publishForm.value.version = tag.replace(/^v/, '')
  tagDropdownOpen.value = false
}

async function handlePublish() {
  if (!publishForm.value.version || !publishForm.value.image_tag) return
  publishing.value = true
  try {
    await api.post('/engine-versions', {
      runtime: selectedRuntime.value,
      version: publishForm.value.version,
      image_tag: publishForm.value.image_tag,
      release_notes: publishForm.value.release_notes || null,
    })
    toast.success(t('orgSettings.engineVersionsPublished'))
    showPublishDialog.value = false
    await fetchVersions()
  } catch (error: unknown) {
    toast.error(resolveApiErrorMessage(error, t('orgSettings.engineVersionsPublishFailed')))
  } finally {
    publishing.value = false
  }
}

async function setDefault(id: string) {
  try {
    await api.patch(`/engine-versions/${id}`, { is_default: true })
    toast.success(t('orgSettings.engineVersionsDefaultSet'))
    await fetchVersions()
  } catch (error: unknown) {
    toast.error(resolveApiErrorMessage(error))
  }
}

async function deprecate(id: string) {
  try {
    await api.patch(`/engine-versions/${id}`, { status: 'deprecated' })
    toast.success(t('orgSettings.engineVersionsDeprecated'))
    await fetchVersions()
  } catch (error: unknown) {
    toast.error(resolveApiErrorMessage(error))
  }
}

async function remove(id: string) {
  try {
    await api.delete(`/engine-versions/${id}`)
    toast.success(t('orgSettings.engineVersionsDeleted'))
    await fetchVersions()
  } catch (error: unknown) {
    toast.error(resolveApiErrorMessage(error))
  }
}

onMounted(async () => {
  await fetchRuntimeOptions()
  await Promise.all([fetchClusters(), fetchVersions(), fetchBuilds()])
  pollTimer = setInterval(pollActiveBuilds, 3000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">{{ t('orgSettings.engineVersionsTitle') }}</h2>
      <p class="mt-1 text-sm text-muted-foreground">{{ t('orgSettings.engineVersionsDesc') }}</p>
    </div>

    <div class="flex items-center justify-between gap-4">
      <div class="inline-flex rounded-lg border border-border bg-card p-1">
        <Button
          v-for="runtime in runtimeOptions"
          :key="runtime.runtime_id"
          variant="unstyled"
          size="unstyled"
          class="rounded-md px-3 py-1.5 text-sm transition-colors"
          :class="selectedRuntime === runtime.runtime_id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'"
          @click="selectRuntime(runtime.runtime_id)"
        >
          {{ runtime.display_name }}
        </Button>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" @click="openPublishDialog">
          <Plus class="mr-1.5 h-4 w-4" />
          {{ t('orgSettings.engineVersionsRegister') }}
        </Button>
        <BaseTooltip :text="buildDisabledReason">
          <Button size="sm" :disabled="Boolean(buildDisabledReason)" @click="openBuildDialog">
            <Hammer class="mr-1.5 h-4 w-4" />
            {{ t('orgSettings.imageBuildAction') }}
          </Button>
        </BaseTooltip>
      </div>
    </div>

    <div v-if="clusters.length === 0" class="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-sm">
      <p class="font-medium">{{ t('orgSettings.imageBuildNoCluster') }}</p>
      <p class="mt-1 text-muted-foreground">{{ t('orgSettings.imageBuildNoClusterHint') }}</p>
      <RouterLink :to="{ name: 'OrgSettingsClusters' }" class="mt-2 inline-flex text-primary hover:underline">
        {{ t('orgSettings.imageBuildGoClusters') }}
      </RouterLink>
    </div>

    <section class="space-y-3">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold">{{ t('orgSettings.imageBuildTasksTitle') }}</h3>
          <p class="mt-0.5 text-xs text-muted-foreground">{{ t('orgSettings.imageBuildTasksDesc') }}</p>
        </div>
        <Button variant="ghost" size="sm" :disabled="buildsLoading" @click="fetchBuilds">
          <RefreshCw class="h-3.5 w-3.5" :class="buildsLoading ? 'animate-spin' : ''" />
        </Button>
      </div>

      <div v-if="buildsLoading" class="flex justify-center py-6">
        <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
      <div v-else-if="builds.length === 0" class="rounded-lg border border-dashed border-border py-7 text-center text-sm text-muted-foreground">
        {{ t('orgSettings.imageBuildEmpty') }}
      </div>
      <div v-else class="space-y-2">
        <div v-for="build in builds" :key="build.id" class="rounded-lg border border-border bg-card p-4">
          <div class="flex items-start justify-between gap-4">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <Box class="h-4 w-4 shrink-0 text-muted-foreground" />
                <span class="truncate font-mono text-sm">{{ build.image_reference }}</span>
                <span class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium" :class="buildStatusClass(build.status)">
                  <Loader2 v-if="['pending', 'running'].includes(build.status)" class="h-3 w-3 animate-spin" />
                  {{ buildStatusLabel(build.status) }}
                </span>
              </div>
              <p class="mt-1 text-xs text-muted-foreground">
                {{ clusterName(build.cluster_id) }} · {{ build.source_ref }} · {{ formatDate(build.created_at) }}
              </p>
              <p v-if="build.error_message" class="mt-2 text-xs text-destructive">{{ build.error_message }}</p>
            </div>
            <Button variant="outline" size="sm" class="shrink-0" @click="openBuildLogs(build)">
              <FileText class="mr-1.5 h-3.5 w-3.5" />
              {{ t('orgSettings.imageBuildViewLogs') }}
            </Button>
          </div>
        </div>
      </div>
    </section>

    <section class="space-y-3 border-t border-border pt-5">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="text-sm font-semibold">{{ t('orgSettings.engineVersionsPublishedTitle') }}</h3>
          <p class="mt-0.5 text-xs text-muted-foreground">{{ t('orgSettings.engineVersionsPublishedDesc') }}</p>
        </div>
        <Button variant="ghost" size="sm" :disabled="loading" @click="fetchVersions">
          <RefreshCw class="h-3.5 w-3.5" :class="loading ? 'animate-spin' : ''" />
        </Button>
      </div>

      <div v-if="loading" class="flex justify-center py-8">
        <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
      <div v-else-if="versions.length === 0" class="rounded-lg border border-dashed border-border py-8 text-center text-sm text-muted-foreground">
        {{ t('orgSettings.engineVersionsEmpty') }}
      </div>
      <div v-else class="space-y-2">
        <div v-for="version in versions" :key="version.id" class="flex items-center justify-between rounded-lg border border-border bg-card p-3">
          <div class="flex min-w-0 items-center gap-3">
            <span class="font-mono text-sm">{{ version.image_tag }}</span>
            <span v-if="version.is_default" class="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
              <Star class="h-3 w-3" />
              {{ t('orgSettings.engineVersionsDefault') }}
            </span>
            <span v-if="version.release_notes" class="max-w-[240px] truncate text-xs text-muted-foreground">{{ version.release_notes }}</span>
          </div>
          <div class="flex shrink-0 items-center gap-1.5">
            <Button v-if="!version.is_default" variant="ghost" size="sm" @click="setDefault(version.id)">
              {{ t('orgSettings.engineVersionsSetDefault') }}
            </Button>
            <Button v-if="!version.is_default" variant="ghost" size="icon" @click="deprecate(version.id)">
              <Ban class="h-3.5 w-3.5" />
            </Button>
            <Button v-if="!version.is_default" variant="ghost" size="icon" @click="remove(version.id)">
              <Trash2 class="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="showBuildDialog" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showBuildDialog = false" />
        <div class="relative w-full max-w-lg space-y-4 rounded-xl border border-border bg-card p-6 shadow-xl">
          <div>
            <h3 class="text-base font-semibold">{{ t('orgSettings.imageBuildDialogTitle') }}</h3>
            <p class="mt-1 text-xs text-muted-foreground">{{ t('orgSettings.imageBuildDialogDesc') }}</p>
          </div>
          <div class="space-y-3">
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('orgSettings.engineVersionsVersion') }}</label>
              <Input v-model="buildForm.version" class="font-mono" placeholder="2026.8.25" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('orgSettings.imageBuildCluster') }}</label>
              <select v-model="buildForm.cluster_id" class="h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring">
                <option v-for="cluster in clusters" :key="cluster.id" :value="cluster.id">
                  {{ cluster.name }} · {{ cluster.status }}
                </option>
              </select>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('orgSettings.imageBuildSourceRef') }}</label>
              <Input v-model="buildForm.source_ref" class="font-mono" :placeholder="t('orgSettings.imageBuildSourceRefPlaceholder')" />
              <p class="mt-1 text-xs text-muted-foreground">{{ t('orgSettings.imageBuildSourceRefHint') }}</p>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('orgSettings.engineVersionsReleaseNotes') }}</label>
              <Textarea v-model="buildForm.release_notes" rows="3" class="resize-none" />
            </div>
          </div>
          <div class="rounded-lg bg-muted/40 p-3 text-xs text-muted-foreground">
            {{ t('orgSettings.imageBuildRegistryHint') }}
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" @click="showBuildDialog = false">{{ t('common.cancel') }}</Button>
            <Button size="sm" :disabled="buildSubmitting || !buildForm.version.trim() || !buildForm.cluster_id" @click="handleBuild">
              <Loader2 v-if="buildSubmitting" class="mr-1.5 h-3.5 w-3.5 animate-spin" />
              <Hammer v-else class="mr-1.5 h-3.5 w-3.5" />
              {{ t('orgSettings.imageBuildStart') }}
            </Button>
          </div>
        </div>
      </div>

      <div v-if="showLogsDialog && selectedBuild" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showLogsDialog = false" />
        <div class="relative flex max-h-[80vh] w-full max-w-3xl flex-col rounded-xl border border-border bg-card shadow-xl">
          <div class="flex items-start justify-between gap-4 border-b border-border p-5">
            <div class="min-w-0">
              <h3 class="text-base font-semibold">{{ t('orgSettings.imageBuildLogsTitle') }}</h3>
              <p class="mt-1 truncate font-mono text-xs text-muted-foreground">{{ selectedBuild.image_reference }}</p>
            </div>
            <Button variant="outline" size="sm" :disabled="logsLoading" @click="refreshBuildLogs">
              <RefreshCw class="mr-1.5 h-3.5 w-3.5" :class="logsLoading ? 'animate-spin' : ''" />
              {{ t('common.refresh') }}
            </Button>
          </div>
          <div class="min-h-0 flex-1 overflow-auto p-5">
            <pre v-if="selectedBuild.log_text" class="whitespace-pre-wrap break-words rounded-lg bg-black/90 p-4 font-mono text-xs leading-5 text-zinc-100">{{ selectedBuild.log_text }}</pre>
            <div v-else class="py-10 text-center text-sm text-muted-foreground">
              <Loader2 v-if="logsLoading" class="mx-auto mb-2 h-5 w-5 animate-spin" />
              {{ t('orgSettings.imageBuildLogsEmpty') }}
            </div>
          </div>
          <div class="flex justify-end border-t border-border p-4">
            <Button variant="outline" size="sm" @click="showLogsDialog = false">{{ t('common.close') }}</Button>
          </div>
        </div>
      </div>

      <div v-if="showPublishDialog" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="absolute inset-0 bg-black/50" @click="showPublishDialog = false" />
        <div class="relative w-full max-w-md space-y-4 rounded-xl border border-border bg-card p-6 shadow-xl">
          <h3 class="text-base font-semibold">{{ t('orgSettings.engineVersionsPublishDialogTitle') }}</h3>
          <div class="space-y-3">
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('orgSettings.engineVersionsSelectTag') }}</label>
              <div class="relative">
                <Button variant="outline" class="w-full justify-between" @click="tagDropdownOpen = !tagDropdownOpen">
                  <span class="font-mono text-xs">{{ publishForm.image_tag || t('engine.selectVersion') }}</span>
                  <RefreshCw v-if="loadingTags" class="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                </Button>
                <div v-if="tagDropdownOpen && registryTags.length > 0" class="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-border bg-card shadow-lg">
                  <Button v-for="tag in registryTags" :key="tag" variant="ghost" class="w-full justify-start font-mono text-xs" @click="selectTag(tag)">
                    {{ tag }}
                  </Button>
                </div>
              </div>
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('orgSettings.engineVersionsVersion') }}</label>
              <Input v-model="publishForm.version" class="font-mono" placeholder="2026.8.25" />
            </div>
            <div>
              <label class="mb-1 block text-sm font-medium">{{ t('orgSettings.engineVersionsReleaseNotes') }}</label>
              <Textarea v-model="publishForm.release_notes" rows="3" class="resize-none" />
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <Button variant="outline" size="sm" @click="showPublishDialog = false">{{ t('common.cancel') }}</Button>
            <Button size="sm" :disabled="publishing || !publishForm.version || !publishForm.image_tag" @click="handlePublish">
              <Loader2 v-if="publishing" class="mr-1.5 h-3.5 w-3.5 animate-spin" />
              {{ t('orgSettings.engineVersionsRegister') }}
            </Button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
