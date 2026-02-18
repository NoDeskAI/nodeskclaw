<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useClusterStore } from '@/stores/cluster'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import GlowCard from '@/components/GlowCard.vue'
import StatusDot from '@/components/StatusDot.vue'
import { Plus, Trash2, Plug, Server, Pencil } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

const router = useRouter()
const clusterStore = useClusterStore()

const showAddDialog = ref(false)
const addForm = ref({ name: '', kubeconfig: '' })
const adding = ref(false)
const testingId = ref<string | null>(null)
const nameAutoFilled = ref(false)

onMounted(() => {
  clusterStore.fetchClusters()
})

/**
 * 从 KubeConfig YAML 中提取集群名称和 server 地址。
 * 优先使用 current-context 作为名称，其次 clusters[0].name。
 */
function parseKubeConfigMeta(yaml: string): { name: string; server: string } | null {
  if (!yaml.trim()) return null

  // 提取 current-context
  const ctxMatch = yaml.match(/^current-context:\s*(.+)$/m)
  const currentCtx = ctxMatch?.[1]?.trim().replace(/^["']|["']$/g, '') || ''

  // 提取 clusters 段中的第一个 name
  const clusterNameMatch = yaml.match(/clusters:\s*\n\s*-\s*(?:cluster:[\s\S]*?\n)?\s*name:\s*(.+)/m)
    || yaml.match(/clusters:\s*\n\s*-\s*name:\s*(.+)/m)
  const clusterName = clusterNameMatch?.[1]?.trim().replace(/^["']|["']$/g, '') || ''

  // 提取 server 地址
  const serverMatch = yaml.match(/server:\s*(.+)/m)
  const server = serverMatch?.[1]?.trim().replace(/^["']|["']$/g, '') || ''

  const name = currentCtx || clusterName
  if (!name) return null
  return { name, server }
}

// 粘贴 KubeConfig 时自动填充名称
watch(
  () => addForm.value.kubeconfig,
  (yaml) => {
    // 仅在名称为空或之前是自动填充时覆盖
    if (addForm.value.name && !nameAutoFilled.value) return

    const meta = parseKubeConfigMeta(yaml)
    if (meta?.name) {
      addForm.value.name = meta.name
      nameAutoFilled.value = true
    }
  },
)


async function handleAdd() {
  if (!addForm.value.name || !addForm.value.kubeconfig) return
  adding.value = true
  try {
    const cluster = await clusterStore.addCluster(addForm.value.name, addForm.value.kubeconfig)
    toast.success(`集群 "${cluster.name}" 添加成功`)
    showAddDialog.value = false
    addForm.value = { name: '', kubeconfig: '' }
    nameAutoFilled.value = false
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '添加失败'
    toast.error(msg)
  } finally {
    adding.value = false
  }
}

async function handleTest(id: string) {
  testingId.value = id
  try {
    const result = await clusterStore.testConnection(id)
    if (result.ok) {
      toast.success(`连接成功: K8s ${result.version}, ${result.nodes} 节点`)
      await clusterStore.fetchClusters()
    } else {
      toast.error(`连接失败: ${result.message}`)
    }
  } catch {
    toast.error('连接测试失败')
  } finally {
    testingId.value = null
  }
}

async function handleDelete(id: string, name: string) {
  if (!confirm(`确定删除集群 "${name}"？`)) return
  try {
    await clusterStore.deleteCluster(id)
    toast.success('集群已删除')
  } catch {
    toast.error('删除失败')
  }
}

// ── 重命名 ──
const renameDialogOpen = ref(false)
const renameForm = ref({ id: '', name: '' })
const renaming = ref(false)

function openRename(id: string, name: string) {
  renameForm.value = { id, name }
  renameDialogOpen.value = true
}

async function handleRename() {
  const { id, name } = renameForm.value
  if (!name.trim()) return
  renaming.value = true
  try {
    await clusterStore.updateCluster(id, { name: name.trim() })
    toast.success('集群已重命名')
    renameDialogOpen.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || '重命名失败')
  } finally {
    renaming.value = false
  }
}

function statusToGlow(status: string) {
  if (status === 'connected') return 'running' as const
  if (status === 'connecting') return 'warning' as const
  return 'error' as const
}

function statusToDot(status: string) {
  if (status === 'connected') return 'running' as const
  if (status === 'connecting') return 'pending' as const
  return 'failed' as const
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold">集群管理</h1>
      <Button @click="showAddDialog = true">
        <Plus class="w-4 h-4 mr-2" />
        添加集群
      </Button>
    </div>

    <!-- 集群列表 -->
    <div v-if="clusterStore.loading" class="text-muted-foreground text-center py-12">
      加载中...
    </div>

    <div v-else-if="clusterStore.clusters.length === 0" class="text-center py-20">
      <Server class="w-12 h-12 text-muted-foreground mx-auto mb-4" />
      <p class="text-muted-foreground">暂无集群，请先添加</p>
    </div>

    <div v-else class="grid gap-4">
      <GlowCard
        v-for="cluster in clusterStore.clusters"
        :key="cluster.id"
        :status="statusToGlow(cluster.status)"
        class="cursor-pointer"
        @click="router.push(`/cluster/${cluster.id}`)"
      >
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <StatusDot :status="statusToDot(cluster.status)" size="md" />
            <div>
              <div class="font-medium">{{ cluster.name }}</div>
              <div class="text-sm text-muted-foreground mt-0.5">
                {{ cluster.api_server_url || '未连接' }}
                <span v-if="cluster.k8s_version" class="ml-2">
                  K8s {{ cluster.k8s_version }}
                </span>
              </div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <Badge variant="secondary">{{ cluster.provider }}</Badge>
            <Badge :variant="cluster.status === 'connected' ? 'default' : 'destructive'">
              {{ cluster.status }}
            </Badge>
            <Button
              variant="outline"
              size="sm"
              :disabled="testingId === cluster.id"
              @click.stop="handleTest(cluster.id)"
            >
              <Plug class="w-3 h-3 mr-1" />
              {{ testingId === cluster.id ? '测试中...' : '测试连接' }}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              @click.stop="openRename(cluster.id, cluster.name)"
            >
              <Pencil class="w-3 h-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              @click.stop="handleDelete(cluster.id, cluster.name)"
            >
              <Trash2 class="w-3 h-3 text-destructive" />
            </Button>
          </div>
        </div>
      </GlowCard>
    </div>

    <!-- 添加集群 Dialog -->
    <Dialog v-model:open="showAddDialog">
      <DialogContent class="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>添加集群</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <div>
            <label class="text-sm font-medium mb-1.5 block">KubeConfig</label>
            <textarea
              v-model="addForm.kubeconfig"
              class="w-full h-48 rounded-md bg-card border border-border px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:ring-1 focus:ring-ring"
              placeholder="粘贴 KubeConfig YAML 内容..."
            />
          </div>
          <div>
            <label class="text-sm font-medium mb-1.5 block">集群名称</label>
            <Input
              v-model="addForm.name"
              placeholder="如：prod-vke"
              @input="nameAutoFilled = false"
            />
            <p v-if="nameAutoFilled" class="text-xs text-muted-foreground mt-1">
              已从 KubeConfig 自动提取，可手动修改
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showAddDialog = false">取消</Button>
          <Button :disabled="adding || !addForm.name || !addForm.kubeconfig" @click="handleAdd">
            {{ adding ? '添加中...' : '添加' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 重命名集群 Dialog -->
    <Dialog v-model:open="renameDialogOpen">
      <DialogContent class="sm:max-w-[380px]">
        <DialogHeader>
          <DialogTitle>重命名集群</DialogTitle>
        </DialogHeader>
        <div class="py-4">
          <Input
            v-model="renameForm.name"
            placeholder="输入新的集群名称"
            @keydown.enter="handleRename"
          />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="renameDialogOpen = false">取消</Button>
          <Button :disabled="renaming || !renameForm.name.trim()" @click="handleRename">
            {{ renaming ? '保存中...' : '确认' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
