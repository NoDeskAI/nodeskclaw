<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useClusterStore, type ClusterInfo } from '@/stores/cluster'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import StatusDot from '@/components/StatusDot.vue'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { ArrowLeft, Server, Cpu, MemoryStick, Box, KeyRound, Plug, Pencil, Check, X, Globe } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import { useI18n } from 'vue-i18n'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'

const { t } = useI18n()

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()

const clusterId = route.params.id as string
const cluster = ref<ClusterInfo | null>(null)
const loading = ref(true)
const error = ref('')

interface NodeInfo {
  name: string
  status: string
  ip: string | null
  cpu_capacity: string
  cpu_used: string
  mem_capacity: string
  mem_used: string
  os: string | null
  kubelet_version: string | null
}

interface OverviewSummary {
  node_count: number
  node_ready: number
  cpu_total: string
  cpu_used: string
  cpu_percent: number
  memory_total: string
  memory_used: string
  memory_percent: number
  pod_count: number
}

interface StorageClassInfo {
  name: string
  provisioner: string
  reclaim_policy: string | null
  allow_volume_expansion: boolean
  is_default: boolean
  enabled: boolean
}

interface IngressClassItem {
  name: string
  controller: string
}

const summary = ref<OverviewSummary | null>(null)
const nodes = ref<NodeInfo[]>([])
const storageClasses = ref<StorageClassInfo[]>([])
const ingressClasses = ref<IngressClassItem[]>([])
const savingIngressClass = ref(false)

onMounted(async () => {
  // Find cluster from store
  if (clusterStore.clusters.length === 0) {
    await clusterStore.fetchClusters()
  }
  cluster.value = clusterStore.clusters.find((c) => c.id === clusterId) ?? null

  if (!cluster.value) {
    error.value = '集群不存在'
    loading.value = false
    return
  }

  try {
    const res = await api.get(`/clusters/${clusterId}/overview`)
    const data = res.data.data
    summary.value = data.summary
    nodes.value = data.nodes
    storageClasses.value = data.storage_classes || []
    ingressClasses.value = data.ingress_classes || []
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '获取集群概览失败'
  } finally {
    loading.value = false
  }
})

function resourcePercent(used: string, total: string): number {
  const usedNum = parseFloat(used)
  const totalNum = parseFloat(total)
  if (!totalNum) return 0
  return Math.round((usedNum / totalNum) * 100)
}

// ── 重命名集群 ──
const editingName = ref(false)
const editName = ref('')
const savingName = ref(false)

const nameInputRef = ref<HTMLInputElement | null>(null)

function startEditName() {
  editName.value = cluster.value?.name || ''
  editingName.value = true
  nextTick(() => nameInputRef.value?.focus())
}

function cancelEditName() {
  editingName.value = false
}

async function handleSaveName() {
  const trimmed = editName.value.trim()
  if (!trimmed || trimmed === cluster.value?.name) {
    editingName.value = false
    return
  }
  savingName.value = true
  try {
    const updated = await clusterStore.updateCluster(clusterId, { name: trimmed })
    cluster.value = updated
    editingName.value = false
    toast.success('集群名称已更新')
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, '重命名失败'))
  } finally {
    savingName.value = false
  }
}

// ── 更新 KubeConfig ──
const showKubeconfigDialog = ref(false)
const newKubeconfig = ref('')
const updatingKubeconfig = ref(false)
const testingConnection = ref(false)

async function handleUpdateKubeconfig() {
  if (!newKubeconfig.value.trim()) return
  updatingKubeconfig.value = true
  try {
    const updated = await clusterStore.updateKubeconfig(clusterId, newKubeconfig.value)
    cluster.value = updated
    showKubeconfigDialog.value = false
    newKubeconfig.value = ''
    toast.success('KubeConfig 已更新')
  } catch {
    toast.error('更新失败')
  } finally {
    updatingKubeconfig.value = false
  }
}

async function handleTestConnection() {
  testingConnection.value = true
  try {
    const result = await clusterStore.testConnection(clusterId)
    if (result.ok) {
      toast.success(`连接成功: K8s ${result.version}, ${result.nodes} 节点`)
      await clusterStore.fetchClusters()
      cluster.value = clusterStore.clusters.find((c) => c.id === clusterId) ?? cluster.value
    } else {
      toast.error(`连接失败: ${result.message}`)
    }
  } catch {
    toast.error('测试连接失败')
  } finally {
    testingConnection.value = false
  }
}

async function handleIngressClassChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (!value || value === cluster.value?.ingress_class) return
  savingIngressClass.value = true
  try {
    const updated = await clusterStore.updateCluster(clusterId, { ingress_class: value })
    cluster.value = updated
    toast.success(t('clusterDetail.ingressClassUpdated'))
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, t('clusterDetail.ingressClassUpdateFailed')))
  } finally {
    savingIngressClass.value = false
  }
}
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center gap-3">
      <Button variant="ghost" size="sm" @click="router.push('/cluster')">
        <ArrowLeft class="w-4 h-4" />
      </Button>
      <Server class="w-6 h-6" />
      <div class="flex-1">
        <div class="flex items-center gap-2">
          <template v-if="editingName">
            <input
              ref="nameInputRef"
              v-model="editName"
              class="text-2xl font-bold bg-transparent border-b-2 border-primary outline-none px-0 py-0 w-80"
              @keydown.enter="handleSaveName"
              @keydown.escape="cancelEditName"
            />
            <Button variant="ghost" size="icon" class="h-7 w-7" :disabled="savingName" @click="handleSaveName">
              <Check class="w-4 h-4 text-primary" />
            </Button>
            <Button variant="ghost" size="icon" class="h-7 w-7" :disabled="savingName" @click="cancelEditName">
              <X class="w-4 h-4 text-muted-foreground" />
            </Button>
          </template>
          <template v-else>
            <h1 class="text-2xl font-bold">{{ cluster?.name || '集群详情' }}</h1>
            <button v-if="cluster" class="h-7 w-7 flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors" @click="startEditName">
              <Pencil class="w-3.5 h-3.5" />
            </button>
          </template>
        </div>
        <div v-if="cluster" class="flex items-center gap-2 text-sm text-muted-foreground mt-0.5">
          <Badge variant="secondary">{{ cluster.provider }}</Badge>
          <span v-if="cluster.k8s_version">K8s {{ cluster.k8s_version }}</span>
          <Badge :variant="cluster.status === 'connected' ? 'default' : 'destructive'">
            {{ cluster.status }}
          </Badge>
        </div>
      </div>
      <div v-if="cluster" class="flex items-center gap-2">
        <Button variant="outline" size="sm" :disabled="testingConnection" @click="handleTestConnection">
          <Plug class="w-3.5 h-3.5 mr-1" />
          {{ testingConnection ? '测试中...' : '测试连接' }}
        </Button>
        <Button variant="outline" size="sm" @click="showKubeconfigDialog = true">
          <KeyRound class="w-3.5 h-3.5 mr-1" />
          更新 KubeConfig
        </Button>
      </div>
    </div>

    <div v-if="loading" class="text-center py-12 text-muted-foreground">加载中...</div>
    <div v-else-if="error" class="text-center py-12 text-destructive">{{ error }}</div>

    <template v-else-if="summary">
      <!-- Resource summary cards -->
      <div class="grid grid-cols-4 gap-4">
        <Card>
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-muted-foreground text-sm mb-2">
              <Server class="w-4 h-4" /> 节点
            </div>
            <div class="text-2xl font-bold">{{ summary.node_ready }} / {{ summary.node_count }}</div>
            <div class="text-xs text-muted-foreground mt-1">Ready / Total</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-muted-foreground text-sm mb-2">
              <Cpu class="w-4 h-4" /> CPU
            </div>
            <div class="text-2xl font-bold">{{ summary.cpu_percent }}%</div>
            <div class="w-full h-1.5 bg-muted rounded-full mt-2 overflow-hidden">
              <div
                class="h-full rounded-full bg-primary transition-all"
                :style="{ width: `${summary.cpu_percent}%` }"
              />
            </div>
            <div class="text-xs text-muted-foreground mt-1">{{ summary.cpu_used }} / {{ summary.cpu_total }}</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-muted-foreground text-sm mb-2">
              <MemoryStick class="w-4 h-4" /> Memory
            </div>
            <div class="text-2xl font-bold">{{ summary.memory_percent }}%</div>
            <div class="w-full h-1.5 bg-muted rounded-full mt-2 overflow-hidden">
              <div
                class="h-full rounded-full bg-primary transition-all"
                :style="{ width: `${summary.memory_percent}%` }"
              />
            </div>
            <div class="text-xs text-muted-foreground mt-1">{{ summary.memory_used }} / {{ summary.memory_total }}</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-muted-foreground text-sm mb-2">
              <Box class="w-4 h-4" /> Pods
            </div>
            <div class="text-2xl font-bold">{{ summary.pod_count }}</div>
            <div class="text-xs text-muted-foreground mt-1">全集群 Pod 数</div>
          </CardContent>
        </Card>
      </div>

      <!-- Node list table -->
      <Card>
        <CardHeader>
          <CardTitle>节点列表</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border text-left text-muted-foreground">
                  <th class="py-2 pr-4">状态</th>
                  <th class="py-2 pr-4">节点名称</th>
                  <th class="py-2 pr-4">IP</th>
                  <th class="py-2 pr-4">CPU</th>
                  <th class="py-2 pr-4">内存</th>
                  <th class="py-2 pr-4">Kubelet</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="node in nodes"
                  :key="node.name"
                  class="border-b border-border/50"
                >
                  <td class="py-2.5 pr-4">
                    <StatusDot :status="node.status === 'Ready' ? 'running' : 'failed'" />
                  </td>
                  <td class="py-2.5 pr-4 font-mono text-xs">{{ node.name }}</td>
                  <td class="py-2.5 pr-4 text-muted-foreground">{{ node.ip || '-' }}</td>
                  <td class="py-2.5 pr-4">
                    <div class="flex items-center gap-2">
                      <div class="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          class="h-full rounded-full bg-primary"
                          :style="{ width: `${resourcePercent(node.cpu_used, node.cpu_capacity)}%` }"
                        />
                      </div>
                      <span class="text-xs text-muted-foreground">{{ node.cpu_used }}/{{ node.cpu_capacity }}</span>
                    </div>
                  </td>
                  <td class="py-2.5 pr-4">
                    <div class="flex items-center gap-2">
                      <div class="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div
                          class="h-full rounded-full bg-primary"
                          :style="{ width: `${resourcePercent(node.mem_used, node.mem_capacity)}%` }"
                        />
                      </div>
                      <span class="text-xs text-muted-foreground">{{ node.mem_used }}/{{ node.mem_capacity }}</span>
                    </div>
                  </td>
                  <td class="py-2.5 pr-4 text-xs text-muted-foreground">{{ node.kubelet_version || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <!-- IngressClass 配置 -->
      <Card>
        <CardHeader>
          <CardTitle>{{ t('clusterDetail.ingressClass') }}</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="flex items-center gap-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <Globe class="w-4 h-4" />
              <span>{{ t('clusterDetail.ingressClassDesc') }}</span>
            </div>
            <select
              :value="cluster?.ingress_class || 'nginx'"
              :disabled="savingIngressClass"
              class="rounded-md bg-card border border-border px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
              @change="handleIngressClassChange"
            >
              <option
                v-for="ic in ingressClasses"
                :key="ic.name"
                :value="ic.name"
              >
                {{ ic.name }} ({{ ic.controller }})
              </option>
              <option
                v-if="cluster && !ingressClasses.some(ic => ic.name === cluster!.ingress_class)"
                :value="cluster.ingress_class"
              >
                {{ cluster.ingress_class }}
              </option>
            </select>
          </div>
        </CardContent>
      </Card>

      <!-- StorageClass 列表 -->
      <Card v-if="storageClasses.length > 0">
        <CardHeader>
          <CardTitle>StorageClass</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-border text-left text-muted-foreground">
                  <th class="py-2 pr-4">名称</th>
                  <th class="py-2 pr-4">Provisioner</th>
                  <th class="py-2 pr-4">回收策略</th>
                  <th class="py-2 pr-4">允许扩容</th>
                  <th class="py-2 pr-4">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="sc in storageClasses"
                  :key="sc.name"
                  class="border-b border-border/50"
                >
                  <td class="py-2.5 pr-4 font-mono text-xs">{{ sc.name }}</td>
                  <td class="py-2.5 pr-4 text-muted-foreground text-xs">{{ sc.provisioner }}</td>
                  <td class="py-2.5 pr-4 text-xs">{{ sc.reclaim_policy || '-' }}</td>
                  <td class="py-2.5 pr-4 text-xs">{{ sc.allow_volume_expansion ? '是' : '否' }}</td>
                  <td class="py-2.5 pr-4 flex gap-1">
                    <Badge v-if="sc.enabled" variant="default" class="text-xs">已启用</Badge>
                    <Badge v-else variant="secondary" class="text-xs">未启用</Badge>
                    <Badge v-if="sc.is_default" variant="outline" class="text-xs">集群默认</Badge>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </template>

    <!-- 更新 KubeConfig 弹窗 -->
    <Dialog v-model:open="showKubeconfigDialog">
      <DialogContent class="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>更新 KubeConfig</DialogTitle>
        </DialogHeader>
        <div class="py-4">
          <textarea
            v-model="newKubeconfig"
            class="w-full h-56 rounded-md bg-card border border-border px-3 py-2 text-sm font-mono resize-none focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="粘贴新的 KubeConfig YAML..."
          />
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showKubeconfigDialog = false">取消</Button>
          <Button
            :disabled="updatingKubeconfig || !newKubeconfig.trim()"
            @click="handleUpdateKubeconfig"
          >
            {{ updatingKubeconfig ? '更新中...' : '确认更新' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
