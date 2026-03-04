<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Plus, Loader2, Bot, Search, Rocket, RefreshCw, Check, AlertTriangle, X, ExternalLink } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import { useToast } from '@/composables/useToast'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'

interface MissingGene {
  id: string
  gene_id: string
  gene_name: string
  gene_slug: string
  gene_short_description: string | null
  gene_icon: string | null
  gene_category: string | null
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()
const toast = useToast()

const workspaceId = computed(() => route.params.id as string)
const targetHexQ = computed(() => route.query.hex_q != null ? Number(route.query.hex_q) : undefined)
const targetHexR = computed(() => route.query.hex_r != null ? Number(route.query.hex_r) : undefined)

interface InstanceItem {
  id: string
  name: string
  slug?: string
  status: string
}

const instances = ref<InstanceItem[]>([])
const loading = ref(false)
const adding = ref<string | null>(null)
const addingStep = ref(0)
const addingDone = ref<string | null>(null)
let stepTimer: ReturnType<typeof setInterval> | null = null
const search = ref('')

const geneDialogInstanceId = ref<string | null>(null)
const missingGenes = ref<MissingGene[]>([])
const genehubWebUrl = ref('')
const geneChecking = ref(false)

const ADDING_STEPS_WITH_GENE = computed(() => [
  t('addAgentView.stepInstallGenes'),
  t('addAgentView.stepConfiguring'),
  t('addAgentView.stepDeployPlugin'),
  t('addAgentView.stepRestarting'),
  t('addAgentView.stepConnecting'),
])

const ADDING_STEPS_NORMAL = computed(() => [
  t('addAgentView.stepConfiguring'),
  t('addAgentView.stepDeployPlugin'),
  t('addAgentView.stepRestarting'),
  t('addAgentView.stepConnecting'),
])

const currentSteps = ref<string[]>([])

const alreadyInWorkspace = computed(() =>
  new Set(store.currentWorkspace?.agents?.map((a) => a.instance_id) || []),
)

const filtered = computed(() =>
  instances.value.filter(
    (i) => !search.value || i.name.toLowerCase().includes(search.value.toLowerCase()),
  ),
)

const runningInstances = computed(() =>
  filtered.value.filter((i) => i.status === 'running' && !alreadyInWorkspace.value.has(i.id)),
)
const addedInstances = computed(() =>
  filtered.value.filter((i) => alreadyInWorkspace.value.has(i.id)),
)
const unavailableInstances = computed(() =>
  filtered.value.filter((i) => i.status !== 'running' && !alreadyInWorkspace.value.has(i.id)),
)

async function fetchInstances() {
  loading.value = true
  try {
    const res = await api.get('/instances')
    instances.value = (res.data.data || []).map((i: any) => ({
      id: i.id,
      name: i.name,
      slug: i.slug,
      status: i.status,
    }))
  } catch (e) {
    console.error('fetch instances error:', e)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await store.fetchMyPermissions(workspaceId.value)
  if (!store.hasPermission('manage_agents')) {
    toast.error(t('errors.common.forbidden'))
    router.replace(`/workspace/${workspaceId.value}`)
    return
  }
  fetchInstances()
})

function geneHubLink(slug: string): string {
  if (!genehubWebUrl.value) return ''
  return `${genehubWebUrl.value.replace(/\/$/, '')}/genes/${slug}`
}

async function addToWorkspace(instanceId: string) {
  geneChecking.value = true
  try {
    const res = await api.get(`/workspaces/${workspaceId.value}/check-agent-genes`, {
      params: { instance_id: instanceId },
    })
    const data = res.data.data
    genehubWebUrl.value = data.genehub_web_url || ''

    if (data.all_installed) {
      geneChecking.value = false
      await doAddAgent(instanceId, [])
      return
    }

    missingGenes.value = data.missing_genes || []
    geneDialogInstanceId.value = instanceId
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, t('addAgentView.geneCheckFailed')))
  } finally {
    geneChecking.value = false
  }
}

function closeGeneDialog() {
  geneDialogInstanceId.value = null
  missingGenes.value = []
}

async function confirmGeneInstall() {
  const instanceId = geneDialogInstanceId.value
  if (!instanceId) return
  const slugs = missingGenes.value.map(g => g.gene_slug)
  geneDialogInstanceId.value = null
  missingGenes.value = []
  await doAddAgent(instanceId, slugs)
}

async function doAddAgent(instanceId: string, installSlugs: string[]) {
  adding.value = instanceId
  addingStep.value = 0
  currentSteps.value = installSlugs.length > 0 ? ADDING_STEPS_WITH_GENE.value : ADDING_STEPS_NORMAL.value

  stepTimer = setInterval(() => {
    if (addingStep.value < currentSteps.value.length - 1) addingStep.value++
  }, 4000)

  try {
    await store.addAgent(
      workspaceId.value, instanceId, undefined,
      targetHexQ.value, targetHexR.value, installSlugs,
    )
    if (stepTimer) { clearInterval(stepTimer); stepTimer = null }
    adding.value = null
    addingDone.value = instanceId
    setTimeout(() => { addingDone.value = null }, 1500)
    await fetchInstances()
    toast.success(t('addAgentView.addedToast'), {
      action: {
        label: t('addAgentView.goToView'),
        onClick: () => router.push({
          path: `/workspace/${workspaceId.value}`,
          query: { focus_agent: instanceId },
        }),
      },
    })
  } catch (e: any) {
    if (stepTimer) { clearInterval(stepTimer); stepTimer = null }
    toast.error(resolveApiErrorMessage(e, t('addAgentView.addFailed')))
    adding.value = null
  }
}

function goBack() {
  router.push(`/workspace/${workspaceId.value}`)
}
</script>

<template>
  <div class="max-w-lg mx-auto px-6 py-8">
    <div class="flex items-center gap-3 mb-6">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="goBack">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h1 class="text-xl font-bold">{{ t('addAgentView.title') }}</h1>
    </div>

    <p class="text-sm text-muted-foreground mb-4">
      {{ t('addAgentView.subtitle') }}
    </p>

    <button
      class="w-full flex items-center gap-3 px-4 py-3 mb-4 rounded-lg border border-dashed border-primary/40 bg-primary/5 hover:bg-primary/10 transition-colors"
      @click="router.push(`/instances/create?workspace=${workspaceId}`)"
    >
      <Rocket class="w-5 h-5 text-primary" />
      <div class="text-left">
        <p class="text-sm font-medium">{{ t('addAgentView.createNew') }}</p>
        <p class="text-xs text-muted-foreground">{{ t('addAgentView.createNewDesc') }}</p>
      </div>
    </button>

    <div class="flex items-center gap-2 mb-4">
      <div class="relative flex-1">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          v-model="search"
          class="w-full pl-9 pr-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50"
          :placeholder="t('addAgentView.searchPlaceholder')"
        />
      </div>
      <button
        class="p-2 rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50"
        :disabled="loading"
        :title="t('addAgentView.refresh')"
        @click="fetchInstances"
      >
        <RefreshCw class="w-4 h-4" :class="loading ? 'animate-spin' : ''" />
      </button>
    </div>

    <div v-if="loading" class="flex justify-center py-10">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="filtered.length === 0" class="text-center py-10 text-muted-foreground text-sm">
      {{ t('addAgentView.noInstances') }}
    </div>

    <template v-else>
      <div v-if="runningInstances.length > 0" class="space-y-2">
        <div
          v-for="inst in runningInstances"
          :key="inst.id"
          class="flex items-center justify-between px-4 py-3 rounded-lg bg-card border border-border hover:border-primary/20 transition-colors"
        >
          <div class="flex items-center gap-3">
            <Bot class="w-5 h-5 text-primary" />
            <div>
              <div class="flex items-center gap-2">
                <p class="text-sm font-medium">{{ inst.name }}</p>
                <span v-if="inst.slug" class="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground leading-none">{{ inst.slug }}</span>
              </div>
              <p class="text-xs text-muted-foreground">{{ inst.status }}</p>
            </div>
          </div>

          <div v-if="adding === inst.id" class="flex items-center gap-2 min-w-[140px]">
            <div class="flex-1">
              <div class="flex items-center gap-1.5 mb-1">
                <Loader2 class="w-3 h-3 animate-spin text-primary" />
                <span class="text-xs text-muted-foreground">{{ currentSteps[addingStep] }}</span>
              </div>
              <div class="h-1 rounded-full bg-muted overflow-hidden">
                <div
                  class="h-full rounded-full bg-primary transition-all duration-700 ease-out"
                  :style="{ width: `${((addingStep + 1) / currentSteps.length) * 100}%` }"
                />
              </div>
            </div>
          </div>
          <span
            v-else-if="addingDone === inst.id"
            class="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-green-500/10 text-green-600 text-xs font-medium"
          >
            <Check class="w-3 h-3" />
            {{ t('addAgentView.added') }}
          </span>
          <div v-else-if="geneChecking && geneDialogInstanceId === null && adding === null" class="flex items-center gap-1.5">
            <Loader2 class="w-3 h-3 animate-spin text-muted-foreground" />
            <span class="text-xs text-muted-foreground">{{ t('addAgentView.stepInstallGenes') }}</span>
          </div>
          <button
            v-else
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
            :disabled="!!adding || geneChecking"
            @click="addToWorkspace(inst.id)"
          >
            <Plus class="w-3 h-3" />
            {{ t('addAgentView.addBtn') }}
          </button>
        </div>
      </div>

      <div v-if="addedInstances.length > 0" class="mt-6">
        <p class="text-xs text-muted-foreground mb-2">{{ t('addAgentView.alreadyInWorkspace') }}</p>
        <div class="space-y-2">
          <div
            v-for="inst in addedInstances"
            :key="inst.id"
            class="flex items-center justify-between px-4 py-3 rounded-lg bg-card border border-border opacity-60"
          >
            <div class="flex items-center gap-3">
              <Bot class="w-5 h-5 text-muted-foreground" />
              <div>
                <div class="flex items-center gap-2">
                  <p class="text-sm font-medium text-muted-foreground">{{ inst.name }}</p>
                  <span v-if="inst.slug" class="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground leading-none">{{ inst.slug }}</span>
                </div>
                <p class="text-xs text-muted-foreground">{{ inst.status }}</p>
              </div>
            </div>
            <span class="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs">
              <Check class="w-3 h-3" />
              {{ t('addAgentView.added') }}
            </span>
          </div>
        </div>
      </div>

      <div v-if="unavailableInstances.length > 0" class="mt-6">
        <p class="text-xs text-muted-foreground mb-2">{{ t('addAgentView.unavailableHint') }}</p>
        <div class="space-y-2 opacity-50">
          <div
            v-for="inst in unavailableInstances"
            :key="inst.id"
            class="flex items-center justify-between px-4 py-3 rounded-lg bg-card border border-border cursor-not-allowed"
          >
            <div class="flex items-center gap-3">
              <Bot class="w-5 h-5 text-muted-foreground" />
              <div>
                <div class="flex items-center gap-2">
                  <p class="text-sm font-medium text-muted-foreground">{{ inst.name }}</p>
                  <span v-if="inst.slug" class="px-1.5 py-0.5 rounded bg-muted text-[10px] font-mono text-muted-foreground leading-none">{{ inst.slug }}</span>
                </div>
                <p class="text-xs text-muted-foreground">{{ inst.status }}</p>
              </div>
            </div>
            <span class="px-3 py-1.5 rounded-lg bg-muted text-muted-foreground text-xs">
              {{ t('addAgentView.unavailable') }}
            </span>
          </div>
        </div>
      </div>
    </template>

    <!-- Missing Genes Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="geneDialogInstanceId"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          @click.self="closeGeneDialog"
        >
          <div class="bg-card border border-border rounded-xl shadow-lg max-w-md w-full mx-4">
            <div class="flex items-start gap-3 p-5 pb-3">
              <div class="shrink-0 w-10 h-10 rounded-full bg-amber-500/10 flex items-center justify-center">
                <AlertTriangle class="w-5 h-5 text-amber-500" />
              </div>
              <div class="flex-1 min-w-0">
                <h3 class="text-sm font-semibold mb-1">{{ t('addAgentView.geneDialogTitle') }}</h3>
                <p class="text-xs text-muted-foreground leading-relaxed">
                  {{ t('addAgentView.geneDialogBody', { count: missingGenes.length }) }}
                </p>
              </div>
              <button class="shrink-0 p-1 rounded-md hover:bg-muted transition-colors" @click="closeGeneDialog">
                <X class="w-4 h-4 text-muted-foreground" />
              </button>
            </div>

            <div class="px-5 pb-3 space-y-2 max-h-[240px] overflow-y-auto">
              <div
                v-for="gene in missingGenes"
                :key="gene.gene_id"
                class="flex items-center gap-3 p-3 rounded-lg border border-border"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium truncate">{{ gene.gene_name }}</span>
                    <span
                      v-if="gene.gene_category"
                      class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                    >{{ gene.gene_category }}</span>
                  </div>
                  <p v-if="gene.gene_short_description" class="text-xs text-muted-foreground mt-0.5 truncate">
                    {{ gene.gene_short_description }}
                  </p>
                </div>
                <a
                  v-if="geneHubLink(gene.gene_slug)"
                  :href="geneHubLink(gene.gene_slug)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                  :title="t('addAgentView.viewOnGeneHub')"
                >
                  <ExternalLink class="w-3.5 h-3.5" />
                </a>
              </div>
            </div>

            <div class="flex items-center gap-2 justify-end p-5 pt-3 border-t border-border">
              <button
                class="px-3 py-1.5 rounded-lg border border-border text-xs font-medium hover:bg-muted transition-colors"
                @click="closeGeneDialog"
              >
                {{ t('addAgentView.geneDialogCancel') }}
              </button>
              <button
                class="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
                @click="confirmGeneInstall"
              >
                {{ t('addAgentView.geneDialogConfirm') }}
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
