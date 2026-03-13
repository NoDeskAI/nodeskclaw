<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, inject, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import {
  Loader2, Package, Download, Trash2, Upload, Sparkles, X,
  AlertTriangle, RefreshCw, Zap, FileText, Save,
} from 'lucide-vue-next'
import { useGeneStore } from '@/stores/gene'
import type { InstanceSkillItem, InstanceGeneItem } from '@/stores/gene'
import { useToast } from '@/composables/useToast'
import { useI18n } from 'vue-i18n'
import GeneMarketDialog from '@/components/gene/GeneMarketDialog.vue'
import api from '@/services/api'
import { renderMarkdown } from '@/utils/markdown'

const { t } = useI18n()
const route = useRoute()
const toast = useToast()
const instanceId = inject<ComputedRef<string>>('instanceId')!
const store = useGeneStore()

const initialLoading = ref(true)
const loadError = ref('')
const instanceSkills = computed(() => store.instanceSkills)
const marketDialogOpen = ref(false)

const installedSkillNames = computed(() =>
  new Set(instanceSkills.value.map(s => s.skill_name)),
)

const focusGeneId = computed(() => {
  const value = route.query.focus_gene_id
  return typeof value === 'string' ? value : ''
})

const displayedSkills = computed(() => {
  const list = instanceSkills.value
  const targetGeneId = focusGeneId.value
  if (!targetGeneId) return list
  const targetItem = list.find(item => item.instance_gene?.gene_id === targetGeneId)
  if (!targetItem) return list
  if (list[0]?.skill_name === targetItem.skill_name) return list
  return [targetItem, ...list.filter(item => item.skill_name !== targetItem.skill_name)]
})

const createDialogOpen = ref(false)
const createPrompt = ref('')
const creating = ref(false)

const saveTemplateOpen = ref(false)
const templateName = ref('')
const templateSlug = ref('')
const templateDesc = ref('')
const savingTemplate = ref(false)

const hasInstalledGenes = computed(() =>
  instanceSkills.value.some(s => s.instance_gene?.status === 'installed' || s.type === 'hub'),
)

async function handleSaveTemplate() {
  if (!templateName.value.trim() || !templateSlug.value.trim()) return
  savingTemplate.value = true
  try {
    await store.createTemplateFromInstance(instanceId.value, {
      name: templateName.value.trim(),
      slug: templateSlug.value.trim(),
      description: templateDesc.value || undefined,
    })
    toast.success(t('template.saved'))
    saveTemplateOpen.value = false
    templateName.value = ''
    templateSlug.value = ''
    templateDesc.value = ''
  } catch {
    toast.error(t('template.saveFailed'))
  } finally {
    savingTemplate.value = false
  }
}

const forgetTarget = ref<InstanceSkillItem | null>(null)
const confirmInput = ref('')
const forgetting = ref(false)

const isConfirmed = computed(() => {
  if (!forgetTarget.value) return false
  return confirmInput.value === forgetTarget.value.name
})

const emergedDetail = ref<InstanceSkillItem | null>(null)

const statusBadgeClass: Record<string, string> = {
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
  return statusBadgeClass[status] ?? 'bg-gray-500/10 text-gray-500'
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

const busyStatuses = new Set(['uninstalling', 'forgetting', 'installing', 'learning'])

const TRANSITIONAL_STATUSES = new Set(['learning', 'installing', 'forgetting', 'uninstalling'])
const hasTransitionalSkills = computed(() =>
  instanceSkills.value.some(s => s.instance_gene && TRANSITIONAL_STATUSES.has(s.instance_gene.status)),
)

let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    try {
      const res = await api.get(`/instances/${instanceId.value}/skills`)
      store.instanceSkills = res.data.data || []
    } catch { /* ignore */ }
    if (!hasTransitionalSkills.value) stopPolling()
  }, 8000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

watch(hasTransitionalSkills, (has) => {
  if (has) startPolling()
  else stopPolling()
})

function openMarketDialog() {
  marketDialogOpen.value = true
}

async function onGeneInstalled() {
  try {
    await store.fetchInstanceSkills(instanceId.value)
  } catch { /* ignore */ }
}

function openForgetDialog(item: InstanceSkillItem) {
  forgetTarget.value = item
  confirmInput.value = ''
}

async function confirmForget() {
  if (!forgetTarget.value || !isConfirmed.value) return
  const ig = forgetTarget.value.instance_gene
  if (!ig) return
  forgetting.value = true
  try {
    await store.uninstallGene(instanceId.value, ig.gene_id)
    forgetTarget.value = null
    await store.fetchInstanceSkills(instanceId.value)
    toast.success(t('instanceGenes.forgetSubmitted'))
  } catch {
    toast.error(t('instanceGenes.forgetFailed'))
  } finally {
    forgetting.value = false
  }
}

async function handleRelearn(item: InstanceSkillItem) {
  if (!item.gene?.slug) return
  try {
    await store.installGene(instanceId.value, item.gene.slug)
    await store.fetchInstanceSkills(instanceId.value)
    toast.success(t('instanceGenes.relearnSubmitted'))
  } catch {
    toast.error(t('instanceGenes.relearnFailed'))
  }
}

async function handlePublishVariant(item: InstanceSkillItem) {
  const ig = item.instance_gene
  if (!ig) return
  try {
    await store.publishVariant(instanceId.value, ig.gene_id)
    await store.fetchInstanceSkills(instanceId.value)
    toast.success(t('instanceGenes.variantPublished'))
  } catch {
    toast.error(t('instanceGenes.publishFailed'))
  }
}

function openCreateDialog() {
  createDialogOpen.value = true
  createPrompt.value = ''
}

async function handleCreate() {
  creating.value = true
  try {
    await store.triggerCreation(instanceId.value, createPrompt.value || undefined)
    createDialogOpen.value = false
    await store.fetchInstanceSkills(instanceId.value)
    toast.success(t('instanceGenes.createSubmitted'))
  } catch {
    toast.error(t('instanceGenes.createFailed'))
  } finally {
    creating.value = false
  }
}

function renderMd(src: string): string {
  return renderMarkdown(src)
}

onMounted(async () => {
  try {
    await store.fetchInstanceSkills(instanceId.value)
    loadError.value = ''
  } catch {
    loadError.value = t('instanceGenes.podUnavailable')
  } finally {
    initialLoading.value = false
  }
})

onUnmounted(stopPolling)
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold">{{ t('instanceGenes.title') }}</h2>
      <div class="flex items-center gap-2">
        <button
          v-if="hasInstalledGenes"
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border border-border hover:bg-muted/50 transition-colors"
          @click="saveTemplateOpen = true"
        >
          <Save class="w-4 h-4" />
          {{ t('template.saveAsTemplate') }}
        </button>
        <button
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          @click="openMarketDialog"
        >
          <Download class="w-4 h-4" />
          {{ t('instanceGenes.learnGene') }}
        </button>
        <button
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border border-border hover:bg-muted/50 transition-colors"
          @click="openCreateDialog"
        >
          <Sparkles class="w-4 h-4" />
          {{ t('instanceGenes.createGene') }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="initialLoading" class="flex items-center justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
    </div>

    <!-- Pod unavailable -->
    <div v-else-if="loadError" class="rounded-xl border border-dashed border-destructive/30 py-16 text-center text-muted-foreground">
      <AlertTriangle class="w-12 h-12 mx-auto mb-4 text-destructive/50" />
      <p class="text-sm">{{ loadError }}</p>
    </div>

    <!-- Empty -->
    <div v-else-if="instanceSkills.length === 0" class="rounded-xl border border-dashed border-border py-16 text-center text-muted-foreground">
      <Package class="w-12 h-12 mx-auto mb-4 opacity-50" />
      <p class="text-sm">{{ t('instanceGenes.empty') }}</p>
      <button
        class="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        @click="openMarketDialog"
      >
        <Download class="w-4 h-4" />
        {{ t('instanceGenes.learnGene') }}
      </button>
    </div>

    <!-- Skills list -->
    <div v-else class="space-y-3">
      <div
        v-for="item in displayedSkills"
        :key="item.skill_name"
        class="rounded-xl border border-border bg-card p-4 hover:border-primary/30 transition-colors"
        :class="{ 'cursor-pointer': item.type === 'emerged' }"
        @click="item.type === 'emerged' ? (emergedDetail = item) : undefined"
      >
        <!-- Hub gene card -->
        <div v-if="item.type === 'hub'" class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="min-w-0 flex-1 truncate font-medium">{{ item.gene?.name ?? item.name }}</span>
                <span
                  v-if="item.instance_gene?.installed_version || item.gene?.version"
                  class="shrink-0 text-xs text-muted-foreground"
                >
                  v{{ item.instance_gene?.installed_version ?? item.gene?.version ?? '-' }}
                </span>
                <span v-else class="shrink-0 px-2 py-0.5 rounded text-xs font-medium bg-green-500/10 text-green-500">
                  {{ t('instanceGenes.statusInstalled') }}
                </span>
              </div>
              <span class="mt-1 block truncate text-xs text-muted-foreground">{{ item.gene?.slug ?? item.skill_name }}</span>
            </div>
            <div v-if="item.gene?.tags?.length" class="flex flex-wrap gap-1 mt-2">
              <span
                v-for="tag in item.gene.tags"
                :key="tag"
                class="px-2 py-0.5 rounded bg-muted text-xs text-muted-foreground"
              >
                {{ tag }}
              </span>
            </div>
            <div class="mt-3 flex items-center gap-4">
              <div class="flex-1 max-w-[200px]">
                <div class="flex justify-between text-xs text-muted-foreground mb-1">
                  <span>{{ t('instanceGenes.effectiveness') }}</span>
                  <span>{{ Math.round(effectivenessScore(item) * 100) }}%</span>
                </div>
                <div class="h-1.5 rounded-full bg-muted overflow-hidden">
                  <div
                    class="h-full rounded-full bg-primary transition-all"
                    :style="{ width: `${Math.min(100, effectivenessScore(item) * 100)}%` }"
                  />
                </div>
              </div>
              <span v-if="item.instance_gene" class="text-sm text-muted-foreground">
                {{ t('instanceGenes.usageCount', { count: item.instance_gene.usage_count }) }}
              </span>
            </div>
          </div>
          <div v-if="item.instance_gene" class="flex items-center gap-2 shrink-0">
            <button
              v-if="item.instance_gene.learning_output && !item.instance_gene.variant_published && item.instance_gene.status === 'installed'"
              class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border border-border hover:bg-muted/50 transition-colors"
              @click.stop="handlePublishVariant(item)"
            >
              <Upload class="w-3.5 h-3.5" />
              {{ t('instanceGenes.publishVariant') }}
            </button>
            <button
              v-if="item.instance_gene.status === 'simplified'"
              class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs border border-border hover:bg-muted/50 transition-colors"
              @click.stop="handleRelearn(item)"
            >
              <RefreshCw class="w-3.5 h-3.5" />
              {{ t('instanceGenes.relearn') }}
            </button>
            <span
              class="px-2 py-0.5 rounded text-xs font-medium shrink-0"
              :class="getStatusClass(item.instance_gene.status)"
            >
              {{ getStatusLabel(item.instance_gene.status) }}
            </span>
            <button
              v-if="!busyStatuses.has(item.instance_gene.status)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-destructive border border-destructive/30 hover:bg-destructive/10 transition-colors"
              @click.stop="openForgetDialog(item)"
            >
              <Trash2 class="w-3.5 h-3.5" />
              {{ item.instance_gene.status === 'simplified' ? t('instanceGenes.forgetFull') : t('instanceGenes.forget') }}
            </button>
          </div>
        </div>

        <!-- Emerged gene card -->
        <div v-else class="flex items-start justify-between gap-4">
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-medium">{{ item.name }}</span>
              <span class="text-xs text-muted-foreground">{{ item.skill_name }}</span>
              <span class="px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-500">
                <Zap class="w-3 h-3 inline -mt-0.5 mr-0.5" />{{ t('instanceGenes.emerged') }}
              </span>
            </div>
            <p v-if="item.description" class="mt-1.5 text-sm text-muted-foreground line-clamp-2">
              {{ item.description }}
            </p>
            <div class="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
              <span class="inline-flex items-center gap-1">
                <FileText class="w-3.5 h-3.5" />
                {{ t('instanceGenes.fileCount', { count: item.file_count }) }}
              </span>
              <span v-if="item.frontmatter?.always" class="inline-flex items-center gap-1 text-amber-500">
                <Zap class="w-3.5 h-3.5" />
                {{ t('instanceGenes.alwaysActive') }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Emerged Gene Detail Dialog -->
    <Teleport to="body">
      <div
        v-if="emergedDetail"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="emergedDetail = null"
      >
        <div class="bg-card rounded-xl border border-border shadow-xl w-full max-w-2xl mx-4 max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-6 pb-4 border-b border-border shrink-0">
            <div>
              <div class="flex items-center gap-2">
                <h3 class="text-lg font-semibold">{{ emergedDetail.name }}</h3>
                <span class="px-2 py-0.5 rounded text-xs font-medium bg-violet-500/10 text-violet-500">
                  <Zap class="w-3 h-3 inline -mt-0.5 mr-0.5" />{{ t('instanceGenes.emerged') }}
                </span>
              </div>
              <p v-if="emergedDetail.description" class="text-sm text-muted-foreground mt-1">{{ emergedDetail.description }}</p>
            </div>
            <button class="text-muted-foreground hover:text-foreground shrink-0" @click="emergedDetail = null">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="p-6 overflow-y-auto flex-1">
            <div class="flex items-center gap-4 text-sm text-muted-foreground mb-4">
              <span class="inline-flex items-center gap-1">
                <FileText class="w-4 h-4" />
                {{ t('instanceGenes.fileCount', { count: emergedDetail.file_count }) }}
              </span>
              <span v-if="emergedDetail.frontmatter?.always" class="inline-flex items-center gap-1 text-amber-500">
                <Zap class="w-4 h-4" />
                {{ t('instanceGenes.alwaysActive') }}
              </span>
            </div>
            <div v-if="emergedDetail.full_content" class="border border-border rounded-lg p-4">
              <h4 class="text-sm font-medium mb-3">{{ t('instanceGenes.skillContent') }}</h4>
              <div
                class="prose prose-sm dark:prose-invert max-w-none"
                v-html="renderMd(emergedDetail.full_content)"
              />
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Forget Confirmation Dialog -->
    <Teleport to="body">
      <div
        v-if="forgetTarget"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="forgetTarget = null"
      >
        <div class="bg-card rounded-xl border border-border shadow-xl w-full max-w-md mx-4 p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold">{{ t('instanceGenes.forgetConfirmTitle') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="forgetTarget = null">
              <X class="w-5 h-5" />
            </button>
          </div>

          <div class="rounded-lg border border-border bg-muted/30 p-3 mb-4">
            <div class="flex items-center gap-2 mb-1">
              <span class="font-medium text-sm">{{ forgetTarget.name }}</span>
              <span class="text-xs text-muted-foreground">{{ forgetTarget.skill_name }}</span>
            </div>
            <p v-if="forgetTarget.description" class="text-xs text-muted-foreground line-clamp-2">
              {{ forgetTarget.description }}
            </p>
          </div>

          <div class="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 mb-4">
            <div class="flex items-start gap-2">
              <AlertTriangle class="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
              <div class="text-xs text-muted-foreground space-y-1">
                <p>{{ t('instanceGenes.forgetWarning1') }}</p>
                <p>{{ t('instanceGenes.forgetWarning2') }}</p>
                <p>{{ t('instanceGenes.forgetWarning3') }}</p>
              </div>
            </div>
          </div>

          <div class="mb-4">
            <label class="block text-sm text-muted-foreground mb-2">
              {{ t('instanceGenes.forgetInputLabel') }}
              <span class="font-medium text-foreground">{{ forgetTarget.name }}</span>
              {{ t('instanceGenes.forgetInputSuffix') }}
            </label>
            <input
              v-model="confirmInput"
              class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-destructive/50"
              :placeholder="forgetTarget.name"
            />
          </div>

          <div class="flex justify-end gap-2">
            <button
              class="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted/50"
              @click="forgetTarget = null"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-4 py-2 rounded-lg text-sm bg-destructive text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
              :disabled="!isConfirmed || forgetting"
              @click="confirmForget"
            >
              <Loader2 v-if="forgetting" class="w-4 h-4 animate-spin inline mr-1" />
              {{ t('instanceGenes.forgetConfirmBtn') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Create Gene Dialog -->
    <Teleport to="body">
      <div
        v-if="createDialogOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="createDialogOpen = false"
      >
        <div class="bg-card rounded-xl border border-border shadow-xl w-full max-w-md mx-4 p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold">{{ t('instanceGenes.createGene') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="createDialogOpen = false">
              <X class="w-5 h-5" />
            </button>
          </div>
          <p class="text-sm text-muted-foreground mb-4">{{ t('instanceGenes.createDesc') }}</p>
          <textarea
            v-model="createPrompt"
            class="w-full h-24 px-3 py-2 rounded-lg border border-border bg-background text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
            :placeholder="t('instanceGenes.createPlaceholder')"
          />
          <div class="flex justify-end gap-2 mt-4">
            <button
              class="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted/50"
              @click="createDialogOpen = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              :disabled="creating"
              @click="handleCreate"
            >
              <Loader2 v-if="creating" class="w-4 h-4 animate-spin inline mr-1" />
              {{ t('common.submit') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Save as Template Dialog -->
    <Teleport to="body">
      <div
        v-if="saveTemplateOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="saveTemplateOpen = false"
      >
        <div class="bg-card rounded-xl border border-border shadow-xl w-full max-w-md mx-4 p-6">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold">{{ t('template.saveAsTemplate') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="saveTemplateOpen = false">
              <X class="w-5 h-5" />
            </button>
          </div>
          <p class="text-sm text-muted-foreground mb-4">{{ t('template.saveDesc') }}</p>
          <div class="space-y-3">
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('template.nameLabel') }}</label>
              <input
                v-model="templateName"
                type="text"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                :placeholder="t('template.namePlaceholder')"
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('template.slugLabel') }}</label>
              <input
                v-model="templateSlug"
                type="text"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/50"
                :placeholder="t('template.slugPlaceholder')"
              />
            </div>
            <div>
              <label class="block text-sm font-medium mb-1">{{ t('template.descLabel') }}</label>
              <textarea
                v-model="templateDesc"
                class="w-full h-20 px-3 py-2 rounded-lg border border-border bg-background text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
                :placeholder="t('template.descPlaceholder')"
              />
            </div>
          </div>
          <div class="flex justify-end gap-2 mt-4">
            <button
              class="px-4 py-2 rounded-lg text-sm border border-border hover:bg-muted/50"
              @click="saveTemplateOpen = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              :disabled="savingTemplate || !templateName.trim() || !templateSlug.trim()"
              @click="handleSaveTemplate"
            >
              <Loader2 v-if="savingTemplate" class="w-4 h-4 animate-spin inline mr-1" />
              {{ t('common.save') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <GeneMarketDialog
      v-model="marketDialogOpen"
      :instance-id="instanceId"
      :installed-skill-names="installedSkillNames"
      @installed="onGeneInstalled"
    />
  </div>
</template>
