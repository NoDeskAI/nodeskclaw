<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowRight, Filter } from 'lucide-vue-next'
import api from '@/services/api'

const { t } = useI18n()

interface TimelineMessage {
  id: string
  sender_type: string
  sender_id: string
  sender_name: string
  content: string
  target_instance_id: string | null
  depth: number
  created_at: string
}

const props = defineProps<{
  workspaceId: string
  agents: { instance_id: string; display_name?: string; name: string }[]
}>()

const emit = defineEmits<{
  (e: 'replay-flow', sourceInstanceId: string, target: string): void
}>()

const messages = ref<TimelineMessage[]>([])
const loading = ref(false)
const filterAgent = ref<string>('')

async function fetchTimeline() {
  loading.value = true
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/collaboration-timeline?limit=100`)
    messages.value = res.data.data || []
  } catch {
    messages.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.workspaceId, fetchTimeline, { immediate: true })

const filteredMessages = computed(() => {
  if (!filterAgent.value) return messages.value
  return messages.value.filter(
    m => m.sender_id === filterAgent.value || m.target_instance_id === filterAgent.value,
  )
})

function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function truncate(text: string, maxLen: number): string {
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

function getAgentName(instanceId: string | null): string {
  if (!instanceId) return '...'
  const agent = props.agents.find(a => a.instance_id === instanceId)
  return agent?.display_name || agent?.name || instanceId.slice(0, 8)
}

function onClickMessage(msg: TimelineMessage) {
  emit('replay-flow', msg.sender_id, msg.target_instance_id ? `agent:${getAgentName(msg.target_instance_id)}` : 'broadcast')
}

function addLiveMessage(data: Record<string, unknown>) {
  messages.value.push({
    id: `live-${Date.now()}`,
    sender_type: 'agent',
    sender_id: data.instance_id as string || '',
    sender_name: data.agent_name as string || '',
    content: data.content as string || '',
    target_instance_id: null,
    depth: 0,
    created_at: new Date().toISOString(),
  })
}

defineExpose({ addLiveMessage })
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex items-center gap-2 px-3 py-2 border-b border-border shrink-0">
      <Filter class="w-3.5 h-3.5 text-muted-foreground" />
      <select
        v-model="filterAgent"
        class="flex-1 text-xs bg-transparent border border-border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
      >
        <option value="">{{ t('workspaceView.allAgents') }}</option>
        <option v-for="a in agents" :key="a.instance_id" :value="a.instance_id">
          {{ a.display_name || a.name }}
        </option>
      </select>
    </div>

    <div class="flex-1 overflow-y-auto p-2 space-y-1.5">
      <div v-if="loading" class="text-center text-sm text-muted-foreground py-8">
        {{ t('common.loading') }}
      </div>
      <div v-else-if="filteredMessages.length === 0" class="text-center text-sm text-muted-foreground py-8">
        {{ t('workspaceView.noMessages') }}
      </div>
      <div
        v-else
        v-for="msg in filteredMessages"
        :key="msg.id"
        class="rounded px-2 py-1.5 hover:bg-muted/60 transition-colors cursor-pointer text-xs"
        @click="onClickMessage(msg)"
      >
        <div class="flex items-center gap-1 text-muted-foreground">
          <span class="text-[10px] tabular-nums">{{ formatTime(msg.created_at) }}</span>
          <span class="font-medium text-foreground/80">{{ msg.sender_name }}</span>
          <ArrowRight class="w-3 h-3" />
          <span class="text-foreground/60">{{ msg.target_instance_id ? getAgentName(msg.target_instance_id) : 'broadcast' }}</span>
        </div>
        <p class="text-foreground/70 mt-0.5 leading-snug">{{ truncate(msg.content, 80) }}</p>
      </div>
    </div>
  </div>
</template>
