<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useClusterStore, type ClusterInfo } from '@/stores/cluster'
import { useFeature } from '@/composables/useFeature'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { resolveApiErrorMessage } from '@/i18n/error'
import {
  Server,
  Container,
  Plus,
  Loader2,
  Plug,
  Pencil,
  Trash2,
  X,
  ChevronRight,
  ArrowRight,
} from 'lucide-vue-next'

const { t } = useI18n()
const router = useRouter()
const clusterStore = useClusterStore()
const toast = useToast()
const { confirm } = useConfirm()
const { isEnabled: isMultiCluster } = useFeature('multi_cluster')

const loading = ref(true)
const testingId = ref<string | null>(null)
const addingDocker = ref(false)

const showAddDialog = ref(false)
const addForm = ref({ name: '', kubeconfig: '' })
const adding = ref(false)
const nameAutoFilled = ref(false)

const hasDocker = computed(() => clusterStore.clusters.some(c => c.compute_provider === 'docker'))
const hasK8s = computed(() => clusterStore.clusters.some(c => c.compute_provider === 'k8s'))

const showRenameDialog = ref(false)
const renameForm = ref({ id: '', name: '' })
const renaming = ref(false)

const showKubeconfigDialog = ref(false)
const kubeconfigForm = ref({ id: '', kubeconfig: '' })
const updatingKubeconfig = ref(false)

type DisplayMode = 'setup' | 'single' | 'list'

const displayMode = computed<DisplayMode>(() => {
  if (isMultiCluster.value) return 'list'
  if (clusterStore.clusters.length > 1) return 'list'
  if (clusterStore.clusters.length === 1) return 'single'
  return 'setup'
})

const canAddCluster = computed(() => isMultiCluster.value || clusterStore.clusters.length === 0)

const singleCluster = computed(() => clusterStore.clusters[0] ?? null)

function parseKubeConfigMeta(yaml: string): string {
  const ctxMatch = yaml.match(/current-context:\s*(.+)/)
  if (ctxMatch) return ctxMatch[1].trim()
  const nameMatch = yaml.match(/- name:\s*(.+)/)
  if (nameMatch) return nameMatch[1].trim()
  return ''
}

watch(() => addForm.value.kubeconfig, (val) => {
  if (!val || addForm.value.name) return
  const parsed = parseKubeConfigMeta(val)
  if (parsed) {
    addForm.value.name = parsed
    nameAutoFilled.value = true
  }
})

onMounted(async () => {
  await clusterStore.fetchClusters()
  loading.value = false
})

async function handleAdd() {
  if (!addForm.value.kubeconfig.trim() || !addForm.value.name.trim()) return
  adding.value = true
  try {
    await clusterStore.createCluster({
      name: addForm.value.name.trim(),
      kubeconfig: addForm.value.kubeconfig.trim(),
    })
    toast.success(t('clusters.addSuccess'))
    showAddDialog.value = false
    addForm.value = { name: '', kubeconfig: '' }
    nameAutoFilled.value = false
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('clusters.addFailed')))
  } finally {
    adding.value = false
  }
}

async function handleTest(id: string) {
  testingId.value = id
  try {
    const result = await clusterStore.testConnection(id)
    if (result.ok) {
      toast.success(t('clusters.testSuccess', { version: result.version ?? '' }))
    } else {
      toast.error(t('clusters.testFailed', { message: result.message ?? '' }))
    }
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('clusters.testFailed', { message: '' })))
  } finally {
    testingId.value = null
  }
}

function openRename(cluster: ClusterInfo) {
  renameForm.value = { id: cluster.id, name: cluster.name }
  showRenameDialog.value = true
}

async function handleRename() {
  if (!renameForm.value.name.trim()) return
  renaming.value = true
  try {
    await clusterStore.updateCluster(renameForm.value.id, { name: renameForm.value.name.trim() })
    toast.success(t('clusters.renameSuccess'))
    showRenameDialog.value = false
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('clusters.renameFailed')))
  } finally {
    renaming.value = false
  }
}

async function handleDelete(cluster: ClusterInfo) {
  const ok = await confirm({
    title: t('clusters.deleteTitle'),
    description: t('clusters.deleteConfirm', { name: cluster.name }),
    variant: 'danger',
  })
  if (!ok) return
  try {
    await clusterStore.deleteCluster(cluster.id)
    toast.success(t('clusters.deleteSuccess'))
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('clusters.deleteFailed')))
  }
}

function openKubeconfigUpdate(cluster: ClusterInfo) {
  kubeconfigForm.value = { id: cluster.id, kubeconfig: '' }
  showKubeconfigDialog.value = true
}

async function handleKubeconfigUpdate() {
  if (!kubeconfigForm.value.kubeconfig.trim()) return
  updatingKubeconfig.value = true
  try {
    await clusterStore.updateKubeconfig(kubeconfigForm.value.id, kubeconfigForm.value.kubeconfig.trim())
    toast.success(t('clusters.kubeconfigUpdateSuccess'))
    showKubeconfigDialog.value = false
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('clusters.kubeconfigUpdateFailed')))
  } finally {
    updatingKubeconfig.value = false
  }
}

async function handleAddDocker() {
  addingDocker.value = true
  try {
    await clusterStore.createDockerCluster()
    toast.success(t('clusters.dockerAddSuccess'))
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('clusters.dockerAddFailed')))
  } finally {
    addingDocker.value = false
  }
}

function goToDetail(id: string) {
  router.push({ name: 'ClusterDetail', params: { id } })
}

function isDockerCluster(cluster: ClusterInfo) {
  return cluster.compute_provider === 'docker'
}

function statusDotClass(status: string) {
  if (status === 'connected') return 'bg-green-500'
  if (status === 'connecting') return 'bg-yellow-500 animate-pulse'
  return 'bg-red-500'
}
</script>

<template>
  <div>
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-base font-semibold">{{ t('clusters.title') }}</h2>
        <p class="text-sm text-muted-foreground mt-0.5">{{ t('clusters.subtitle') }}</p>
      </div>
      <div v-if="canAddCluster && displayMode !== 'setup'" class="flex items-center gap-2">
        <button
          v-if="!hasDocker"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          @click="showAddDialog = true"
        >
          <Plus class="w-4 h-4" />
          {{ t('clusters.addK8sCluster') }}
        </button>
        <button
          v-if="!hasK8s"
          class="flex items-center gap-1.5 px-4 py-2 rounded-lg border border-border text-sm font-medium hover:bg-accent transition-colors disabled:opacity-50"
          :disabled="addingDocker"
          @click="handleAddDocker"
        >
          <Loader2 v-if="addingDocker" class="w-4 h-4 animate-spin" />
          <Container v-else class="w-4 h-4" />
          {{ t('clusters.addDockerRuntime') }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Setup Wizard (0 clusters) -->
    <template v-else-if="displayMode === 'setup'">
      <div class="space-y-4">
        <!-- Docker Runtime Option -->
        <div class="p-6 rounded-xl border border-border bg-card space-y-4">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <Container class="w-5 h-5 text-blue-500" />
            </div>
            <div class="flex-1">
              <h3 class="font-semibold">{{ t('clusters.dockerSetupTitle') }}</h3>
              <p class="text-sm text-muted-foreground">{{ t('clusters.dockerSetupDesc') }}</p>
            </div>
            <button
              class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="addingDocker"
              @click="handleAddDocker"
            >
              <Loader2 v-if="addingDocker" class="w-4 h-4 animate-spin" />
              <ArrowRight v-else class="w-4 h-4" />
              {{ t('clusters.dockerSetupSubmit') }}
            </button>
          </div>
        </div>

        <div class="flex items-center gap-3 px-2">
          <div class="flex-1 border-t border-border" />
          <span class="text-xs text-muted-foreground">{{ t('common.or') }}</span>
          <div class="flex-1 border-t border-border" />
        </div>

        <!-- K8s Cluster Option -->
        <div class="p-6 rounded-xl border border-border bg-card space-y-5">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center">
              <Server class="w-5 h-5 text-primary" />
            </div>
            <div>
              <h3 class="font-semibold">{{ t('clusters.setupTitle') }}</h3>
              <p class="text-sm text-muted-foreground">{{ t('clusters.setupDesc') }}</p>
            </div>
          </div>

          <div class="space-y-3">
            <div>
              <label class="block text-sm text-muted-foreground mb-1">KubeConfig</label>
              <textarea
                v-model="addForm.kubeconfig"
                rows="8"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                :placeholder="t('clusters.kubeconfigPlaceholder')"
              />
            </div>
            <div>
              <label class="block text-sm text-muted-foreground mb-1">{{ t('clusters.clusterName') }}</label>
              <input
                v-model="addForm.name"
                type="text"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                :placeholder="t('clusters.namePlaceholder')"
              />
              <p v-if="nameAutoFilled" class="text-xs text-muted-foreground mt-1">{{ t('clusters.nameAutoFilled') }}</p>
            </div>
          </div>

          <div class="flex justify-end">
            <button
              class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!addForm.kubeconfig.trim() || !addForm.name.trim() || adding"
              @click="handleAdd"
            >
              <Loader2 v-if="adding" class="w-4 h-4 animate-spin" />
              <ArrowRight v-else class="w-4 h-4" />
              {{ t('clusters.setupSubmit') }}
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Single Cluster Card -->
    <template v-else-if="displayMode === 'single' && singleCluster">
      <div class="p-5 rounded-xl border border-border bg-card space-y-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-lg flex items-center justify-center" :class="isDockerCluster(singleCluster) ? 'bg-blue-500/10' : 'bg-primary/10'">
              <Container v-if="isDockerCluster(singleCluster)" class="w-5 h-5 text-blue-500" />
              <Server v-else class="w-5 h-5 text-primary" />
            </div>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-semibold">{{ singleCluster.name }}</span>
                <span class="w-2 h-2 rounded-full" :class="statusDotClass(singleCluster.status)" />
                <span class="text-xs text-muted-foreground">{{ t(`clusters.status.${singleCluster.status}`) }}</span>
              </div>
              <p v-if="isDockerCluster(singleCluster)" class="text-xs text-muted-foreground mt-0.5">{{ t('clusters.dockerRuntimeLabel') }}</p>
              <p v-else class="text-xs text-muted-foreground mt-0.5">{{ singleCluster.api_server_url || '-' }}</p>
            </div>
          </div>
        </div>

        <div v-if="!isDockerCluster(singleCluster)" class="flex items-center gap-4 text-xs text-muted-foreground">
          <span v-if="singleCluster.k8s_version">K8s {{ singleCluster.k8s_version }}</span>
          <span>{{ t(`clusters.provider.${singleCluster.provider}`) }}</span>
          <span>{{ t(`clusters.authType.${singleCluster.auth_type}`) }}</span>
        </div>

        <div class="flex items-center gap-2 pt-1">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm hover:bg-accent transition-colors disabled:opacity-50"
            :disabled="testingId === singleCluster.id"
            @click="handleTest(singleCluster.id)"
          >
            <Loader2 v-if="testingId === singleCluster.id" class="w-3.5 h-3.5 animate-spin" />
            <Plug v-else class="w-3.5 h-3.5" />
            {{ t('clusters.testConnection') }}
          </button>
          <template v-if="!isDockerCluster(singleCluster)">
            <button
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="openKubeconfigUpdate(singleCluster)"
            >
              {{ t('clusters.updateKubeconfig') }}
            </button>
          </template>
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-sm text-red-400 hover:bg-red-500/10 transition-colors"
            @click="handleDelete(singleCluster)"
          >
            <Trash2 class="w-3.5 h-3.5" />
            {{ t('common.delete') }}
          </button>
          <div class="flex-1" />
          <button
            v-if="!isDockerCluster(singleCluster)"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            @click="goToDetail(singleCluster.id)"
          >
            {{ t('clusters.viewDetail') }}
            <ChevronRight class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <!-- Mutual exclusivity hint -->
      <p v-if="hasDocker" class="text-xs text-muted-foreground mt-3">{{ t('clusters.dockerMutualHint') }}</p>
      <p v-if="hasK8s" class="text-xs text-muted-foreground mt-3">{{ t('clusters.k8sMutualHint') }}</p>
    </template>

    <!-- Multi-cluster List -->
    <template v-else-if="displayMode === 'list'">
      <div v-if="clusterStore.clusters.length === 0" class="text-center py-20 space-y-3">
        <Server class="w-12 h-12 mx-auto text-muted-foreground/40" />
        <p class="text-muted-foreground">{{ t('clusters.emptyList') }}</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="cluster in clusterStore.clusters"
          :key="cluster.id"
          class="flex items-center justify-between p-4 rounded-xl border border-border bg-card hover:border-primary/20 transition-colors cursor-pointer"
          @click="!isDockerCluster(cluster) && goToDetail(cluster.id)"
        >
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" :class="isDockerCluster(cluster) ? 'bg-blue-500/10' : 'bg-primary/10'">
              <Container v-if="isDockerCluster(cluster)" class="w-4 h-4 text-blue-500" />
              <Server v-else class="w-4 h-4 text-primary" />
            </div>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium text-sm truncate">{{ cluster.name }}</span>
                <span class="w-2 h-2 rounded-full shrink-0" :class="statusDotClass(cluster.status)" />
              </div>
              <div class="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                <template v-if="isDockerCluster(cluster)">
                  <span>{{ t('clusters.dockerRuntimeLabel') }}</span>
                </template>
                <template v-else>
                  <span class="truncate">{{ cluster.api_server_url || '-' }}</span>
                  <span v-if="cluster.k8s_version" class="shrink-0">{{ cluster.k8s_version }}</span>
                  <span class="shrink-0 px-1.5 py-0.5 rounded bg-accent text-accent-foreground text-[10px]">{{ cluster.provider }}</span>
                </template>
              </div>
            </div>
          </div>

          <div class="flex items-center gap-1.5 shrink-0 ml-3" @click.stop>
            <button
              class="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
              :disabled="testingId === cluster.id"
              :title="t('clusters.testConnection')"
              @click="handleTest(cluster.id)"
            >
              <Loader2 v-if="testingId === cluster.id" class="w-4 h-4 animate-spin" />
              <Plug v-else class="w-4 h-4" />
            </button>
            <button
              v-if="!isDockerCluster(cluster)"
              class="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              :title="t('clusters.rename')"
              @click="openRename(cluster)"
            >
              <Pencil class="w-4 h-4" />
            </button>
            <button
              class="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
              :title="t('common.delete')"
              @click="handleDelete(cluster)"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Add Cluster Dialog -->
    <Teleport to="body">
      <div
        v-if="showAddDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="showAddDialog = false"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-lg p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ t('clusters.addCluster') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="showAddDialog = false">
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="space-y-3">
            <div>
              <label class="block text-sm text-muted-foreground mb-1">KubeConfig</label>
              <textarea
                v-model="addForm.kubeconfig"
                rows="8"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                :placeholder="t('clusters.kubeconfigPlaceholder')"
              />
            </div>
            <div>
              <label class="block text-sm text-muted-foreground mb-1">{{ t('clusters.clusterName') }}</label>
              <input
                v-model="addForm.name"
                type="text"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                :placeholder="t('clusters.namePlaceholder')"
              />
              <p v-if="nameAutoFilled" class="text-xs text-muted-foreground mt-1">{{ t('clusters.nameAutoFilled') }}</p>
            </div>
          </div>

          <div class="flex justify-end gap-2 pt-2">
            <button
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showAddDialog = false"
            >{{ t('common.cancel') }}</button>
            <button
              class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!addForm.kubeconfig.trim() || !addForm.name.trim() || adding"
              @click="handleAdd"
            >
              <Loader2 v-if="adding" class="w-4 h-4 animate-spin" />
              {{ t('clusters.addCluster') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Rename Dialog -->
    <Teleport to="body">
      <div
        v-if="showRenameDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="showRenameDialog = false"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-sm p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ t('clusters.rename') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="showRenameDialog = false">
              <X class="w-4 h-4" />
            </button>
          </div>
          <input
            v-model="renameForm.name"
            type="text"
            class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            @keyup.enter="handleRename"
          />
          <div class="flex justify-end gap-2">
            <button
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showRenameDialog = false"
            >{{ t('common.cancel') }}</button>
            <button
              class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!renameForm.name.trim() || renaming"
              @click="handleRename"
            >
              <Loader2 v-if="renaming" class="w-4 h-4 animate-spin" />
              <template v-else>{{ t('common.confirm') }}</template>
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Update KubeConfig Dialog -->
    <Teleport to="body">
      <div
        v-if="showKubeconfigDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="showKubeconfigDialog = false"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-lg p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ t('clusters.updateKubeconfig') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="showKubeconfigDialog = false">
              <X class="w-4 h-4" />
            </button>
          </div>
          <textarea
            v-model="kubeconfigForm.kubeconfig"
            rows="10"
            class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
            :placeholder="t('clusters.kubeconfigPlaceholder')"
          />
          <div class="flex justify-end gap-2">
            <button
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showKubeconfigDialog = false"
            >{{ t('common.cancel') }}</button>
            <button
              class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!kubeconfigForm.kubeconfig.trim() || updatingKubeconfig"
              @click="handleKubeconfigUpdate"
            >
              <Loader2 v-if="updatingKubeconfig" class="w-4 h-4 animate-spin" />
              {{ t('clusters.updateKubeconfig') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
