<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { Plus, Pin, MessageSquare, ChevronLeft, ChevronRight, Loader2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import api from '@/services/api'

const props = defineProps<{ workspaceId: string }>()
const emit = defineEmits<{ (e: 'select', postId: string): void }>()
const { t } = useI18n()

interface PostItem {
  id: string
  title: string
  author_type: string
  author_name: string
  is_pinned: boolean
  reply_count: number
  created_at: string
  last_reply_at: string | null
}

const posts = ref<PostItem[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const showCreate = ref(false)
const newTitle = ref('')
const newContent = ref('')
const creating = ref(false)

async function fetchPosts() {
  loading.value = true
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/posts`, {
      params: { page: page.value, size: 20 },
    })
    posts.value = res.data.data?.items || []
    total.value = res.data.data?.total || 0
  } catch (e) {
    console.error('fetch posts error:', e)
  } finally {
    loading.value = false
  }
}

async function createPost() {
  if (!newTitle.value.trim() || !newContent.value.trim()) return
  creating.value = true
  try {
    await api.post(`/workspaces/${props.workspaceId}/blackboard/posts`, {
      title: newTitle.value.trim(),
      content: newContent.value.trim(),
    })
    showCreate.value = false
    newTitle.value = ''
    newContent.value = ''
    page.value = 1
    await fetchPosts()
  } catch (e) {
    console.error('create post error:', e)
  } finally {
    creating.value = false
  }
}

const totalPages = ref(0)
watch(total, (t) => { totalPages.value = Math.ceil(t / 20) })

function formatTime(ts: string | null) {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchPosts)
watch(() => props.workspaceId, fetchPosts)
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="text-sm font-medium text-muted-foreground">{{ t('blackboard.posts') }}</h3>
      <button
        class="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        @click="showCreate = !showCreate"
      >
        <Plus class="w-3.5 h-3.5" />
        {{ t('blackboard.newPost') }}
      </button>
    </div>

    <div v-if="showCreate" class="border border-border rounded-lg p-3 space-y-2 bg-muted/30">
      <input
        v-model="newTitle"
        class="w-full bg-background border border-border rounded px-3 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
        :placeholder="t('blackboard.postTitlePlaceholder')"
      />
      <textarea
        v-model="newContent"
        rows="4"
        class="w-full bg-background border border-border rounded px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-primary/50 resize-none font-mono"
        :placeholder="t('blackboard.postContentPlaceholder')"
      />
      <div class="flex justify-end gap-2">
        <button
          class="px-3 py-1.5 text-xs rounded-lg bg-muted hover:bg-muted/80 transition-colors"
          @click="showCreate = false"
        >
          {{ t('blackboard.cancel') }}
        </button>
        <button
          class="px-3 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1 disabled:opacity-50"
          :disabled="creating || !newTitle.trim() || !newContent.trim()"
          @click="createPost"
        >
          <Loader2 v-if="creating" class="w-3.5 h-3.5 animate-spin" />
          {{ t('blackboard.publish') }}
        </button>
      </div>
    </div>

    <div v-if="loading && posts.length === 0" class="flex items-center justify-center py-8">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="posts.length === 0" class="text-sm text-muted-foreground py-6 text-center">
      {{ t('blackboard.noPosts') }}
    </div>

    <div v-else class="space-y-1.5">
      <button
        v-for="post in posts"
        :key="post.id"
        class="w-full text-left px-3 py-2.5 rounded-lg bg-muted/40 hover:bg-muted/70 transition-colors"
        @click="emit('select', post.id)"
      >
        <div class="flex items-center gap-2">
          <Pin v-if="post.is_pinned" class="w-3.5 h-3.5 text-primary shrink-0" />
          <span class="text-sm font-medium truncate flex-1">{{ post.title }}</span>
          <span class="flex items-center gap-0.5 text-xs text-muted-foreground shrink-0">
            <MessageSquare class="w-3 h-3" />
            {{ post.reply_count }}
          </span>
        </div>
        <div class="flex items-center justify-between mt-1 text-xs text-muted-foreground">
          <span>{{ post.author_name }}</span>
          <span>{{ formatTime(post.last_reply_at || post.created_at) }}</span>
        </div>
      </button>
    </div>

    <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 pt-2">
      <button
        class="p-1 rounded hover:bg-muted transition-colors disabled:opacity-30"
        :disabled="page <= 1"
        @click="page--; fetchPosts()"
      >
        <ChevronLeft class="w-4 h-4" />
      </button>
      <span class="text-xs text-muted-foreground">{{ page }} / {{ totalPages }}</span>
      <button
        class="p-1 rounded hover:bg-muted transition-colors disabled:opacity-30"
        :disabled="page >= totalPages"
        @click="page++; fetchPosts()"
      >
        <ChevronRight class="w-4 h-4" />
      </button>
    </div>
  </div>
</template>
