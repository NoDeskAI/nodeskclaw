<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Plus, Loader2, Bot, Search } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()

const workspaceId = computed(() => route.params.id as string)

interface InstanceItem {
  id: string
  name: string
  status: string
  workspace_id: string | null
}

const instances = ref<InstanceItem[]>([])
const loading = ref(false)
const adding = ref<string | null>(null)
const search = ref('')

const available = computed(() =>
  instances.value
    .filter((i) => !i.workspace_id)
    .filter((i) => !search.value || i.name.toLowerCase().includes(search.value.toLowerCase())),
)

onMounted(async () => {
  loading.value = true
  try {
    const res = await api.get('/instances')
    instances.value = (res.data.data || []).map((i: any) => ({
      id: i.id,
      name: i.name,
      status: i.status,
      workspace_id: i.workspace_id,
    }))
  } catch (e) {
    console.error('fetch instances error:', e)
  } finally {
    loading.value = false
  }
})

async function addToWorkspace(instanceId: string) {
  adding.value = instanceId
  try {
    await store.addAgent(workspaceId.value, instanceId)
    const idx = instances.value.findIndex((i) => i.id === instanceId)
    if (idx >= 0) instances.value[idx].workspace_id = workspaceId.value
  } catch (e: any) {
    alert(e?.response?.data?.detail || '添加失败')
  } finally {
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
      <h1 class="text-xl font-bold">添加 Agent</h1>
    </div>

    <p class="text-sm text-muted-foreground mb-4">
      从已有实例中选择一个 Agent 添加到工作区
    </p>

    <!-- Search -->
    <div class="relative mb-4">
      <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
      <input
        v-model="search"
        class="w-full pl-9 pr-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50"
        placeholder="搜索实例..."
      />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-10">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty -->
    <div v-else-if="available.length === 0" class="text-center py-10 text-muted-foreground text-sm">
      没有可用的实例
    </div>

    <!-- Instance list -->
    <div v-else class="space-y-2">
      <div
        v-for="inst in available"
        :key="inst.id"
        class="flex items-center justify-between px-4 py-3 rounded-lg bg-card border border-border hover:border-primary/20 transition-colors"
      >
        <div class="flex items-center gap-3">
          <Bot class="w-5 h-5 text-primary" />
          <div>
            <p class="text-sm font-medium">{{ inst.name }}</p>
            <p class="text-xs text-muted-foreground">{{ inst.status }}</p>
          </div>
        </div>
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 disabled:opacity-50"
          :disabled="adding === inst.id"
          @click="addToWorkspace(inst.id)"
        >
          <Loader2 v-if="adding === inst.id" class="w-3 h-3 animate-spin" />
          <Plus v-else class="w-3 h-3" />
          添加
        </button>
      </div>
    </div>
  </div>
</template>
