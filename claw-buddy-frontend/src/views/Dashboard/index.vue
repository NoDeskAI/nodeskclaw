<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useClusterStore } from '@/stores/cluster'
import { useInstanceStore } from '@/stores/instance'
import { useGlobalSSE } from '@/composables/useGlobalSSE'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import StatusDot from '@/components/StatusDot.vue'
import ActivityFeed from '@/components/ActivityFeed.vue'
import { Server, Box, Activity, Rocket, AlertTriangle } from 'lucide-vue-next'

const router = useRouter()
const clusterStore = useClusterStore()
const instanceStore = useInstanceStore()
const { feedEvents } = useGlobalSSE()

const loading = ref(true)

onMounted(async () => {
  await Promise.all([
    clusterStore.fetchClusters(),
    instanceStore.fetchInstances(),
  ])
  loading.value = false
})

const stats = computed(() => {
  const total = instanceStore.instances.length
  const running = instanceStore.instances.filter((i) => i.status === 'running').length
  const failed = instanceStore.instances.filter((i) => i.status === 'failed').length
  const clusters = clusterStore.clusters.length
  const clustersConnected = clusterStore.clusters.filter((c) => c.status === 'connected').length
  return { total, running, failed, clusters, clustersConnected }
})
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-2xl font-bold">Dashboard</h1>

    <div v-if="loading" class="text-muted-foreground text-center py-12">加载中...</div>

    <template v-else>
      <!-- Stats cards -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card class="cursor-pointer hover:border-primary/50 transition-colors" @click="router.push('/cluster')">
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <Server class="w-4 h-4" />
              集群
            </div>
            <div class="text-3xl font-bold mt-2">{{ stats.clusters }}</div>
            <div class="text-xs text-muted-foreground mt-1">
              {{ stats.clustersConnected }} 已连接
            </div>
          </CardContent>
        </Card>

        <Card class="cursor-pointer hover:border-primary/50 transition-colors" @click="router.push('/instances')">
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <Box class="w-4 h-4" />
              实例
            </div>
            <div class="text-3xl font-bold mt-2">{{ stats.total }}</div>
            <div class="text-xs text-muted-foreground mt-1">
              {{ stats.running }} 运行中
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <Activity class="w-4 h-4" />
              运行中
            </div>
            <div class="text-3xl font-bold text-green-400 mt-2">{{ stats.running }}</div>
          </CardContent>
        </Card>

        <Card>
          <CardContent class="pt-4">
            <div class="flex items-center gap-2 text-sm text-muted-foreground">
              <AlertTriangle class="w-4 h-4" />
              异常
            </div>
            <div class="text-3xl font-bold mt-2" :class="stats.failed > 0 ? 'text-red-400' : 'text-muted-foreground'">
              {{ stats.failed }}
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- Quick actions + Activity Feed -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Left: Quick actions + Recent instances -->
        <div class="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>快捷操作</CardTitle>
            </CardHeader>
            <CardContent class="flex gap-3">
              <Button @click="router.push('/deploy')">
                <Rocket class="w-4 h-4 mr-2" />
                部署实例
              </Button>
              <Button variant="outline" @click="router.push('/cluster')">
                <Server class="w-4 h-4 mr-2" />
                管理集群
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>最近实例</CardTitle>
            </CardHeader>
            <CardContent>
              <div v-if="instanceStore.instances.length === 0" class="text-sm text-muted-foreground">
                暂无实例，请先部署
              </div>
              <div v-else class="space-y-2">
                <div
                  v-for="inst in instanceStore.instances.slice(0, 5)"
                  :key="inst.id"
                  class="flex items-center justify-between rounded-md bg-muted/30 px-4 py-2 cursor-pointer hover:bg-muted/50 transition-colors"
                  @click="router.push(`/instances/${inst.id}`)"
                >
                  <div class="flex items-center gap-2">
                    <StatusDot
                      :status="inst.status === 'running' ? 'running' : inst.status === 'failed' ? 'failed' : 'pending'"
                    />
                    <span class="text-sm font-medium">{{ inst.name }}</span>
                    <span class="text-xs text-muted-foreground">{{ inst.image_version }}</span>
                  </div>
                  <span class="text-xs text-muted-foreground">
                    {{ inst.available_replicas }}/{{ inst.replicas }}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <!-- Right: Activity Feed -->
        <Card>
          <CardHeader>
            <CardTitle>实时动态</CardTitle>
          </CardHeader>
          <CardContent>
            <ActivityFeed :events="feedEvents" :max-items="20" />
          </CardContent>
        </Card>
      </div>
    </template>
  </div>
</template>
