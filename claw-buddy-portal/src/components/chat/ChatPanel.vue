<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { Send, Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  workspaceId: string
  agentId: string
}>()

const store = useWorkspaceStore()

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

const messages = ref<ChatMessage[]>([])
const input = ref('')
const sending = ref(false)
const messagesEl = ref<HTMLElement | null>(null)

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  sending.value = true
  scrollToBottom()

  const history = messages.value.slice(0, -1).map((m) => ({
    role: m.role,
    content: m.content,
  }))

  messages.value.push({ role: 'assistant', content: '' })
  const assistantIdx = messages.value.length - 1

  try {
    const stream = store.sendMessage(props.workspaceId, props.agentId, text, history)
    for await (const chunk of stream) {
      messages.value[assistantIdx].content += chunk
      scrollToBottom()
    }
  } catch (e: any) {
    messages.value[assistantIdx].content = `错误: ${e.message || '无法连接到 Agent'}`
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- Messages -->
    <div ref="messagesEl" class="flex-1 overflow-y-auto px-4 py-3 space-y-3 min-h-0">
      <div v-if="messages.length === 0" class="flex items-center justify-center h-full text-muted-foreground text-sm">
        开始和 Agent 对话吧
      </div>
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="flex"
        :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div
          class="max-w-[75%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
          :class="msg.role === 'user'
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted text-foreground'"
        >
          {{ msg.content || '...' }}
        </div>
      </div>
    </div>

    <!-- Input -->
    <div class="border-t border-border px-4 py-2 shrink-0">
      <div class="flex items-center gap-2">
        <textarea
          v-model="input"
          rows="1"
          class="flex-1 resize-none bg-muted rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50"
          placeholder="输入消息..."
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
