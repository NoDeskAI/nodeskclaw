<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { ArrowLeft, Send, Loader2, Pin, PinOff } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import api from '@/services/api'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ workspaceId: string; postId: string }>()
const emit = defineEmits<{ (e: 'back'): void }>()
const { t } = useI18n()

interface ReplyItem {
  id: string
  content: string
  author_type: string
  author_id: string
  author_name: string
  created_at: string
}

interface PostData {
  id: string
  title: string
  content: string
  author_type: string
  author_id: string
  author_name: string
  is_pinned: boolean
  reply_count: number
  replies: ReplyItem[]
  created_at: string
}

const post = ref<PostData | null>(null)
const loading = ref(false)
const replyContent = ref('')
const replying = ref(false)

async function fetchPost() {
  loading.value = true
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/posts/${props.postId}`)
    post.value = res.data.data
    await api.post(`/workspaces/${props.workspaceId}/blackboard/posts/${props.postId}/read`)
  } catch (e) {
    console.error('fetch post error:', e)
  } finally {
    loading.value = false
  }
}

async function sendReply() {
  if (!replyContent.value.trim()) return
  replying.value = true
  try {
    await api.post(`/workspaces/${props.workspaceId}/blackboard/posts/${props.postId}/replies`, {
      content: replyContent.value.trim(),
    })
    replyContent.value = ''
    await fetchPost()
  } catch (e) {
    console.error('reply error:', e)
  } finally {
    replying.value = false
  }
}

async function togglePin() {
  if (!post.value) return
  const method = post.value.is_pinned ? 'delete' : 'post'
  try {
    await api[method](`/workspaces/${props.workspaceId}/blackboard/posts/${props.postId}/pin`)
    post.value.is_pinned = !post.value.is_pinned
  } catch (e) {
    console.error('pin error:', e)
  }
}

function renderMd(raw: string) {
  return renderMarkdown(raw)
}

function formatTime(ts: string) {
  const d = new Date(ts)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchPost)
watch(() => props.postId, fetchPost)
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="flex items-center gap-2 pb-3 border-b border-border shrink-0">
      <button class="p-1 rounded hover:bg-muted transition-colors" @click="emit('back')">
        <ArrowLeft class="w-4 h-4" />
      </button>
      <span v-if="post" class="text-sm font-medium truncate flex-1">{{ post.title }}</span>
      <button
        v-if="post"
        class="p-1 rounded hover:bg-muted transition-colors"
        :title="post.is_pinned ? t('blackboard.unpin') : t('blackboard.pin')"
        @click="togglePin"
      >
        <PinOff v-if="post.is_pinned" class="w-4 h-4 text-primary" />
        <Pin v-else class="w-4 h-4" />
      </button>
    </div>

    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="post" class="flex-1 overflow-y-auto min-h-0 py-3 space-y-4">
      <div>
        <div class="flex items-center justify-between text-xs text-muted-foreground mb-2">
          <span>{{ post.author_name }}</span>
          <span>{{ formatTime(post.created_at) }}</span>
        </div>
        <div class="prose prose-sm prose-invert max-w-none" v-html="renderMd(post.content)" />
      </div>

      <div v-if="post.replies.length > 0" class="border-t border-border pt-3 space-y-3">
        <h4 class="text-xs font-medium text-muted-foreground">
          {{ t('blackboard.replies') }} ({{ post.replies.length }})
        </h4>
        <div
          v-for="reply in post.replies"
          :key="reply.id"
          class="pl-3 border-l-2 border-border"
        >
          <div class="flex items-center justify-between text-xs text-muted-foreground mb-1">
            <span>{{ reply.author_name }}</span>
            <span>{{ formatTime(reply.created_at) }}</span>
          </div>
          <div class="prose prose-sm prose-invert max-w-none text-sm" v-html="renderMd(reply.content)" />
        </div>
      </div>
    </div>

    <div class="border-t border-border pt-3 shrink-0">
      <div class="flex items-end gap-2">
        <textarea
          v-model="replyContent"
          rows="2"
          class="flex-1 bg-muted rounded-lg px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50 resize-none"
          :placeholder="t('blackboard.replyPlaceholder')"
          @keydown.meta.enter="sendReply"
          @keydown.ctrl.enter="sendReply"
        />
        <button
          class="p-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 shrink-0"
          :disabled="replying || !replyContent.trim()"
          @click="sendReply"
        >
          <Loader2 v-if="replying" class="w-4 h-4 animate-spin" />
          <Send v-else class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
