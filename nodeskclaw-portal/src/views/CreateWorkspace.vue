<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Plus, Loader2, Palette, Bot, ChevronLeft, Server, Container } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import type { WorkspaceTemplateItem } from '@/stores/workspace'
import { useClusterStore, type ClusterInfo } from '@/stores/cluster'
import { resolveApiErrorMessage } from '@/i18n/error'
import TemplateCard from '@/components/workspace/TemplateCard.vue'
import DeployFromTemplateDialog from '@/components/workspace/DeployFromTemplateDialog.vue'

const { t } = useI18n()
const router = useRouter()
const store = useWorkspaceStore()
const clusterStore = useClusterStore()

const step = ref(1)
const selectedTemplateId = ref<string | null>(null)
const selectedTemplateName = ref('')
const templates = ref<WorkspaceTemplateItem[]>([])
const loadingTemplates = ref(false)

const name = ref('')
const description = ref('')
const selectedColor = ref('#a78bfa')
const selectedClusterId = ref('')
const creating = ref(false)
const error = ref('')

const availableClusters = computed(() => clusterStore.clusters)
const clusterDropdownOpen = ref(false)
const selectedCluster = computed(() =>
  availableClusters.value.find(c => c.id === selectedClusterId.value) ?? null
)
const deployDialogOpen = ref(false)
const deployTemplateId = ref<string | null>(null)

const colors = [
  '#a78bfa', '#60a5fa', '#34d399', '#fbbf24',
  '#f87171', '#f472b6', '#38bdf8', '#a3e635',
]

onMounted(async () => {
  loadingTemplates.value = true
  try {
    await clusterStore.fetchClusters()
    if (availableClusters.value.length === 1) {
      selectedClusterId.value = availableClusters.value[0].id
    }
    templates.value = await store.fetchWorkspaceTemplates()
  } catch {
    // Silently fall back to blank-only
  } finally {
    loadingTemplates.value = false
  }
})

function selectCluster(cluster: ClusterInfo) {
  selectedClusterId.value = cluster.id
  clusterDropdownOpen.value = false
}

function selectBlank() {
  selectedTemplateId.value = null
  selectedTemplateName.value = ''
  step.value = 2
}

function selectTemplate(tpl: WorkspaceTemplateItem) {
  if (tpl.can_deploy_from_template) {
    deployTemplateId.value = tpl.id
    deployDialogOpen.value = true
    return
  }
  selectedTemplateId.value = tpl.id
  selectedTemplateName.value = tpl.name
  step.value = 2
}

function onDeployFromTemplateDone(workspaceId: string) {
  router.push(`/workspace/${workspaceId}`)
}

function goBackToTemplates() {
  step.value = 1
}

async function handleCreate() {
  if (!name.value.trim()) {
    error.value = t('createWorkspace.nameRequired')
    return
  }

  creating.value = true
  error.value = ''

  try {
    const payload: Record<string, unknown> = {
      name: name.value.trim(),
      description: description.value.trim(),
      color: selectedColor.value,
      cluster_id: selectedClusterId.value,
    }
    if (selectedTemplateId.value) {
      payload.template_id = selectedTemplateId.value
    }
    const ws = await store.createWorkspace(payload as any)
    router.push(`/workspace/${ws.id}`)
  } catch (e: any) {
    error.value = resolveApiErrorMessage(e, t('createWorkspace.createFailed'))
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-8">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="router.push('/')">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h1 class="text-xl font-bold">{{ t('createWorkspace.title') }}</h1>
    </div>

    <!-- Step 1: Template Selection -->
    <div v-if="step === 1" class="space-y-6">
      <p class="text-sm text-muted-foreground">{{ t('createWorkspace.chooseTemplate') }}</p>

      <div v-if="loadingTemplates" class="flex items-center justify-center py-12">
        <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
      </div>

      <div v-else class="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <TemplateCard :blank="true" @select="selectBlank" />
        <TemplateCard
          v-for="tpl in templates"
          :key="tpl.id"
          :template="tpl"
          @select="selectTemplate(tpl)"
        />
      </div>
    </div>

    <!-- Step 2: Basic Info -->
    <div v-else class="space-y-6">
      <button
        class="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        @click="goBackToTemplates"
      >
        <ChevronLeft class="w-4 h-4" />
        {{ t('createWorkspace.backToTemplates') }}
      </button>

      <div v-if="selectedTemplateName" class="text-sm text-muted-foreground">
        {{ t('createWorkspace.selectedTemplate') }}:
        <span class="font-medium text-foreground">{{ selectedTemplateName }}</span>
      </div>

      <div class="space-y-6 max-w-lg">
        <!-- Name -->
        <div class="space-y-2">
          <label class="text-sm font-medium">{{ t('createWorkspace.nameLabel') }}</label>
          <input
            v-model="name"
            class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50"
            :placeholder="t('createWorkspace.namePlaceholder')"
            maxlength="128"
          />
        </div>

        <!-- Cluster -->
        <div class="space-y-2">
          <label class="text-sm font-medium flex items-center gap-1.5">
            <Server class="w-4 h-4 text-muted-foreground" />
            {{ t('createWorkspace.clusterLabel') }}
          </label>

          <template v-if="availableClusters.length === 0">
            <div class="px-3 py-4 rounded-lg border border-dashed border-border bg-muted/50 text-center">
              <p class="text-sm text-muted-foreground">{{ t('createWorkspace.noCluster') }}</p>
              <button
                class="mt-2 text-sm text-primary hover:underline"
                @click="router.push('/settings/clusters')"
              >
                {{ t('createWorkspace.goConfigCluster') }}
              </button>
            </div>
          </template>

          <template v-else-if="availableClusters.length === 1">
            <div class="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted border border-border text-sm">
              <Container v-if="availableClusters[0].compute_provider === 'docker'" class="w-4 h-4 text-blue-500 shrink-0" />
              <Server v-else class="w-4 h-4 text-primary shrink-0" />
              <span>{{ availableClusters[0].name }}</span>
              <span class="text-xs text-muted-foreground">({{ availableClusters[0].compute_provider === 'docker' ? 'Docker' : 'K8s' }})</span>
            </div>
          </template>

          <template v-else>
            <div class="relative">
              <button
                class="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50"
                @click="clusterDropdownOpen = !clusterDropdownOpen"
              >
                <span v-if="selectedCluster" class="flex items-center gap-2">
                  <Container v-if="selectedCluster.compute_provider === 'docker'" class="w-4 h-4 text-blue-500 shrink-0" />
                  <Server v-else class="w-4 h-4 text-primary shrink-0" />
                  {{ selectedCluster.name }}
                  <span class="text-xs text-muted-foreground">({{ selectedCluster.compute_provider === 'docker' ? 'Docker' : 'K8s' }})</span>
                </span>
                <span v-else class="text-muted-foreground">{{ t('createWorkspace.clusterPlaceholder') }}</span>
              </button>
              <div v-if="clusterDropdownOpen" class="fixed inset-0 z-0" @click="clusterDropdownOpen = false" />
              <div
                v-if="clusterDropdownOpen"
                class="absolute z-10 mt-1 w-full rounded-lg border border-border bg-popover shadow-md"
              >
                <button
                  v-for="c in availableClusters"
                  :key="c.id"
                  class="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent transition-colors first:rounded-t-lg last:rounded-b-lg"
                  @click="selectCluster(c)"
                >
                  <Container v-if="c.compute_provider === 'docker'" class="w-4 h-4 text-blue-500 shrink-0" />
                  <Server v-else class="w-4 h-4 text-primary shrink-0" />
                  <span>{{ c.name }}</span>
                  <span class="text-xs text-muted-foreground">({{ c.compute_provider === 'docker' ? 'Docker' : 'K8s' }})</span>
                </button>
              </div>
            </div>
          </template>
        </div>

        <!-- Description -->
        <div class="space-y-2">
          <label class="text-sm font-medium">{{ t('createWorkspace.descriptionLabel') }}</label>
          <textarea
            v-model="description"
            rows="3"
            class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50 resize-none"
            :placeholder="t('createWorkspace.descriptionPlaceholder')"
          />
        </div>

        <!-- Color -->
        <div class="space-y-2">
          <label class="text-sm font-medium flex items-center gap-1.5">
            <Palette class="w-4 h-4 text-muted-foreground" />
            {{ t('createWorkspace.themeColor') }}
          </label>
          <div class="flex gap-2">
            <button
              v-for="c in colors"
              :key="c"
              class="w-8 h-8 rounded-full border-2 transition-all"
              :class="selectedColor === c ? 'border-white scale-110' : 'border-transparent hover:scale-105'"
              :style="{ backgroundColor: c }"
              @click="selectedColor = c"
            />
          </div>
        </div>

        <!-- Preview -->
        <div class="rounded-xl border border-border p-4 bg-card">
          <div class="flex items-center gap-3">
            <div
              class="w-10 h-10 rounded-lg flex items-center justify-center text-lg"
              :style="{ backgroundColor: selectedColor + '22', color: selectedColor }"
            >
              <Bot class="w-5 h-5" />
            </div>
            <div>
              <h3 class="font-semibold text-sm">{{ name || t('createWorkspace.previewNameFallback') }}</h3>
              <p class="text-xs text-muted-foreground">{{ description || t('createWorkspace.previewDescFallback') }}</p>
            </div>
          </div>
        </div>

        <!-- Error -->
        <p v-if="error" class="text-sm text-red-400">{{ error }}</p>

        <!-- Submit -->
        <button
          class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          :disabled="creating || !name.trim() || !selectedClusterId"
          @click="handleCreate"
        >
          <Loader2 v-if="creating" class="w-4 h-4 animate-spin" />
          <Plus v-else class="w-4 h-4" />
          {{ t('createWorkspace.submit') }}
        </button>
      </div>
    </div>

    <DeployFromTemplateDialog
      v-model:open="deployDialogOpen"
      :template-id="deployTemplateId"
      @done="onDeployFromTemplateDone"
    />
  </div>
</template>
