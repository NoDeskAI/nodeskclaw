<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Loader2, Server, RefreshCw, Package, Dna, X } from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useGeneStore } from '@/stores/gene'
import { useClusterStore } from '@/stores/cluster'
import { useEdition } from '@/composables/useFeature'
import { getStatusDisplay } from '@/utils/instanceStatus'
import BaseTooltip from '@/components/shared/BaseTooltip.vue'
import type { TemplateInfo } from '@/stores/gene'
import { Button } from '@/components/ui/button'
import { Table, TableHeader, TableBody, TableFooter, TableRow, TableHead, TableCell, TableCaption } from '@/components/ui/table'

interface InstanceInfo {
  id: string
  name: string
  display_name?: string | null
  effective_name?: string
  cluster_id: string
  namespace: string
  image_version: string
  replicas: number
  available_replicas: number
  status: string
  health_status?: string
  display_status?: string
  service_type: string
  ingress_domain: string | null
  created_by: string
  created_at: string
  updated_at: string
  my_role: string | null
  compute_provider?: string
}

const roleLabels: Record<string, string> = {
  admin: 'instanceMembers.roleAdmin',
  editor: 'instanceMembers.roleEditor',
  user: 'instanceMembers.roleUser',
  viewer: 'instanceMembers.roleViewer',
}

function getRoleLabel(role: string | null): string {
  if (!role) return '-'
  const key = roleLabels[role]
  return key ? t(key) : role
}

const router = useRouter()
const { t, locale } = useI18n()
const geneStore = useGeneStore()
const clusterStore = useClusterStore()
const { isEE } = useEdition()

const hasCluster = computed(() => clusterStore.clusters.length > 0)
const loading = ref(true)
const instances = ref<InstanceInfo[]>([])
const error = ref('')

const templateSelectorOpen = ref(false)
const templateLoading = ref(false)

async function openTemplateSelector() {
  templateSelectorOpen.value = true
  templateLoading.value = true
  try {
    await geneStore.fetchTemplates({ page_size: 50 })
  } finally {
    templateLoading.value = false
  }
}

function selectTemplate(tpl: TemplateInfo) {
  templateSelectorOpen.value = false
  router.push(`/instances/create?template_id=${tpl.id}`)
}

function getStatus(inst: InstanceInfo) {
  return getStatusDisplay(inst.display_status ?? '')
}

function getStatusLabel(inst: InstanceInfo) {
  const d = getStatusDisplay(inst.display_status ?? '')
  return t(`displayStatus.${d.key}`)
}

function getInstanceDisplayName(inst: InstanceInfo): string {
  return inst.effective_name || inst.display_name || inst.name
}

const sortedInstances = computed(() =>
  [...instances.value].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  ),
)

async function fetchInstances() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/instances')
    instances.value = data.data ?? []
  } catch (e: unknown) {
    error.value = resolveApiErrorMessage(e, t('instanceList.loadFailed'))
  } finally {
    loading.value = false
  }
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const currentLocale = locale.value === 'zh-CN' ? 'zh-CN' : 'en-US'
  return d.toLocaleDateString(currentLocale, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  fetchInstances()
  clusterStore.fetchClusters()
})
</script>

<template>
  <div class="max-w-5xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">{{ t('instanceList.title') }}</h1>
        <p class="text-sm text-muted-foreground mt-1">{{ t('instanceList.subtitle') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="unstyled" size="unstyled"
          class="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          @click="fetchInstances"
        >
          <RefreshCw class="w-4 h-4" />
          {{ t('instanceList.refresh') }}
        </Button>
        <BaseTooltip :text="!hasCluster ? t('instanceList.noClusterHint') : ''">
          <Button variant="unstyled" size="unstyled"
            class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            :disabled="!hasCluster"
            @click="router.push('/instances/create')"
          >
            <Plus class="w-4 h-4" />
            {{ t('instanceList.createInstance') }}
          </Button>
        </BaseTooltip>
        <BaseTooltip :text="!hasCluster ? t('instanceList.noClusterHint') : ''">
          <Button variant="unstyled" size="unstyled"
            class="flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors disabled:opacity-50"
            :disabled="!hasCluster"
            @click="openTemplateSelector"
          >
            <Package class="w-4 h-4" />
            {{ t('instanceList.createFromTemplate') }}
          </Button>
        </BaseTooltip>
      </div>
    </div>

    <!-- Template selector modal -->
    <div v-if="templateSelectorOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="templateSelectorOpen = false">
      <div class="w-[480px] max-h-[60vh] bg-card border border-border rounded-xl shadow-lg flex flex-col">
        <div class="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 class="font-semibold text-sm">{{ t('template.chooseTemplate') }}</h3>
          <Button variant="unstyled" size="unstyled" class="p-1 rounded hover:bg-muted transition-colors" @click="templateSelectorOpen = false">
            <X class="w-4 h-4" />
          </Button>
        </div>
        <div class="flex-1 min-h-0 overflow-y-auto p-3 space-y-2">
          <div v-if="templateLoading" class="flex justify-center py-8">
            <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
          <template v-else-if="geneStore.templates.length > 0">
            <Button variant="unstyled" size="unstyled"
              v-for="tpl in geneStore.templates"
              :key="tpl.id"
              class="w-full flex items-center gap-3 p-3 rounded-lg border border-border hover:border-primary/30 hover:bg-primary/5 transition-colors text-left"
              @click="selectTemplate(tpl)"
            >
              <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                <Package class="w-4 h-4 text-primary" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="text-sm font-medium">{{ tpl.name }}</div>
                <div class="text-xs text-muted-foreground line-clamp-1">{{ tpl.short_description ?? '' }}</div>
              </div>
              <span class="text-xs text-muted-foreground shrink-0 flex items-center gap-1">
                <Dna class="w-3 h-3" />
                {{ tpl.gene_slugs?.length ?? 0 }}
              </span>
            </Button>
          </template>
          <div v-else class="text-center py-8 text-muted-foreground text-sm">
            {{ t('template.noTemplates') }}
          </div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-center py-20 space-y-4">
      <div class="w-16 h-16 rounded-2xl bg-red-500/10 flex items-center justify-center mx-auto">
        <Server class="w-8 h-8 text-red-400" />
      </div>
      <p class="text-sm text-red-400">{{ error }}</p>
      <Button variant="unstyled" size="unstyled"
        class="mt-2 px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
        @click="fetchInstances"
      >
        {{ t('instanceList.retry') }}
      </Button>
    </div>

    <!-- Empty state: no cluster + no instances -->
    <div
      v-else-if="instances.length === 0 && !hasCluster"
      class="text-center py-20 space-y-4"
    >
      <div class="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
        <Server class="w-8 h-8 text-primary" />
      </div>
      <h3 class="text-lg font-semibold">{{ t('instanceList.noClusterTitle') }}</h3>
      <p class="text-sm text-muted-foreground max-w-sm mx-auto">
        {{ isEE ? t('instanceList.noClusterDescEE') : t('instanceList.noClusterDesc') }}
      </p>
      <Button variant="unstyled" size="unstyled"
        v-if="!isEE"
        class="mt-4 px-6 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="router.push('/org-settings/clusters')"
      >
        {{ t('instanceList.goSetupCluster') }}
      </Button>
      <p class="text-xs text-muted-foreground pt-2">
        {{ t('instanceList.alreadySetup') }}
        <Button variant="unstyled" size="unstyled" class="text-primary hover:underline ml-1" @click="clusterStore.fetchClusters()">
          {{ t('instanceList.refresh') }}
        </Button>
      </p>
    </div>

    <!-- Empty state: has cluster + no instances -->
    <div
      v-else-if="instances.length === 0"
      class="text-center py-20 space-y-4"
    >
      <div class="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto">
        <Server class="w-8 h-8 text-primary" />
      </div>
      <h3 class="text-lg font-semibold">{{ t('instanceList.emptyTitle') }}</h3>
      <p class="text-sm text-muted-foreground max-w-sm mx-auto">
        {{ t('instanceList.emptyDescription') }}
      </p>
      <Button variant="unstyled" size="unstyled"
        class="mt-4 px-6 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="router.push('/instances/create')"
      >
        {{ t('instanceList.createFirst') }}
      </Button>
    </div>

    <!-- Instance table -->
    <div v-else class="rounded-xl border border-border overflow-hidden">
      <Table class="w-full text-sm">
        <TableHeader>
          <TableRow class="border-b border-border bg-card/60">
            <TableHead class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableName') }}</TableHead>
            <TableHead class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableStatus') }}</TableHead>
            <TableHead class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableImageVersion') }}</TableHead>
            <TableHead class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceList.tableCreatedAt') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="inst in sortedInstances"
            :key="inst.id"
            class="border-b border-border last:border-b-0 hover:bg-accent/50 cursor-pointer transition-colors"
            @click="router.push(`/instances/${inst.id}`)"
          >
            <TableCell class="px-4 py-3 font-medium">
              {{ getInstanceDisplayName(inst) }}
            </TableCell>
            <TableCell class="px-4 py-3">
              <span class="inline-flex items-center gap-1.5">
                <span
                  class="w-2 h-2 rounded-full"
                  :class="[
                    getStatus(inst).bgColor,
                    getStatus(inst).pulse ? 'animate-pulse' : '',
                  ]"
                />
                <span :class="getStatus(inst).color">
                  {{ getStatusLabel(inst) }}
                </span>
              </span>
            </TableCell>
            <TableCell class="px-4 py-3 text-muted-foreground font-mono text-xs">{{ inst.image_version }}</TableCell>
            <TableCell class="px-4 py-3 text-muted-foreground">{{ formatTime(inst.created_at) }}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  </div>
</template>
