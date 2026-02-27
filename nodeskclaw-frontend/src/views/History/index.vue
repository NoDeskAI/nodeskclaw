<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useInstanceStore, type DeployRecord } from '@/stores/instance'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '@/components/ui/dialog'
import { ArrowLeft, GitCompare } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

const route = useRoute()
const router = useRouter()
const instanceStore = useInstanceStore()

const instanceId = route.params.id as string
const instanceName = ref('')
const history = ref<DeployRecord[]>([])
const loading = ref(true)

// Compare dialog
const showCompare = ref(false)
const compareOld = ref<Record<string, unknown>>({})
const compareNew = ref<Record<string, unknown>>({})
const compareTitle = ref('')

onMounted(async () => {
  try {
    const detail = await instanceStore.fetchDetail(instanceId)
    instanceName.value = detail.name
    history.value = await instanceStore.getHistory(instanceId)
  } finally {
    loading.value = false
  }
})

function formatTime(ts: string | null): string {
  if (!ts) return '-'
  return new Date(ts).toLocaleString('zh-CN')
}

function actionLabel(action: string): string {
  const map: Record<string, string> = {
    deploy: '部署',
    create: '创建',
    upgrade: '升级',
    rollback: '回滚',
    scale: '扩缩容',
    restart: '重启',
    delete: '删除',
  }
  return map[action] || action
}

function statusVariant(status: string) {
  if (status === 'success') return 'default' as const
  if (status === 'failed') return 'destructive' as const
  return 'secondary' as const
}

async function handleRollback(revision: number) {
  try {
    await instanceStore.rollback(instanceId, revision)
    toast.success(`已回滚到 Revision ${revision}`)
    history.value = await instanceStore.getHistory(instanceId)
  } catch {
    toast.error('回滚失败')
  }
}

function openCompare(idx: number) {
  if (idx >= history.value.length - 1) return
  const current = history.value[idx]
  const prev = history.value[idx + 1]

  const parseSafe = (s: string | null): Record<string, unknown> => {
    if (!s) return {}
    try {
      return JSON.parse(s)
    } catch {
      return {}
    }
  }

  compareNew.value = {
    revision: current.revision,
    action: current.action,
    image_version: current.image_version,
    replicas: current.replicas,
    ...parseSafe(current.config_snapshot),
  }
  compareOld.value = {
    revision: prev.revision,
    action: prev.action,
    image_version: prev.image_version,
    replicas: prev.replicas,
    ...parseSafe(prev.config_snapshot),
  }
  compareTitle.value = `Revision ${prev.revision} -> ${current.revision}`
  showCompare.value = true
}

// Compute diff keys
const diffKeys = computed(() => {
  const allKeys = new Set([...Object.keys(compareOld.value), ...Object.keys(compareNew.value)])
  return [...allKeys]
})
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center gap-3">
      <Button variant="ghost" size="sm" @click="router.back()">
        <ArrowLeft class="w-4 h-4" />
      </Button>
      <h1 class="text-2xl font-bold">{{ instanceName }} -- 部署历史</h1>
    </div>

    <div v-if="loading" class="text-muted-foreground text-center py-12">加载中...</div>

    <Card v-else>
      <CardHeader>
        <CardTitle>版本时间线</CardTitle>
      </CardHeader>
      <CardContent>
        <div v-if="history.length === 0" class="text-sm text-muted-foreground py-8 text-center">
          暂无部署记录
        </div>
        <div v-else class="relative">
          <!-- Timeline line -->
          <div class="absolute left-[15px] top-6 bottom-6 w-px bg-primary/30" />

          <div v-for="(rec, idx) in history" :key="rec.id" class="relative pl-12 pb-8">
            <!-- Timeline dot -->
            <div
              class="absolute left-0 top-1 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
              :class="idx === 0
                ? 'bg-primary text-primary-foreground shadow-md shadow-primary/30'
                : 'bg-muted text-muted-foreground'"
            >
              {{ rec.revision }}
            </div>

            <div class="rounded-lg border bg-card px-5 py-4">
              <!-- Header -->
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2 flex-wrap">
                  <Badge v-if="idx === 0" class="text-xs">当前版本</Badge>
                  <Badge variant="outline" class="text-xs">{{ actionLabel(rec.action) }}</Badge>
                  <Badge :variant="statusVariant(rec.status)" class="text-xs">{{ rec.status }}</Badge>
                </div>
                <span class="text-xs text-muted-foreground">{{ formatTime(rec.started_at) }}</span>
              </div>

              <!-- Details -->
              <div class="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                <div v-if="rec.image_version">
                  <span class="text-muted-foreground">镜像:</span>
                  <span class="ml-1 font-medium">{{ rec.image_version }}</span>
                </div>
                <div v-if="rec.replicas">
                  <span class="text-muted-foreground">副本:</span>
                  <span class="ml-1 font-medium">{{ rec.replicas }}</span>
                </div>
                <div v-if="rec.finished_at">
                  <span class="text-muted-foreground">耗时:</span>
                  <span class="ml-1 font-medium">
                    {{ rec.started_at && rec.finished_at
                      ? Math.round((new Date(rec.finished_at).getTime() - new Date(rec.started_at).getTime()) / 1000) + 's'
                      : '-'
                    }}
                  </span>
                </div>
              </div>

              <div v-if="rec.message" class="mt-2 text-xs text-red-400 break-all">
                {{ rec.message }}
              </div>

              <!-- Actions -->
              <div v-if="idx !== 0" class="mt-3 flex gap-2">
                <Button
                  v-if="idx < history.length - 1 && rec.config_snapshot"
                  variant="ghost" size="sm" class="text-xs h-7"
                  @click="openCompare(idx)"
                >
                  <GitCompare class="w-3 h-3 mr-1" /> 对比
                </Button>
                <Button
                  v-if="rec.config_snapshot"
                  variant="ghost" size="sm" class="text-xs h-7"
                  @click="handleRollback(rec.revision)"
                >
                  回滚到此版本
                </Button>
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Compare Dialog -->
    <Dialog v-model:open="showCompare">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>版本对比: {{ compareTitle }}</DialogTitle>
          <DialogDescription>对比两个版本之间的配置差异</DialogDescription>
        </DialogHeader>
        <div class="grid grid-cols-2 gap-4 py-4 text-xs font-mono">
          <div>
            <div class="text-muted-foreground mb-2 font-bold">旧版本</div>
            <div v-for="key in diffKeys" :key="'old-' + key" class="py-1">
              <span class="text-muted-foreground">{{ key }}:</span>
              <span
                class="ml-1"
                :class="String(compareOld[key]) !== String(compareNew[key]) ? 'text-red-400' : ''"
              >
                {{ compareOld[key] ?? '-' }}
              </span>
            </div>
          </div>
          <div>
            <div class="text-muted-foreground mb-2 font-bold">新版本</div>
            <div v-for="key in diffKeys" :key="'new-' + key" class="py-1">
              <span class="text-muted-foreground">{{ key }}:</span>
              <span
                class="ml-1"
                :class="String(compareOld[key]) !== String(compareNew[key]) ? 'text-green-400' : ''"
              >
                {{ compareNew[key] ?? '-' }}
              </span>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showCompare = false">关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
