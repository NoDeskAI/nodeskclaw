<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import { Folder, File, FolderPlus, Upload, Trash2, Download, Loader2, ChevronRight } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import api from '@/services/api'

const props = defineProps<{ workspaceId: string }>()
const { t } = useI18n()

interface FileItem {
  id: string
  name: string
  is_directory: boolean
  file_size: number
  content_type: string
  uploader_name: string
  created_at: string
}

const currentPath = ref('/')
const files = ref<FileItem[]>([])
const loading = ref(false)
const showMkdir = ref(false)
const newDirName = ref('')
const creating = ref(false)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const breadcrumbs = computed(() => {
  const parts = currentPath.value.split('/').filter(Boolean)
  const crumbs = [{ name: '/', path: '/' }]
  let acc = '/'
  for (const p of parts) {
    acc += p + '/'
    crumbs.push({ name: p, path: acc })
  }
  return crumbs
})

async function fetchFiles() {
  loading.value = true
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files`, {
      params: { parent_path: currentPath.value },
    })
    files.value = res.data.data || []
  } catch (e) {
    console.error('fetch files error:', e)
  } finally {
    loading.value = false
  }
}

function navigate(item: FileItem) {
  if (item.is_directory) {
    currentPath.value = currentPath.value + item.name + '/'
    fetchFiles()
  }
}

function navigateTo(path: string) {
  currentPath.value = path
  fetchFiles()
}

async function mkdir() {
  if (!newDirName.value.trim()) return
  creating.value = true
  try {
    await api.post(`/workspaces/${props.workspaceId}/blackboard/files/mkdir`, {
      parent_path: currentPath.value,
      name: newDirName.value.trim(),
    })
    showMkdir.value = false
    newDirName.value = ''
    await fetchFiles()
  } catch (e) {
    console.error('mkdir error:', e)
  } finally {
    creating.value = false
  }
}

async function uploadFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  try {
    const reader = new FileReader()
    const b64 = await new Promise<string>((resolve) => {
      reader.onload = () => {
        const result = reader.result as string
        resolve(result.split(',')[1] || '')
      }
      reader.readAsDataURL(file)
    })
    await api.post(`/workspaces/${props.workspaceId}/blackboard/files/upload`, {
      parent_path: currentPath.value,
      filename: file.name,
      content: b64,
      content_type: file.type || 'application/octet-stream',
    })
    await fetchFiles()
  } catch (e) {
    console.error('upload error:', e)
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function downloadFile(item: FileItem) {
  try {
    const res = await api.get(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}/url`)
    const url = res.data.data?.url
    if (url) window.open(url, '_blank')
  } catch (e) {
    console.error('download error:', e)
  }
}

async function deleteFile(item: FileItem) {
  try {
    await api.delete(`/workspaces/${props.workspaceId}/blackboard/files/${item.id}`)
    await fetchFiles()
  } catch (e) {
    console.error('delete error:', e)
  }
}

function formatSize(bytes: number) {
  if (bytes === 0) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

onMounted(fetchFiles)
watch(() => props.workspaceId, () => { currentPath.value = '/'; fetchFiles() })
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-0.5 text-sm text-muted-foreground overflow-x-auto">
        <button
          v-for="(crumb, idx) in breadcrumbs"
          :key="crumb.path"
          class="flex items-center gap-0.5 hover:text-foreground transition-colors shrink-0"
          @click="navigateTo(crumb.path)"
        >
          <ChevronRight v-if="idx > 0" class="w-3 h-3" />
          <span class="text-xs">{{ crumb.name }}</span>
        </button>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <button
          class="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg hover:bg-muted transition-colors"
          @click="showMkdir = !showMkdir"
        >
          <FolderPlus class="w-3.5 h-3.5" />
        </button>
        <button
          class="flex items-center gap-1 text-xs px-2 py-1.5 rounded-lg hover:bg-muted transition-colors"
          :disabled="uploading"
          @click="fileInputRef?.click()"
        >
          <Loader2 v-if="uploading" class="w-3.5 h-3.5 animate-spin" />
          <Upload v-else class="w-3.5 h-3.5" />
        </button>
        <input ref="fileInputRef" type="file" class="hidden" @change="uploadFile" />
      </div>
    </div>

    <div v-if="showMkdir" class="flex items-center gap-2">
      <input
        v-model="newDirName"
        class="flex-1 bg-background border border-border rounded px-2.5 py-1.5 text-sm outline-none focus:ring-1 focus:ring-primary/50"
        :placeholder="t('blackboard.dirNamePlaceholder')"
        @keydown.enter="mkdir"
      />
      <button
        class="px-2.5 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
        :disabled="creating || !newDirName.trim()"
        @click="mkdir"
      >
        {{ t('blackboard.create') }}
      </button>
    </div>

    <div v-if="loading && files.length === 0" class="flex items-center justify-center py-8">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="files.length === 0" class="text-sm text-muted-foreground py-6 text-center">
      {{ t('blackboard.noFiles') }}
    </div>

    <div v-else class="space-y-0.5">
      <div
        v-for="item in files"
        :key="item.id"
        class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted/50 transition-colors group"
        :class="item.is_directory ? 'cursor-pointer' : ''"
        @click="item.is_directory && navigate(item)"
      >
        <Folder v-if="item.is_directory" class="w-4 h-4 text-primary shrink-0" />
        <File v-else class="w-4 h-4 text-muted-foreground shrink-0" />
        <span class="text-sm flex-1 truncate">{{ item.name }}</span>
        <span class="text-xs text-muted-foreground shrink-0">{{ formatSize(item.file_size) }}</span>
        <span class="text-xs text-muted-foreground shrink-0 hidden sm:inline">{{ item.uploader_name }}</span>
        <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            v-if="!item.is_directory"
            class="p-1 rounded hover:bg-muted transition-colors"
            @click.stop="downloadFile(item)"
          >
            <Download class="w-3.5 h-3.5" />
          </button>
          <button
            class="p-1 rounded hover:bg-destructive/20 text-destructive transition-colors"
            @click.stop="deleteFile(item)"
          >
            <Trash2 class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
