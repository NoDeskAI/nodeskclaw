<script setup lang="ts">
import { ref, nextTick, watch, computed, onMounted } from 'vue'
import { useWorkspaceStore, type GroupChatMessage, type AgentBrief } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { Send, Loader2, Bot, User, AtSign, Slash, RotateCw, Trash2, Activity, XCircle } from 'lucide-vue-next'
import api from '@/services/api'

const props = defineProps<{
  workspaceId: string
}>()

const store = useWorkspaceStore()
const authStore = useAuthStore()

const input = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const messagesEl = ref<HTMLElement | null>(null)

const messages = computed(() => store.chatMessages)
const sending = computed(() => store.chatLoading)
const typingAgents = computed(() => store.typingAgents)
const agents = computed(() => store.currentWorkspace?.agents || [])
const userAvatarUrl = computed(() => authStore.user?.avatar_url)

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

function agentLabel(a: AgentBrief): string {
  return a.display_name || a.name
}

// ── @ Mention autocomplete ────────────────────────
const mentionOpen = ref(false)
const mentionQuery = ref('')
const mentionIdx = ref(0)

const filteredAgents = computed(() => {
  const q = mentionQuery.value.toLowerCase()
  if (!q) return agents.value
  return agents.value.filter(a => agentLabel(a).toLowerCase().includes(q))
})

watch(filteredAgents, () => { mentionIdx.value = 0 })

function findMentionTrigger(): number | null {
  const el = textareaRef.value
  if (!el) return null
  const text = el.value
  const cursor = el.selectionStart
  const before = text.slice(0, cursor)
  const atIdx = before.lastIndexOf('@')
  if (atIdx < 0) return null
  if (atIdx > 0 && before[atIdx - 1] !== ' ' && before[atIdx - 1] !== '\n') return null
  const query = before.slice(atIdx + 1)
  if (query.includes(' ') || query.includes('\n')) return null
  return atIdx
}

function selectMention(agent: AgentBrief) {
  const el = textareaRef.value
  if (!el) return
  const atIdx = findMentionTrigger()
  if (atIdx === null) return
  const cursor = el.selectionStart
  const name = agentLabel(agent)
  const after = el.value.slice(cursor)
  input.value = el.value.slice(0, atIdx) + `@${name} ` + after
  mentionOpen.value = false
  nextTick(() => {
    const pos = atIdx + name.length + 2
    el.setSelectionRange(pos, pos)
    el.focus()
  })
}

// ── / Command autocomplete ────────────────────────
const COMMANDS = [
  { name: 'status', label: '显示所有 Agent 状态', icon: Activity, needsAgent: false },
  { name: 'clear', label: '清空聊天记录', icon: XCircle, needsAgent: false },
  { name: 'restart', label: '重启 Agent', icon: RotateCw, needsAgent: true },
  { name: 'remove', label: '移除 Agent', icon: Trash2, needsAgent: true },
]

const commandOpen = ref(false)
const commandQuery = ref('')
const commandIdx = ref(0)

const filteredCommands = computed(() => {
  const q = commandQuery.value.toLowerCase()
  if (!q) return COMMANDS
  return COMMANDS.filter(c => c.name.includes(q) || c.label.includes(q))
})

watch(filteredCommands, () => { commandIdx.value = 0 })

function selectCommand(cmd: typeof COMMANDS[number]) {
  commandOpen.value = false
  if (!cmd.needsAgent) {
    executeSlashCommand(cmd.name)
    input.value = ''
    return
  }
  input.value = `/${cmd.name} @`
  nextTick(() => {
    const el = textareaRef.value
    if (el) {
      el.setSelectionRange(input.value.length, input.value.length)
      el.focus()
      mentionQuery.value = ''
      mentionOpen.value = true
    }
  })
}

// ── Input event detection ─────────────────────────
function handleInputEvent() {
  const el = textareaRef.value
  if (!el) return
  const text = el.value

  if (text.startsWith('/') && !text.includes('\n')) {
    const firstSpace = text.indexOf(' ')
    commandQuery.value = firstSpace < 0 ? text.slice(1) : text.slice(1, firstSpace)
    const afterCommand = firstSpace >= 0 ? text.slice(firstSpace) : ''
    if (!afterCommand.includes('@')) {
      commandOpen.value = true
      mentionOpen.value = false
      return
    }
  }
  commandOpen.value = false

  const atIdx = findMentionTrigger()
  if (atIdx !== null) {
    mentionQuery.value = el.value.slice(atIdx + 1, el.selectionStart)
    mentionOpen.value = true
  } else {
    mentionOpen.value = false
  }
}

// ── Keyboard nav ──────────────────────────────────
function handleKeydown(e: KeyboardEvent) {
  if (mentionOpen.value && filteredAgents.value.length > 0) {
    if (e.key === 'ArrowDown') { e.preventDefault(); mentionIdx.value = (mentionIdx.value + 1) % filteredAgents.value.length; return }
    if (e.key === 'ArrowUp') { e.preventDefault(); mentionIdx.value = (mentionIdx.value - 1 + filteredAgents.value.length) % filteredAgents.value.length; return }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); selectMention(filteredAgents.value[mentionIdx.value]); return }
    if (e.key === 'Escape') { e.preventDefault(); mentionOpen.value = false; return }
  }

  if (commandOpen.value && filteredCommands.value.length > 0) {
    if (e.key === 'ArrowDown') { e.preventDefault(); commandIdx.value = (commandIdx.value + 1) % filteredCommands.value.length; return }
    if (e.key === 'ArrowUp') { e.preventDefault(); commandIdx.value = (commandIdx.value - 1 + filteredCommands.value.length) % filteredCommands.value.length; return }
    if (e.key === 'Enter' || e.key === 'Tab') { e.preventDefault(); selectCommand(filteredCommands.value[commandIdx.value]); return }
    if (e.key === 'Escape') { e.preventDefault(); commandOpen.value = false; return }
  }

  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    sendMessage()
  }
}

// ── Slash command execution ───────────────────────
function insertSystemMessage(content: string) {
  store.chatMessages.push({
    id: `sys-local-${Date.now()}`,
    sender_type: 'system',
    sender_id: 'system',
    sender_name: 'System',
    content,
    message_type: 'system',
    created_at: new Date().toISOString(),
  })
  scrollToBottom()
}

function executeSlashCommand(name: string, arg?: string) {
  switch (name) {
    case 'status': {
      const lines = agents.value.map(a => `${agentLabel(a)}: ${a.status}`)
      insertSystemMessage(lines.length ? lines.join('\n') : '工作区内没有 Agent')
      break
    }
    case 'clear':
      store.chatMessages.splice(0, store.chatMessages.length)
      insertSystemMessage('聊天记录已清空')
      break
    case 'restart':
      if (arg) doRestartAgent(arg)
      else insertSystemMessage('用法: /restart @AgentName')
      break
    case 'remove':
      if (arg) doRemoveAgent(arg)
      else insertSystemMessage('用法: /remove @AgentName')
      break
    default:
      insertSystemMessage(`未知命令: /${name}`)
  }
}

async function doRestartAgent(name: string) {
  const agent = agents.value.find(a => agentLabel(a) === name)
  if (!agent) { insertSystemMessage(`找不到 Agent: ${name}`); return }
  insertSystemMessage(`正在重启 ${name}...`)
  try {
    await api.post(`/instances/${agent.instance_id}/restart`)
    insertSystemMessage(`${name} 已触发重启`)
  } catch (e: any) {
    insertSystemMessage(`重启失败: ${e?.response?.data?.detail || e.message}`)
  }
}

async function doRemoveAgent(name: string) {
  const agent = agents.value.find(a => agentLabel(a) === name)
  if (!agent) { insertSystemMessage(`找不到 Agent: ${name}`); return }
  insertSystemMessage(`正在移除 ${name}...`)
  try {
    await store.removeAgent(props.workspaceId, agent.instance_id)
    insertSystemMessage(`${name} 已从工作区移除`)
  } catch (e: any) {
    insertSystemMessage(`移除失败: ${e?.response?.data?.detail || e.message}`)
  }
}

// ── Message send ──────────────────────────────────
function extractMentionIds(text: string): string[] {
  const ids: string[] = []
  const regex = /@(\S+)/g
  let m
  while ((m = regex.exec(text)) !== null) {
    const agent = agents.value.find(a => agentLabel(a) === m![1])
    if (agent) ids.push(agent.instance_id)
  }
  return [...new Set(ids)]
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || sending.value) return

  if (text.startsWith('/')) {
    const parts = text.split(/\s+/)
    const cmd = parts[0].slice(1)
    const arg = parts.slice(1).join(' ').replace(/^@/, '')
    executeSlashCommand(cmd, arg || undefined)
    input.value = ''
    mentionOpen.value = false
    commandOpen.value = false
    return
  }

  const mentions = extractMentionIds(text)
  input.value = ''
  mentionOpen.value = false
  commandOpen.value = false
  await store.sendWorkspaceMessage(props.workspaceId, text, mentions.length > 0 ? mentions : undefined)
  scrollToBottom()
}

// ── Message content parsing (highlight @mentions) ─
function parseContent(content: string): Array<{ type: 'text' | 'mention'; value: string }> {
  if (!content) return [{ type: 'text', value: '...' }]
  const agentNames = new Set(agents.value.map(a => agentLabel(a)))
  const segments: Array<{ type: 'text' | 'mention'; value: string }> = []
  const regex = /@(\S+)/g
  let lastIdx = 0
  let m
  while ((m = regex.exec(content)) !== null) {
    if (agentNames.has(m[1])) {
      if (m.index > lastIdx) segments.push({ type: 'text', value: content.slice(lastIdx, m.index) })
      segments.push({ type: 'mention', value: m[0] })
      lastIdx = m.index + m[0].length
    }
  }
  if (lastIdx < content.length) segments.push({ type: 'text', value: content.slice(lastIdx) })
  return segments.length ? segments : [{ type: 'text', value: content }]
}

// ── Misc ──────────────────────────────────────────
function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  })
}

watch(messages, scrollToBottom, { deep: true })

onMounted(() => {
  store.fetchChatHistory(props.workspaceId)
})

function formatTime(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
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

      <div v-for="msg in messages" :key="msg.id">
        <!-- System message -->
        <div v-if="msg.sender_type === 'system'" class="flex justify-center">
          <span class="text-xs text-muted-foreground bg-muted/50 rounded-full px-3 py-1 whitespace-pre-wrap">
            {{ msg.content }}
          </span>
        </div>

        <!-- User / Agent message -->
        <div v-else class="flex gap-2" :class="msg.sender_type === 'user' ? 'flex-row-reverse' : 'flex-row'">
          <!-- Avatar -->
          <img
            v-if="msg.sender_type === 'user' && userAvatarUrl"
            :src="userAvatarUrl"
            class="w-7 h-7 rounded-full shrink-0 object-cover"
          />
          <div
            v-else
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
              <template v-for="(seg, si) in parseContent(msg.content)" :key="si">
                <span
                  v-if="seg.type === 'mention'"
                  class="inline-block rounded px-1 font-medium text-xs leading-5"
                  :class="msg.sender_type === 'user'
                    ? 'bg-white/20 text-primary-foreground'
                    : 'bg-primary/20 text-primary'"
                >{{ seg.value }}</span>
                <span v-else>{{ seg.value }}</span>
              </template>
              <span v-if="msg.streaming" class="inline-block w-1.5 h-4 bg-current animate-pulse ml-0.5 align-text-bottom" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Typing indicator -->
    <div v-if="typingNames" class="px-4 py-1 text-xs text-muted-foreground shrink-0">
      {{ typingNames }}
    </div>

    <!-- Input area -->
    <div class="border-t border-border px-4 py-2 shrink-0 relative">
      <!-- @ Mention dropdown -->
      <Transition name="dropdown">
        <div
          v-if="mentionOpen && filteredAgents.length > 0"
          class="absolute bottom-full left-4 right-4 mb-1 rounded-lg border border-border bg-card shadow-lg overflow-hidden z-10"
        >
          <div class="px-3 py-1.5 text-[10px] text-muted-foreground font-medium uppercase tracking-wide border-b border-border">
            Agent
          </div>
          <div class="max-h-40 overflow-y-auto">
            <button
              v-for="(agent, idx) in filteredAgents"
              :key="agent.instance_id"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent transition-colors text-left"
              :class="idx === mentionIdx ? 'bg-accent' : ''"
              @mousedown.prevent="selectMention(agent)"
              @mouseenter="mentionIdx = idx"
            >
              <Bot class="w-4 h-4 shrink-0" :style="{ color: getAgentColor(agent.instance_id) }" />
              <span class="font-medium truncate">{{ agentLabel(agent) }}</span>
              <span class="text-xs text-muted-foreground ml-auto shrink-0">{{ agent.status }}</span>
            </button>
          </div>
        </div>
      </Transition>

      <!-- / Command dropdown -->
      <Transition name="dropdown">
        <div
          v-if="commandOpen && filteredCommands.length > 0"
          class="absolute bottom-full left-4 right-4 mb-1 rounded-lg border border-border bg-card shadow-lg overflow-hidden z-10"
        >
          <div class="px-3 py-1.5 text-[10px] text-muted-foreground font-medium uppercase tracking-wide border-b border-border">
            Commands
          </div>
          <div class="max-h-40 overflow-y-auto">
            <button
              v-for="(cmd, idx) in filteredCommands"
              :key="cmd.name"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent transition-colors text-left"
              :class="idx === commandIdx ? 'bg-accent' : ''"
              @mousedown.prevent="selectCommand(cmd)"
              @mouseenter="commandIdx = idx"
            >
              <component :is="cmd.icon" class="w-4 h-4 shrink-0 text-muted-foreground" />
              <span class="font-mono text-primary">/{{ cmd.name }}</span>
              <span class="text-xs text-muted-foreground ml-1">{{ cmd.label }}</span>
            </button>
          </div>
        </div>
      </Transition>

      <!-- Textarea + hints + send -->
      <div class="flex items-center gap-2">
        <div class="flex-1 relative">
          <textarea
            ref="textareaRef"
            v-model="input"
            rows="1"
            class="w-full resize-none bg-muted rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50"
            placeholder="消息... 输入 @ 提及 Agent，/ 执行命令"
            @keydown="handleKeydown"
            @input="handleInputEvent"
          />
        </div>
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

<style scoped>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
