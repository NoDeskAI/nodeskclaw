<script setup lang="ts">
import { computed } from 'vue'
import { Bot, Users } from 'lucide-vue-next'
import MiniHexPreview from './MiniHexPreview.vue'
import type { WorkspaceListItem } from '@/stores/workspace'

const props = defineProps<{ workspace: WorkspaceListItem }>()
const emit = defineEmits<{ (e: 'click'): void }>()

const statusSummary = computed(() => {
  const agents = props.workspace.agents || []
  const active = agents.filter((a) => a.status === 'running' || a.status === 'active').length
  if (agents.length === 0) return '无 Agent'
  if (active === agents.length) return '全部活跃'
  return `${active}/${agents.length} 活跃`
})
</script>

<template>
  <div
    class="group relative bg-card border border-border rounded-xl overflow-hidden cursor-pointer hover:border-primary/30 transition-all hover:shadow-lg hover:shadow-primary/5"
    @click="emit('click')"
  >
    <!-- Mini 3D preview area -->
    <div class="h-36 bg-gradient-to-b from-primary/5 to-transparent flex items-center justify-center overflow-hidden">
      <MiniHexPreview :agents="workspace.agents" :color="workspace.color" />
    </div>

    <!-- Info -->
    <div class="p-4 space-y-2">
      <div class="flex items-center gap-2">
        <div
          class="w-8 h-8 rounded-lg flex items-center justify-center text-sm"
          :style="{ backgroundColor: workspace.color + '22', color: workspace.color }"
        >
          {{ workspace.icon === 'bot' ? '🤖' : workspace.icon }}
        </div>
        <div class="flex-1 min-w-0">
          <h3 class="font-semibold text-sm truncate">{{ workspace.name }}</h3>
          <p class="text-xs text-muted-foreground truncate">{{ workspace.description || '无描述' }}</p>
        </div>
      </div>

      <div class="flex items-center gap-3 text-xs text-muted-foreground">
        <span class="flex items-center gap-1">
          <Bot class="w-3 h-3" />
          {{ workspace.agent_count }} Agent{{ workspace.agent_count !== 1 ? 's' : '' }}
        </span>
        <span>{{ statusSummary }}</span>
      </div>
    </div>
  </div>
</template>
