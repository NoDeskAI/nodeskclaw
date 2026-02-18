<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Loader2 } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import WorkspaceCard from '@/components/workspace/WorkspaceCard.vue'

const router = useRouter()
const store = useWorkspaceStore()

onMounted(() => {
  store.fetchWorkspaces()
})

function openWorkspace(id: string) {
  router.push(`/workspace/${id}`)
}

function createNew() {
  router.push('/workspace/create')
}
</script>

<template>
  <div class="max-w-5xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold">我的工作区</h1>
        <p class="text-sm text-muted-foreground mt-1">管理你的 Agent 协作空间</p>
      </div>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="createNew"
      >
        <Plus class="w-4 h-4" />
        新建工作区
      </button>
    </div>

    <!-- Loading -->
    <div v-if="store.loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="store.workspaces.length === 0"
      class="text-center py-20 space-y-4"
    >
      <div class="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto text-2xl">
        🤖
      </div>
      <h3 class="text-lg font-semibold">还没有工作区</h3>
      <p class="text-sm text-muted-foreground max-w-sm mx-auto">
        创建一个工作区，添加 Agent，让它们互相协作，共同完成任务
      </p>
      <button
        class="mt-4 px-6 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="createNew"
      >
        创建第一个工作区
      </button>
    </div>

    <!-- Grid -->
    <div
      v-else
      class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      <WorkspaceCard
        v-for="ws in store.workspaces"
        :key="ws.id"
        :workspace="ws"
        @click="openWorkspace(ws.id)"
      />
    </div>
  </div>
</template>
