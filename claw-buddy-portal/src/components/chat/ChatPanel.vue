<script setup lang="ts">
import { ref, nextTick, watch, computed, onMounted } from 'vue'
import { useWorkspaceStore, type GroupChatMessage } from '@/stores/workspace'
import { Send, Loader2, Bot, User } from 'lucide-vue-next'

const props = defineProps<{
  workspaceId: string
}>()

const store = useWorkspaceStore()

const input = ref('')
const messagesEl = ref<HTMLElement | null>(null)

const messages = computed(() => store.chatMessages)
const sending = computed(() => store.chatLoading)
const typingAgents = computed(() => store.typingAgents)

const typingNames = computed(() => {
  const names = Array.from(typingAgents.value.values())
  if (names.length === 0) return ''
  if (names.length === 1) return `${names[0]} 正在输入...`
  return `${names.join(', ')} 正在输入...`
})

const AGENT_COLORS = [
  '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#a855f7',
]

const agentColorMap = new Map<string, string>()
function getAgentColor(senderId: string): string {
  if (!agentColorMap.has(senderId)) {
    agentColorMap.set(senderId, AGENT_COLORS[agentColorMap.size % AGENT_COLORS.length])
  }
  return agentColorMap.get(senderId)!
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

watch(messages, scrollToBottom, { deep: true })

onMounted(() => {
  store.fetchChatHistory(props.workspaceId)
})

async function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return
  input.value = ''
  await store.sendWorkspaceMessage(props.workspaceId, text)
  scrollToBottom()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

function formatTime(dateStr: string): string {
  try {
    const d = new Date(dateStr)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Messages -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
      <div
        v-if="messages.length === 0"
        class="flex items-center justify-center h-full text-muted-foreground text-sm"
      >
        发送消息开始群聊，所有 Agent 都会看到
      </div>

      <div v-for="msg in messages" :key="msg.id" class="flex gap-2" :class="msg.sender_type === 'user' ? 'flex-row-reverse' : 'flex-row'">
        <!-- Avatar -->
        <div
          class="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-white text-xs"
          :style="{
            backgroundColor: msg.sender_type === 'agent'
              ? getAgentColor(msg.sender_id)
              : '#6b7280',
          }"
        >
          <Bot v-if="msg.sender_type === 'agent'" class="w-3.5 h-3.5" />
          <User v-else class="w-3.5 h-3.5" />
        </div>

        <!-- Bubble -->
        <div class="flex flex-col max-w-[75%]" :class="msg.sender_type === 'user' ? 'items-end' : 'items-start'">
          <div class="flex items-center gap-1.5 mb-0.5">
            <span class="text-xs font-medium" :style="{ color: msg.sender_type === 'agent' ? getAgentColor(msg.sender_id) : undefined }">
              {{ msg.sender_name }}
            </span>
            <span class="text-[10px] text-muted-foreground">{{ formatTime(msg.created_at) }}</span>
            <span
              v-if="msg.message_type === 'collaboration'"
              class="text-[10px] px-1 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300"
            >
              collaboration
            </span>
          </div>
          <div
            class="rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
            :class="msg.sender_type === 'user'
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-foreground'"
          >
            {{ msg.content || '...' }}
            <span v-if="msg.streaming" class="inline-block w-1.5 h-4 bg-current animate-pulse ml-0.5 align-text-bottom" />
          </div>
        </div>
      </div>
    </div>

    <!-- Typing indicator -->
    <div v-if="typingNames" class="px-4 py-1 text-xs text-muted-foreground shrink-0">
      {{ typingNames }}
    </div>

    <!-- Input -->
    <div class="border-t border-border px-4 py-2 shrink-0">
      <div class="flex items-center gap-2">
        <textarea
          v-model="input"
          rows="1"
          class="flex-1 resize-none bg-muted rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          placeholder="发送消息给所有 Agent..."
          @keydown="handleKeydown"
        />
        <button
          class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          :disabled="!input.trim() || sending"
          @click="sendMessage"
        >
          <Loader2 v-if="sending" class="w-4 h-4 animate-spin" />
          <Send v-else class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
