<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useClusterStore, type ClusterInfo } from '@/stores/cluster'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { resolveApiErrorMessage } from '@/i18n/error'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import {
  Server,
  Plus,
  Loader2,
  Plug,
  Pencil,
  Trash2,
  X,
  ChevronRight,
} from 'lucide-vue-next'

const { t } = useI18n()
const router = useRouter()
const clusterStore = useClusterStore()
const toast = useToast()
const { confirm } = useConfirm()

const loading = ref(true)
const testingId = ref<string | null>(null)

const showAddDialog = ref(false)
const addForm = ref({ name: '', kubeconfig: '' })
const adding = ref(false)
const nameAutoFilled = ref(false)

const showRenameDialog = ref(false)
const renameForm = ref({ id: '', name: '' })
const renaming = ref(false)

const showKubeconfigDialog = ref(false)
const kubeconfigForm = ref({ id: '', kubeconfig: '' })
const updatingKubeconfig = ref(false)

type DisplayMode = 'setup' | 'list'

const displayMode = computed<DisplayMode>(() => {
  return clusterStore.clusters.length === 0 ? 'setup' : 'list'
})

const canAddCluster = computed(() => true)



const addFormValid = computed(() => {
  if (!addForm.value.name.trim()) return false
  if (!addForm.value.kubeconfig.trim()) return false
  return true
})

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

function openAddDialog() {
  addForm.value = { name: '', kubeconfig: '' }
  nameAutoFilled.value = false
  showAddDialog.value = true
}

onMounted(async () => {
  await clusterStore.fetchClusters()
  loading.value = false
})

async function handleAdd() {
  if (!addFormValid.value) return
  adding.value = true
  try {
    await clusterStore.createCluster({
      name: addForm.value.name.trim(),
      compute_provider: 'k8s',
      kubeconfig: addForm.value.kubeconfig.trim(),
    })
    toast.success(t('clusters.addSuccess'))
    showAddDialog.value = false
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
      const msg = result.nodes != null
        ? t('clusters.testSuccessK8s', { version: result.version ?? '', nodes: result.nodes })
        : t('clusters.testSuccess', { version: result.version ?? '' })
      toast.success(msg)
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

function goToDetail(id: string) {
  router.push({ name: 'ClusterDetail', params: { id } })
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
      <Button variant="unstyled" size="unstyled"
        v-if="canAddCluster && displayMode !== 'setup'"
        class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="openAddDialog"
      >
        <Plus class="w-4 h-4" />
        {{ t('clusters.addCluster') }}
      </Button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Setup (0 clusters) -->
    <template v-else-if="displayMode === 'setup'">
      <div class="flex flex-col items-center justify-center py-16 space-y-4">
        <div class="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center">
          <Server class="w-7 h-7 text-primary" />
        </div>
        <div class="text-center space-y-1">
          <h3 class="font-semibold">{{ t('clusters.setupTitle') }}</h3>
          <p class="text-sm text-muted-foreground">{{ t('clusters.setupDesc') }}</p>
        </div>
        <Button variant="unstyled" size="unstyled"
          class="flex items-center gap-1.5 px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          @click="openAddDialog"
        >
          <Plus class="w-4 h-4" />
          {{ t('clusters.addCluster') }}
        </Button>
      </div>
    </template>

    <!-- Cluster List -->
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
          @click="goToDetail(cluster.id)"
        >
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 bg-primary/10">
              <Server class="w-4 h-4 text-primary" />
            </div>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="font-medium text-sm truncate">{{ cluster.name }}</span>
                <span class="w-2 h-2 rounded-full shrink-0" :class="statusDotClass(cluster.status)" />
              </div>
              <div class="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                <span class="truncate">{{ cluster.api_server_url || '-' }}</span>
                <span v-if="cluster.k8s_version" class="shrink-0">{{ cluster.k8s_version }}</span>
                <span class="shrink-0 px-1.5 py-0.5 rounded bg-accent text-accent-foreground text-[10px]">{{ cluster.provider }}</span>
              </div>
            </div>
          </div>

          <div class="flex items-center gap-1.5 shrink-0 ml-3" @click.stop>
            <Button variant="unstyled" size="unstyled"
              class="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors disabled:opacity-50"
              :disabled="testingId === cluster.id"
              :title="t('clusters.testConnection')"
              @click="handleTest(cluster.id)"
            >
              <Loader2 v-if="testingId === cluster.id" class="w-4 h-4 animate-spin" />
              <Plug v-else class="w-4 h-4" />
            </Button>
            <Button variant="unstyled" size="unstyled"
              class="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              :title="t('clusters.rename')"
              @click="openRename(cluster)"
            >
              <Pencil class="w-4 h-4" />
            </Button>
            <Button variant="unstyled" size="unstyled"
              class="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
              :title="t('common.delete')"
              @click="handleDelete(cluster)"
            >
              <Trash2 class="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </template>

    <!-- Unified Add Cluster Dialog -->
    <Teleport to="body">
      <div
        v-if="showAddDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="showAddDialog = false"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-lg p-6 space-y-5">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ t('clusters.addCluster') }}</h3>
            <Button variant="unstyled" size="unstyled" class="text-muted-foreground hover:text-foreground" @click="showAddDialog = false">
              <X class="w-4 h-4" />
            </Button>
          </div>

          <!-- KubeConfig -->
          <div class="space-y-3">
            <div>
              <label class="block text-sm text-muted-foreground mb-1">KubeConfig</label>
              <Textarea
                v-model="addForm.kubeconfig"
                rows="8"
                class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                :placeholder="t('clusters.kubeconfigPlaceholder')"
              />
            </div>
          </div>

          <!-- Cluster Name -->
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('clusters.clusterName') }}</label>
            <Input
              v-model="addForm.name"
              type="text"
              class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              :placeholder="t('clusters.namePlaceholder')"
            />
            <p v-if="nameAutoFilled" class="text-xs text-muted-foreground mt-1">{{ t('clusters.nameAutoFilled') }}</p>
          </div>

          <div class="flex justify-end gap-2 pt-1">
            <Button variant="unstyled" size="unstyled"
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showAddDialog = false"
            >{{ t('common.cancel') }}</Button>
            <Button variant="unstyled" size="unstyled"
              class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!addFormValid || adding"
              @click="handleAdd"
            >
              <Loader2 v-if="adding" class="w-4 h-4 animate-spin" />
              {{ t('clusters.addCluster') }}
            </Button>
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
            <Button variant="unstyled" size="unstyled" class="text-muted-foreground hover:text-foreground" @click="showRenameDialog = false">
              <X class="w-4 h-4" />
            </Button>
          </div>
          <Input
            v-model="renameForm.name"
            type="text"
            class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            @keyup.enter="handleRename"
          />
          <div class="flex justify-end gap-2">
            <Button variant="unstyled" size="unstyled"
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showRenameDialog = false"
            >{{ t('common.cancel') }}</Button>
            <Button variant="unstyled" size="unstyled"
              class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!renameForm.name.trim() || renaming"
              @click="handleRename"
            >
              <Loader2 v-if="renaming" class="w-4 h-4 animate-spin" />
              <template v-else>{{ t('common.confirm') }}</template>
            </Button>
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
            <Button variant="unstyled" size="unstyled" class="text-muted-foreground hover:text-foreground" @click="showKubeconfigDialog = false">
              <X class="w-4 h-4" />
            </Button>
          </div>
          <Textarea
            v-model="kubeconfigForm.kubeconfig"
            rows="10"
            class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
            :placeholder="t('clusters.kubeconfigPlaceholder')"
          />
          <div class="flex justify-end gap-2">
            <Button variant="unstyled" size="unstyled"
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showKubeconfigDialog = false"
            >{{ t('common.cancel') }}</Button>
            <Button variant="unstyled" size="unstyled"
              class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!kubeconfigForm.kubeconfig.trim() || updatingKubeconfig"
              @click="handleKubeconfigUpdate"
            >
              <Loader2 v-if="updatingKubeconfig" class="w-4 h-4 animate-spin" />
              {{ t('clusters.updateKubeconfig') }}
            </Button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
