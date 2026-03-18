<script setup lang="ts">
import { ref, nextTick, watch, computed, onMounted, type Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import { Extension } from '@tiptap/core'
import { PluginKey } from '@tiptap/pm/state'
import { useWorkspaceStore, type GroupChatMessage, type AgentBrief, type FileAttachment } from '@/stores/workspace'
import FileAttachmentList from './FileAttachmentList.vue'
import BaseTooltip from '@/components/shared/BaseTooltip.vue'
import { useAuthStore } from '@/stores/auth'
import { Send, Loader2, Bot, User, Users, AtSign, Slash, RotateCw, Trash2, Activity, XCircle, Copy, ThumbsUp, ThumbsDown, Paperclip, X, FileText } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { renderMarkdown as renderMd } from '@/utils/markdown'
import { AgentMention } from './extensions/agentMention'
import { SlashCommand } from './extensions/slashCommand'

const props = withDefaults(defineProps<{
  workspaceId: string
  canSend?: boolean
}>(), {
  canSend: true,
})

const { t } = useI18n()
const store = useWorkspaceStore()
const authStore = useAuthStore()
const toast = useToast()

const messagesEl = ref<HTMLElement | null>(null)

const messages = computed(() => store.chatMessages)
const sending = computed(() => store.chatLoading)
const typingAgents = computed(() => store.typingAgents)
const agents = computed(() => store.currentWorkspace?.agents || [])
const userAvatarUrl = computed(() => authStore.user?.avatar_url)

const typingNames = computed(() => {
  const names = Array.from(typingAgents.value.values())
  if (names.length === 0) return ''
  return t('chat.isTyping', { names: names.join(', ') })
})

const AGENT_COLORS = [
  '#8b5cf6', '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#ec4899', '#6366f1', '#14b8a6', '#f97316', '#a855f7',
]

const agentColorMap = new Map<string, string>()
function getAgentColor(senderId: string): string {
  if (!agentColorMap.has(senderId)) {
    const color = AGENT_COLORS[agentColorMap.size % AGENT_COLORS.length] ?? '#8b5cf6'
    agentColorMap.set(senderId, color)
  }
  return agentColorMap.get(senderId)!
}

function agentLabel(a: AgentBrief): string {
  return a.display_name || a.name
}

function hexDistToBlackboard(q: number, r: number): number {
  return Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r))
}

function agentSublabel(senderId: string): string | null {
  const a = agents.value.find(x => x.instance_id === senderId)
  return a?.label ?? null
}

function agentSlug(senderId: string): string | null {
  const a = agents.value.find(x => x.instance_id === senderId)
  return a?.slug ?? null
}

const slugTooltipId = ref<string | null>(null)

function onSlugEnter(e: MouseEvent, msgId: string) {
  const el = (e.currentTarget as HTMLElement).querySelector('.slug-text')
  if (el && el.scrollWidth > el.clientWidth) {
    slugTooltipId.value = msgId
  }
}

async function copySlug(agentId: string) {
  const slug = agentSlug(agentId)
  if (!slug) return
  await navigator.clipboard.writeText(slug)
  toast.success(t('chat.slugCopied'))
}

// ── File upload ──────────────────────────────────────
const fileInputRef = ref<HTMLInputElement | null>(null)
const pendingFiles = ref<File[]>([])
const fileUploading = ref(false)

const MAX_FILE_SIZE = 20 * 1024 * 1024

function triggerFileInput() {
  if (!store.fileUploadEnabled) return
  fileInputRef.value?.click()
}

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  addFiles(Array.from(input.files))
  input.value = ''
}

function addFiles(files: File[]) {
  for (const f of files) {
    if (f.size > MAX_FILE_SIZE) {
      toast.error(t('chat.fileTooLarge', { size: 20 }))
      continue
    }
    pendingFiles.value.push(f)
  }
}

function removePendingFile(idx: number) {
  pendingFiles.value.splice(idx, 1)
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

function handleDragOver(e: DragEvent) {
  if (!store.fileUploadEnabled) return
  e.preventDefault()
}

function handleDrop(e: DragEvent) {
  if (!store.fileUploadEnabled) return
  e.preventDefault()
  if (e.dataTransfer?.files) {
    addFiles(Array.from(e.dataTransfer.files))
  }
}

// ── Commands ────────────────────────────────────────
const COMMANDS = computed(() => [
  { name: 'status', label: t('chat.cmdStatusLabel'), icon: Activity, needsAgent: false, immediate: true },
  { name: 'clear', label: t('chat.cmdClearLabel'), icon: XCircle, needsAgent: false, immediate: true },
  { name: 'restart', label: t('chat.cmdRestartLabel'), icon: RotateCw, needsAgent: true, immediate: false },
  { name: 'remove', label: t('chat.cmdRemoveLabel'), icon: Trash2, needsAgent: true, immediate: false },
])

// ── Suggestion state ─────────────────────────────────
interface SuggestionItem {
  id: string
  label: string
  [key: string]: any
}

interface SuggestionState {
  items: SuggestionItem[]
  selectedIndex: number
  command: (item: SuggestionItem) => void
}

const mentionState = ref<SuggestionState | null>(null)
const commandState = ref<SuggestionState | null>(null)
const pendingCommand = ref<{ id: string; label: string } | null>(null)

function createSuggestionRenderer(stateRef: Ref<SuggestionState | null>) {
  return () => {
    let idx = 0
    return {
      onStart(p: any) {
        idx = 0
        stateRef.value = { items: p.items, selectedIndex: 0, command: p.command }
      },
      onUpdate(p: any) {
        idx = 0
        stateRef.value = p.items.length
          ? { items: p.items, selectedIndex: 0, command: p.command }
          : null
      },
      onKeyDown({ event }: { event: KeyboardEvent }): boolean {
        if (!stateRef.value || !stateRef.value.items.length) return false
        const len = stateRef.value.items.length
        if (event.key === 'ArrowUp') {
          idx = (idx - 1 + len) % len
          stateRef.value = { ...stateRef.value, selectedIndex: idx }
          return true
        }
        if (event.key === 'ArrowDown') {
          idx = (idx + 1) % len
          stateRef.value = { ...stateRef.value, selectedIndex: idx }
          return true
        }
        if (event.key === 'Enter' || event.key === 'Tab') {
          const selected = stateRef.value.items[idx]
          if (selected) stateRef.value.command(selected)
          return true
        }
        if (event.key === 'Escape') {
          stateRef.value = null
          return true
        }
        return false
      },
      onExit() {
        stateRef.value = null
      },
    }
  }
}

// ── Slash command execution ───────────────────────
function insertSystemMessage(content: string, persist = true) {
  if (persist) {
    store.sendSystemMessage(props.workspaceId, content)
  } else {
    store.chatMessages.push({
      id: `sys-local-${Date.now()}`,
      sender_type: 'system',
      sender_id: 'system',
      sender_name: 'System',
      content,
      message_type: 'system',
      created_at: new Date().toISOString(),
    })
  }
  scrollToBottom()
}

function executeSlashCommand(name: string, arg?: string) {
  switch (name) {
    case 'status': {
      const lines = agents.value.map(a => `${agentLabel(a)}: ${a.status}`)
      insertSystemMessage(lines.length ? lines.join('\n') : t('chat.noAgentsInWorkspace'))
      break
    }
    case 'clear':
      store.chatMessages.splice(0, store.chatMessages.length)
      insertSystemMessage(t('chat.chatCleared'), false)
      break
    case 'restart':
      if (arg) doRestartAgent(arg)
      else insertSystemMessage(t('chat.restartUsage'))
      break
    case 'remove':
      if (arg) doRemoveAgent(arg)
      else insertSystemMessage(t('chat.removeUsage'))
      break
    default:
      insertSystemMessage(t('chat.unknownCommand', { command: name }))
  }
}

async function doRestartAgent(name: string) {
  const agent = agents.value.find(a => agentLabel(a) === name)
  if (!agent) { insertSystemMessage(t('chat.agentNotFound', { name })); return }
  insertSystemMessage(t('chat.restartingAgent', { name }))
  try {
    await api.post(`/instances/${agent.instance_id}/restart`)
    insertSystemMessage(t('chat.agentRestarted', { name }))
  } catch (e: any) {
    insertSystemMessage(t('chat.restartFailed', { error: resolveApiErrorMessage(e, e?.message || '') }))
  }
}

async function doRemoveAgent(name: string) {
  const agent = agents.value.find(a => agentLabel(a) === name)
  if (!agent) { insertSystemMessage(t('chat.agentNotFound', { name })); return }
  insertSystemMessage(t('chat.removingAgent', { name }))
  try {
    await store.removeAgent(props.workspaceId, agent.instance_id)
    insertSystemMessage(t('chat.agentRemoved', { name }))
  } catch (e: any) {
    insertSystemMessage(t('chat.removeFailed', { error: resolveApiErrorMessage(e, e?.message || '') }))
  }
}

// ── Content extraction ─────────────────────────────
function getEditorContent(): { text: string; mentions: string[]; commands: string[] } {
  const json = editor.value?.getJSON()
  if (!json?.content) return { text: '', mentions: [], commands: [] }
  const parts: string[] = []
  const mentions: string[] = []
  const commands: string[] = []

  for (const block of json.content) {
    if (!block.content) { parts.push('\n'); continue }
    for (const node of block.content as any[]) {
      if (node.type === 'text') {
        parts.push(node.text || '')
      } else if (node.type === 'agentMention') {
        parts.push(`@${node.attrs?.label || ''}`)
        if (node.attrs?.id) mentions.push(node.attrs.id)
      } else if (node.type === 'slashCommand') {
        const agentLbl = node.attrs?.agentLabel
        parts.push(`/${node.attrs?.label || ''}${agentLbl ? ' @' + agentLbl : ''}`)
        if (node.attrs?.id) commands.push(node.attrs.id)
        if (node.attrs?.agentId) mentions.push(node.attrs.agentId)
      }
    }
    parts.push('\n')
  }

  return {
    text: parts.join('').trim(),
    mentions: [...new Set(mentions)],
    commands: [...new Set(commands)],
  }
}

// ── Message send ──────────────────────────────────
async function sendMessage() {
  const hasFiles = pendingFiles.value.length > 0
  const editorIsEmpty = !editor.value || editor.value.isEmpty

  if (editorIsEmpty && !hasFiles) return
  if (sending.value || fileUploading.value) return

  const { text, mentions, commands } = editorIsEmpty
    ? { text: '', mentions: [] as string[], commands: [] as string[] }
    : getEditorContent()
  editor.value?.commands.clearContent()

  if (commands.length > 0) {
    for (const cmdName of commands) {
      const mentionedAgent = mentions.length > 0
        ? agents.value.find(a => a.instance_id === mentions[0])
        : undefined
      executeSlashCommand(cmdName, mentionedAgent ? agentLabel(mentionedAgent) : undefined)
    }
    return
  }

  const slashMatch = text.match(/^\/([a-zA-Z]\w*)(?![/])/)
  if (slashMatch) {
    const cmd = slashMatch[1].toLowerCase()
    const arg = text.slice(slashMatch[0].length).trim().replace(/^@/, '')
    executeSlashCommand(cmd, arg || undefined)
    return
  }

  if (!text.trim() && !hasFiles) return

  let fileIds: string[] | undefined
  let attachments: FileAttachment[] | undefined

  if (hasFiles) {
    fileUploading.value = true
    const filesToUpload = [...pendingFiles.value]
    pendingFiles.value = []
    try {
      const uploaded: FileAttachment[] = []
      for (const f of filesToUpload) {
        const result = await store.uploadFile(props.workspaceId, f)
        if (result) uploaded.push(result)
      }
      if (uploaded.length > 0) {
        fileIds = uploaded.map(u => u.id)
        attachments = uploaded
      }
    } catch (e) {
      toast.error(t('chat.fileUploadFailed'))
      console.error('File upload error:', e)
    } finally {
      fileUploading.value = false
    }
  }

  if (!text.trim() && !fileIds?.length) return

  await store.sendWorkspaceMessage(
    props.workspaceId,
    text || '',
    mentions.length > 0 ? mentions : undefined,
    fileIds,
    attachments,
  )
  scrollToBottom()
}

// ── Editor ────────────────────────────────────────────
const AGENT_MENTION_KEY = new PluginKey('agentMention')
const SLASH_COMMAND_KEY = new PluginKey('slashCommand')

const editorEmpty = ref(true)

const editor = useEditor({
  extensions: [
    StarterKit.configure({
      heading: false,
      bold: false,
      italic: false,
      strike: false,
      code: false,
      codeBlock: false,
      blockquote: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      horizontalRule: false,
      gapcursor: false,
      dropcursor: false,
    }),
    Placeholder.configure({
      placeholder: t('chat.inputPlaceholder'),
    }),
    AgentMention.configure({
      suggestion: {
        pluginKey: AGENT_MENTION_KEY,
        char: '@',
        allowedPrefixes: null,
        items: ({ query, editor: ed }: { query: string; editor: any }) => {
          const q = query.toLowerCase()

          const existingMentions = new Set<string>()
          ed.state.doc.descendants((node: any) => {
            if (node.type.name === 'agentMention' && node.attrs?.id) {
              existingMentions.add(node.attrs.id)
            }
          })

          if (existingMentions.has('__all__')) return []

          const allItem = {
            id: '__all__',
            label: t('chat.mentionAll'),
            sublabel: t('chat.mentionAllHint'),
            status: '',
            slug: '',
          }
          const agentItems = agents.value
            .filter(a => agentLabel(a).toLowerCase().includes(q))
            .filter(a => !existingMentions.has(a.instance_id))
            .sort((a, b) => hexDistToBlackboard(a.hex_q, a.hex_r) - hexDistToBlackboard(b.hex_q, b.hex_r))
            .slice(0, 10)
            .map(a => ({
              id: a.instance_id,
              label: agentLabel(a),
              sublabel: a.label,
              status: a.status,
              slug: a.slug,
            }))
          const showAll = allItem.label.toLowerCase().includes(q) || 'all'.includes(q)
          return showAll ? [allItem, ...agentItems] : agentItems
        },
        render: createSuggestionRenderer(mentionState),
        command: ({ editor: ed, range, props: p }: any) => {
          const pending = pendingCommand.value
          if (pending) {
            ed.chain().focus().insertContentAt(range, [
              { type: 'slashCommand', attrs: {
                id: pending.id, label: pending.label,
                agentId: p.id, agentLabel: p.label,
              }},
              { type: 'text', text: ' ' },
            ]).run()
            pendingCommand.value = null
            return
          }
          const nodeAfter = ed.view.state.selection.$to.nodeAfter
          if (nodeAfter?.text?.startsWith(' ')) range.to += 1
          ed.chain().focus().insertContentAt(range, [
            { type: 'agentMention', attrs: { id: p.id, label: p.label, status: p.status, slug: p.slug } },
            { type: 'text', text: ' ' },
          ]).run()
        },
      },
    }),
    SlashCommand.configure({
      suggestion: {
        pluginKey: SLASH_COMMAND_KEY,
        char: '/',
        items: ({ query }: { query: string }) => {
          const q = query.toLowerCase()
          return COMMANDS.value
            .filter(c => c.name.includes(q) || c.label.includes(q))
            .map(c => ({
              id: c.name,
              label: c.name,
              displayLabel: c.label,
              icon: c.icon,
              immediate: c.immediate,
              needsAgent: c.needsAgent,
            }))
        },
        render: createSuggestionRenderer(commandState),
        command: ({ editor: ed, range, props: p }: any) => {
          if (p.immediate) {
            ed.chain().focus().deleteRange(range).run()
            nextTick(() => executeSlashCommand(p.id))
            return
          }
          if (p.needsAgent) {
            ed.chain().focus().deleteRange(range).run()
            pendingCommand.value = { id: p.id, label: p.label }
            nextTick(() => {
              ed.chain().focus().insertContent('@').run()
            })
            return
          }
          const nodeAfter = ed.view.state.selection.$to.nodeAfter
          const overrideSpace = nodeAfter?.text?.startsWith(' ')
          if (overrideSpace) range.to += 1
          ed.chain().focus().insertContentAt(range, [
            { type: 'slashCommand', attrs: { id: p.id, label: p.label } },
            { type: 'text', text: ' ' },
          ]).run()
          window.getSelection()?.collapseToEnd()
        },
      },
    }),
    Extension.create({
      name: 'sendOnEnter',
      addKeyboardShortcuts() {
        return {
          Enter: () => {
            sendMessage()
            return true
          },
        }
      },
    }),
  ],
  editorProps: {
    attributes: {
      class: 'chat-editor-content scrollbar-compact',
    },
  },
  onUpdate: ({ editor: ed }) => {
    editorEmpty.value = ed.isEmpty
  },
})

// ── Trigger buttons ──────────────────────────────
function triggerMention() {
  if (!editor.value) return
  const text = editor.value.getText()
  const prefix = text.length > 0 && !text.endsWith(' ') && !text.endsWith('\n') ? ' @' : '@'
  editor.value.chain().focus().insertContent(prefix).run()
}

function triggerSlash() {
  if (!editor.value) return
  editor.value.chain().focus().setContent('/').run()
}

// ── Message content parsing (highlight @mentions) ─
function parseContent(content: string): Array<{ type: 'text' | 'mention'; value: string }> {
  if (!content) return [{ type: 'text', value: '...' }]
  const agentNames = new Set(agents.value.map(a => agentLabel(a)))
  agentNames.add(t('chat.mentionAll'))
  agentNames.add('Everyone')
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

// ── Markdown rendering ──────────────────────────────
const GENE_SLUG_RE = /`([a-z][a-z0-9-]*(?:-[a-z0-9]+)*)`/g

function renderMarkdown(content: string): string {
  if (!content) return ''
  let html = renderMd(content)
  html = html.replace(GENE_SLUG_RE, (_match, slug) => {
    return `<a href="/gene-market" class="gene-slug-link" data-gene-slug="${slug}">${slug}</a>`
  })
  return html
}

const feedbackGiven = ref<Record<string, 'up' | 'down'>>({})

async function handleFeedback(msg: GroupChatMessage, type: 'up' | 'down') {
  const key = msg.id
  feedbackGiven.value[key] = type
  try {
    const geneStore = await import('@/stores/gene').then(m => m.useGeneStore())
    const agent = agents.value.find((a: AgentBrief) => a.instance_id === msg.sender_id)
    if (agent) {
      const instanceGenes = await api.get(`/instances/${agent.instance_id}/genes`)
      const installed = instanceGenes.data?.data || []
      for (const ig of installed) {
        if (ig.status === 'installed' && ig.gene_id) {
          await geneStore.logEffectiveness(
            agent.instance_id,
            ig.gene_id,
            type === 'up' ? 'user_positive' : 'user_negative',
          )
        }
      }
    }
  } catch (e) {
    console.error('Feedback error:', e)
  }
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
  store.fetchSystemCapabilities()
})

function formatTime(dateStr: string): string {
  try {
    return new Date(dateStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

function selectSuggestionItem(state: SuggestionState, item: SuggestionItem) {
  state.command(item)
}

function updateSuggestionIndex(state: SuggestionState, idx: number) {
  state.selectedIndex = idx
}
</script>

<template>
  <div class="flex flex-col flex-1 min-h-0">
    <!-- Messages -->
    <div ref="messagesEl" class="messages-scroll flex-1 px-4 py-3 space-y-3 min-h-0">
      <div
        v-if="messages.length === 0"
        class="flex items-center justify-center h-full text-muted-foreground text-sm"
      >
        {{ t('chat.emptyHint') }}
      </div>

      <div v-for="msg in messages" :key="msg.id">
        <!-- System message -->
        <div v-if="msg.sender_type === 'system'" class="flex justify-center">
          <span class="text-xs text-muted-foreground bg-muted/50 rounded-lg px-3 py-1 whitespace-pre-wrap">
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
          <div class="flex flex-col min-w-0" :class="msg.sender_type === 'user' ? 'max-w-[75%] items-end' : 'max-w-[92%] items-start'">
            <div class="flex items-center gap-1.5 mb-0.5 max-w-full min-w-0 group/header">
              <span
                class="text-xs font-medium truncate max-w-[120px] cursor-default"
                :style="{ color: msg.sender_type === 'agent' ? getAgentColor(msg.sender_id) : undefined }"
                :title="msg.sender_name"
              >{{ msg.sender_name }}</span>
              <span
                v-if="msg.sender_type === 'agent' && agentSublabel(msg.sender_id)"
                class="text-[10px] text-muted-foreground truncate max-w-[100px]"
                :title="agentSublabel(msg.sender_id)!"
              >{{ agentSublabel(msg.sender_id) }}</span>
              <span
                v-if="msg.sender_type === 'agent' && agentSlug(msg.sender_id)"
                class="slug-tag"
                @click="copySlug(msg.sender_id)"
                @mouseenter="onSlugEnter($event, msg.id)"
                @mouseleave="slugTooltipId = null"
              >
                <span class="slug-text">{{ agentSlug(msg.sender_id) }}</span>
                <Copy class="slug-copy-icon" />
                <span v-if="slugTooltipId === msg.id" class="slug-tooltip">{{ agentSlug(msg.sender_id) }}</span>
              </span>
              <span class="text-[10px] text-muted-foreground shrink-0">{{ formatTime(msg.created_at) }}</span>
              <span
                v-if="msg.message_type === 'collaboration'"
                class="text-[10px] px-1 py-0.5 rounded bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300 shrink-0"
              >
                collaboration
              </span>
              <span
                v-if="msg.intent"
                class="text-[10px] px-1 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 shrink-0"
              >
                {{ msg.intent }}
              </span>
              <span
                v-if="msg.priority && msg.priority !== 'normal'"
                class="text-[10px] px-1 py-0.5 rounded shrink-0"
                :class="msg.priority === 'critical' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300' : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'"
              >
                {{ msg.priority }}
              </span>
            </div>
            <div
              v-if="msg.sender_type === 'agent'"
              class="rounded-lg px-3 py-2 text-sm bg-muted text-foreground chat-markdown"
              v-html="renderMarkdown(msg.content)"
            />
            <div
              v-if="msg.sender_type === 'agent' && !msg.streaming && msg.content"
              class="flex items-center gap-1 mt-1"
            >
              <button
                class="p-1 rounded hover:bg-muted/80 transition-colors"
                :class="feedbackGiven[msg.id] === 'up' ? 'text-green-500' : 'text-muted-foreground/50 hover:text-green-500'"
                @click="handleFeedback(msg, 'up')"
              >
                <ThumbsUp class="w-3 h-3" />
              </button>
              <button
                class="p-1 rounded hover:bg-muted/80 transition-colors"
                :class="feedbackGiven[msg.id] === 'down' ? 'text-red-500' : 'text-muted-foreground/50 hover:text-red-500'"
                @click="handleFeedback(msg, 'down')"
              >
                <ThumbsDown class="w-3 h-3" />
              </button>
            </div>
            <div
              v-else-if="msg.sender_type !== 'agent'"
              class="rounded-lg px-3 py-2 text-sm whitespace-pre-wrap bg-primary text-primary-foreground"
            >
              <template v-for="(seg, si) in parseContent(msg.content)" :key="si">
                <span
                  v-if="seg.type === 'mention'"
                  class="inline-block rounded px-1 font-semibold text-xs leading-5 bg-white/30 text-primary-foreground"
                >{{ seg.value }}</span>
                <span v-else>{{ seg.value }}</span>
              </template>
            </div>
            <FileAttachmentList
              v-if="msg.attachments?.length"
              :attachments="msg.attachments"
              :workspace-id="workspaceId"
            />
            <span v-if="msg.streaming" class="inline-block w-1.5 h-4 bg-current animate-pulse ml-0.5 align-text-bottom" />
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
      <!-- @ Agent suggestion dropdown -->
      <Transition name="dropdown">
        <div
          v-if="mentionState && mentionState.items.length > 0"
          class="absolute bottom-full left-4 right-4 mb-1 rounded-lg border border-border bg-card shadow-lg overflow-hidden z-10"
        >
          <div class="px-3 py-1.5 text-[10px] text-muted-foreground font-medium uppercase tracking-wide border-b border-border">
            {{ t('chat.mentionTitle') }}
          </div>
          <div class="max-h-40 overflow-y-auto">
            <button
              v-for="(item, idx) in mentionState.items"
              :key="item.id"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent transition-colors text-left"
              :class="idx === mentionState.selectedIndex ? 'bg-accent' : ''"
              @mousedown.prevent="selectSuggestionItem(mentionState!, item)"
              @mouseenter="updateSuggestionIndex(mentionState!, idx)"
            >
              <Users v-if="item.id === '__all__'" class="w-4 h-4 shrink-0 text-primary" />
              <Bot v-else class="w-4 h-4 shrink-0" :style="{ color: getAgentColor(item.id) }" />
              <div class="flex flex-col min-w-0 flex-1">
                <span class="font-medium truncate">{{ item.label }}</span>
                <span v-if="item.sublabel" class="text-[10px] text-muted-foreground truncate">{{ item.sublabel }}</span>
              </div>
              <span class="text-xs text-muted-foreground ml-auto shrink-0">{{ item.slug || item.status }}</span>
            </button>
          </div>
        </div>
      </Transition>

      <!-- / Command suggestion dropdown -->
      <Transition name="dropdown">
        <div
          v-if="commandState && commandState.items.length > 0"
          class="absolute bottom-full left-4 right-4 mb-1 rounded-lg border border-border bg-card shadow-lg overflow-hidden z-10"
        >
          <div class="px-3 py-1.5 text-[10px] text-muted-foreground font-medium uppercase tracking-wide border-b border-border">
            Commands
          </div>
          <div class="max-h-40 overflow-y-auto">
            <button
              v-for="(item, idx) in commandState.items"
              :key="item.id"
              class="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent transition-colors text-left"
              :class="idx === commandState.selectedIndex ? 'bg-accent' : ''"
              @mousedown.prevent="selectSuggestionItem(commandState!, item)"
              @mouseenter="updateSuggestionIndex(commandState!, idx)"
            >
              <component :is="item.icon" class="w-4 h-4 shrink-0 text-muted-foreground" />
              <span class="font-mono text-primary">/{{ item.id }}</span>
              <span class="text-xs text-muted-foreground ml-1">{{ item.displayLabel }}</span>
              <span
                class="ml-auto text-[10px] px-1.5 py-0.5 rounded-full shrink-0"
                :class="item.immediate
                  ? 'bg-green-500/15 text-green-600 dark:text-green-400'
                  : 'bg-primary/10 text-primary'"
              >{{ item.immediate ? t('chat.immediate') : 'Tag' }}</span>
            </button>
          </div>
        </div>
      </Transition>

      <!-- Tiptap editor container -->
      <div
        v-if="canSend"
        class="rounded-lg border border-border bg-muted focus-within:ring-1 focus-within:ring-primary/50 focus-within:border-primary/50 transition-colors"
        @dragover="handleDragOver"
        @drop="handleDrop"
      >
        <!-- Pending files preview -->
        <div v-if="pendingFiles.length > 0" class="flex flex-wrap gap-2 px-3 pt-2 max-h-[76px] overflow-y-auto">
          <div
            v-for="(file, idx) in pendingFiles"
            :key="idx"
            class="group relative flex items-center gap-1.5 px-2 py-1 rounded-md bg-background border border-border text-xs max-w-[200px]"
          >
            <FileText class="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
            <span class="truncate">{{ file.name }}</span>
            <span class="text-muted-foreground shrink-0">({{ formatFileSize(file.size) }})</span>
            <button
              class="absolute -top-1.5 -right-1.5 p-0.5 rounded-full bg-destructive text-destructive-foreground opacity-0 group-hover:opacity-100 transition-opacity"
              @click.stop="removePendingFile(idx)"
            >
              <X class="w-2.5 h-2.5" />
            </button>
          </div>
        </div>

        <EditorContent :editor="editor" class="tiptap-editor" />

        <div v-if="fileUploading" class="px-3 pb-1">
          <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 class="w-3 h-3 animate-spin" />
            <span>{{ t('chat.fileUploading') }}</span>
          </div>
        </div>

        <div class="flex items-center justify-between px-2 pb-1.5">
          <div class="flex items-center gap-0.5">
            <input
              ref="fileInputRef"
              type="file"
              multiple
              class="hidden"
              @change="handleFileSelect"
            />
            <BaseTooltip :text="!store.fileUploadEnabled ? t('chat.fileUploadDisabled') : ''">
              <button
                class="p-1.5 rounded-md transition-colors"
                :class="store.fileUploadEnabled
                  ? 'text-muted-foreground hover:text-foreground hover:bg-accent'
                  : 'text-muted-foreground/40 cursor-not-allowed'"
                :disabled="!store.fileUploadEnabled"
                @click="triggerFileInput"
              >
                <Paperclip class="w-3.5 h-3.5" />
              </button>
            </BaseTooltip>
            <button
              class="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              :title="t('chat.mentionAgent')"
              @click="triggerMention"
            >
              <AtSign class="w-3.5 h-3.5" />
            </button>
            <button
              class="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              :title="t('chat.slashCommand')"
              @click="triggerSlash"
            >
              <Slash class="w-3.5 h-3.5" />
            </button>
          </div>
          <button
            class="p-1.5 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40"
            :disabled="(editorEmpty && pendingFiles.length === 0) || sending || fileUploading"
            @click="sendMessage"
          >
            <Loader2 v-if="sending || fileUploading" class="w-3.5 h-3.5 animate-spin" />
            <Send v-else class="w-3.5 h-3.5" />
          </button>
        </div>
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

.tiptap-editor :deep(.ProseMirror) {
  min-height: 2.25rem;
  max-height: 10rem;
  overflow-y: scroll;
  padding: 0.5rem 0.75rem 0.25rem;
  outline: none;
  font-size: 0.875rem;
  line-height: 1.5;
}

.tiptap-editor :deep(.ProseMirror p) {
  margin: 0;
}

.tiptap-editor :deep(.ProseMirror p.is-editor-empty:first-child::before) {
  content: attr(data-placeholder);
  color: hsl(var(--muted-foreground));
  opacity: 0.5;
  font-size: 0.8rem;
  letter-spacing: 0.01em;
  pointer-events: none;
  float: left;
  height: 0;
}

.slug-tag {
  display: inline-flex;
  align-items: center;
  position: relative;
  max-width: 140px;
  cursor: pointer;
  gap: 2px;
}
.slug-tag:hover .slug-copy-icon {
  opacity: 0.6;
}
.slug-copy-icon {
  width: 10px;
  height: 10px;
  opacity: 0;
  flex-shrink: 0;
  transition: opacity 0.15s;
  color: var(--muted-foreground);
}
.slug-text {
  display: block;
  font-size: 10px;
  padding: 2px 4px;
  border-radius: 4px;
  background: var(--muted);
  color: var(--muted-foreground);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  line-height: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.slug-tooltip {
  position: absolute;
  top: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 8px;
  border-radius: 6px;
  background: var(--popover);
  color: var(--popover-foreground);
  border: 1px solid var(--border);
  box-shadow: 0 4px 12px rgb(0 0 0 / 0.15);
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  white-space: nowrap;
  z-index: 50;
  pointer-events: none;
}
.slug-tooltip::before {
  content: '';
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-bottom-color: var(--border);
}
.slug-tooltip::after {
  content: '';
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-bottom-color: var(--popover);
}

.messages-scroll {
  overflow-y: scroll;
  overflow-x: hidden;
}

.chat-markdown {
  overflow: hidden;
  max-width: 100%;
  word-break: break-word;
}
.chat-markdown :deep(img) {
  max-width: 100%;
  height: auto;
}

.chat-markdown :deep(p) { margin: 0.25em 0; }
.chat-markdown :deep(p:first-child) { margin-top: 0; }
.chat-markdown :deep(p:last-child) { margin-bottom: 0; }
.chat-markdown :deep(ul),
.chat-markdown :deep(ol) { padding-left: 1.25em; margin: 0.25em 0; }
.chat-markdown :deep(li) { margin: 0.1em 0; }
.chat-markdown :deep(strong) { font-weight: 600; }
.chat-markdown :deep(code) {
  background: hsl(var(--primary) / 0.08);
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.85em;
}
.chat-markdown :deep(pre) {
  background: hsl(var(--primary) / 0.06);
  padding: 0.5em 0.75em;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.5em 0;
}
.chat-markdown :deep(pre code) { background: none; padding: 0; }
.chat-markdown :deep(h1),
.chat-markdown :deep(h2),
.chat-markdown :deep(h3) {
  font-weight: 600;
  margin: 0.5em 0 0.25em;
}
.chat-markdown :deep(blockquote) {
  border-left: 3px solid hsl(var(--border));
  padding-left: 0.75em;
  color: hsl(var(--muted-foreground));
  margin: 0.25em 0;
}
.chat-markdown :deep(a) {
  color: hsl(var(--primary));
  text-decoration: underline;
}
.chat-markdown :deep(a.gene-slug-link) {
  display: inline-block;
  background: color-mix(in srgb, var(--primary) 12%, transparent);
  color: var(--primary);
  padding: 0.05em 0.4em;
  border-radius: 4px;
  text-decoration: none;
  font-family: monospace;
  font-size: 0.85em;
  cursor: pointer;
}
.chat-markdown :deep(a.gene-slug-link:hover) {
  background: color-mix(in srgb, var(--primary) 20%, transparent);
  text-decoration: underline;
}

</style>
