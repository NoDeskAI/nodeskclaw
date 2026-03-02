<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft, ChevronRight, Download, File, FileCode, FileText,
  Folder, Loader2, Search, X,
} from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'

interface FileItem {
  name: string
  is_dir: boolean
  size: number
  mime_type: string | null
  modified_at: string | null
}

interface FileListing {
  instance_id: string
  instance_name: string
  path: string
  breadcrumb: string[]
  items: FileItem[]
}

const route = useRoute()
const router = useRouter()
const { t, locale } = useI18n()

const instanceId = computed(() => route.params.instanceId as string)
const currentPath = ref(route.query.path as string || '.openclaw')

const loading = ref(true)
const error = ref('')
const listing = ref<FileListing | null>(null)
const filterText = ref('')

const previewVisible = ref(false)
const previewLoading = ref(false)
const previewContent = ref('')
const previewFileName = ref('')
const previewError = ref('')
const previewTruncated = ref(false)
const previewBinary = ref(false)

const CODE_EXTENSIONS = new Set([
  'ts', 'js', 'tsx', 'jsx', 'vue', 'py', 'sh', 'bash', 'css', 'scss', 'html', 'sql',
])

const TEXT_EXTENSIONS = new Set([
  'md', 'txt', 'json', 'yaml', 'yml', 'toml', 'xml', 'csv', 'log', 'env',
  'gitignore', 'dockerfile', 'conf', 'cfg', 'ini',
])

function getFileIcon(item: FileItem) {
  if (item.is_dir) return Folder
  const ext = item.name.split('.').pop()?.toLowerCase() ?? ''
  if (CODE_EXTENSIONS.has(ext)) return FileCode
  if (TEXT_EXTENSIONS.has(ext)) return FileText
  return File
}

function isPreviewable(item: FileItem): boolean {
  if (item.is_dir) return false
  const ext = item.name.split('.').pop()?.toLowerCase() ?? ''
  return CODE_EXTENSIONS.has(ext) || TEXT_EXTENSIONS.has(ext)
}

function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  const val = bytes / Math.pow(1024, i)
  return `${val < 10 ? val.toFixed(1) : Math.round(val)} ${units[i]}`
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  const loc = locale.value === 'zh-CN' ? 'zh-CN' : 'en-US'
  return d.toLocaleDateString(loc, {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

const filteredItems = computed(() => {
  if (!listing.value) return []
  if (!filterText.value.trim()) return listing.value.items
  const q = filterText.value.toLowerCase()
  return listing.value.items.filter(i => i.name.toLowerCase().includes(q))
})

async function fetchFiles() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(
      `/enterprise-files/agents/${instanceId.value}/files`,
      { params: { path: currentPath.value } },
    )
    listing.value = data.data
  } catch (e: unknown) {
    error.value = resolveApiErrorMessage(e)
  } finally {
    loading.value = false
  }
}

function navigateTo(path: string) {
  currentPath.value = path
  filterText.value = ''
  router.replace({ query: { path } })
  fetchFiles()
}

function handleBreadcrumb(index: number) {
  if (!listing.value) return
  const parts = listing.value.breadcrumb.slice(0, index + 1)
  navigateTo(parts.join('/'))
}

function handleItemClick(item: FileItem) {
  if (item.is_dir) {
    navigateTo(`${currentPath.value}/${item.name}`)
  } else if (isPreviewable(item)) {
    openPreview(item)
  }
}

async function openPreview(item: FileItem) {
  previewVisible.value = true
  previewLoading.value = true
  previewContent.value = ''
  previewError.value = ''
  previewFileName.value = item.name
  previewTruncated.value = false
  previewBinary.value = false
  try {
    const { data } = await api.get(
      `/enterprise-files/agents/${instanceId.value}/files/content`,
      { params: { path: `${currentPath.value}/${item.name}` } },
    )
    const result = data.data
    if (result.truncated) {
      previewTruncated.value = true
    } else if (result.binary) {
      previewBinary.value = true
    } else {
      previewContent.value = result.content ?? ''
    }
  } catch (e: unknown) {
    previewError.value = resolveApiErrorMessage(e)
  } finally {
    previewLoading.value = false
  }
}

function closePreview() {
  previewVisible.value = false
}

function downloadFile(item: FileItem) {
  const filePath = `${currentPath.value}/${item.name}`
  const url = `/api/v1/enterprise-files/agents/${instanceId.value}/files/download?path=${encodeURIComponent(filePath)}`
  const token = localStorage.getItem('portal_token')
  const a = document.createElement('a')
  a.href = url
  a.download = item.name
  if (token) {
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => res.blob())
      .then(blob => {
        const blobUrl = URL.createObjectURL(blob)
        a.href = blobUrl
        a.click()
        URL.revokeObjectURL(blobUrl)
      })
  }
}

watch(() => route.query.path, (val) => {
  if (val && val !== currentPath.value) {
    currentPath.value = val as string
    fetchFiles()
  }
})

onMounted(fetchFiles)
</script>

<template>
  <div class="max-w-5xl mx-auto px-6 py-8">
    <!-- Back + Breadcrumb -->
    <div class="flex items-center gap-2 mb-4 text-sm">
      <button
        class="flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors"
        @click="router.push('/enterprise-files')"
      >
        <ArrowLeft class="w-4 h-4" />
        {{ t('enterpriseFiles.backToAgents') }}
      </button>
    </div>

    <div class="flex items-center gap-1 mb-6 text-sm flex-wrap">
      <button
        class="text-muted-foreground hover:text-foreground transition-colors"
        @click="router.push('/enterprise-files')"
      >
        {{ t('enterpriseFiles.title') }}
      </button>
      <template v-if="listing">
        <ChevronRight class="w-3 h-3 text-muted-foreground shrink-0" />
        <span class="font-medium">{{ listing.instance_name }}</span>
        <template v-for="(part, idx) in listing.breadcrumb" :key="idx">
          <ChevronRight class="w-3 h-3 text-muted-foreground shrink-0" />
          <button
            v-if="idx < listing.breadcrumb.length - 1"
            class="text-muted-foreground hover:text-foreground transition-colors"
            @click="handleBreadcrumb(idx)"
          >
            {{ part }}
          </button>
          <span v-else class="text-foreground">{{ part }}</span>
        </template>
      </template>
    </div>

    <!-- Filter -->
    <div v-if="!loading && !error && listing" class="mb-4">
      <div class="relative max-w-xs">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          v-model="filterText"
          :placeholder="t('enterpriseFiles.filterPlaceholder')"
          class="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
      <span class="ml-2 text-sm text-muted-foreground">{{ t('enterpriseFiles.loading') }}</span>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-center py-20 space-y-4">
      <p class="text-sm text-red-400">{{ error }}</p>
      <button
        class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
        @click="fetchFiles"
      >
        {{ t('instanceList.retry') }}
      </button>
    </div>

    <!-- Empty -->
    <div
      v-else-if="listing && listing.items.length === 0"
      class="text-center py-20 text-sm text-muted-foreground"
    >
      {{ t('enterpriseFiles.emptyDir') }}
    </div>

    <!-- File table -->
    <div v-else-if="listing" class="rounded-xl border border-border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border bg-card/60">
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">
              {{ t('enterpriseFiles.fileName') }}
            </th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground w-24">
              {{ t('enterpriseFiles.fileSize') }}
            </th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground w-44">
              {{ t('enterpriseFiles.fileModified') }}
            </th>
            <th class="w-20" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in filteredItems"
            :key="item.name"
            class="border-b border-border last:border-b-0 hover:bg-accent/50 transition-colors"
            :class="item.is_dir || isPreviewable(item) ? 'cursor-pointer' : ''"
            @click="handleItemClick(item)"
          >
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <component
                  :is="getFileIcon(item)"
                  class="w-4 h-4 shrink-0"
                  :class="item.is_dir ? 'text-primary' : 'text-muted-foreground'"
                />
                <span class="truncate" :class="item.is_dir ? 'font-medium' : ''">
                  {{ item.name }}
                </span>
              </div>
            </td>
            <td class="px-4 py-3 text-muted-foreground tabular-nums">
              {{ item.is_dir ? '-' : formatSize(item.size) }}
            </td>
            <td class="px-4 py-3 text-muted-foreground">
              {{ formatTime(item.modified_at) }}
            </td>
            <td class="px-4 py-3 text-right">
              <button
                v-if="!item.is_dir"
                class="p-1 rounded hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
                :title="t('enterpriseFiles.download')"
                @click.stop="downloadFile(item)"
              >
                <Download class="w-4 h-4" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Preview panel -->
    <Teleport to="body">
      <Transition name="slide-right">
        <div
          v-if="previewVisible"
          class="fixed inset-y-0 right-0 w-xl max-w-full bg-background border-l border-border shadow-xl z-50 flex flex-col"
        >
          <div class="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
            <h3 class="font-medium text-sm truncate">{{ previewFileName }}</h3>
            <button
              class="p-1 rounded hover:bg-accent transition-colors"
              @click="closePreview"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="flex-1 overflow-auto p-4">
            <div v-if="previewLoading" class="flex items-center justify-center py-10">
              <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
            <div v-else-if="previewError" class="text-sm text-red-400">{{ previewError }}</div>
            <div v-else-if="previewTruncated" class="text-sm text-muted-foreground">
              {{ t('enterpriseFiles.fileTooLarge') }}
            </div>
            <div v-else-if="previewBinary" class="text-sm text-muted-foreground">
              {{ t('enterpriseFiles.binaryFile') }}
            </div>
            <pre
              v-else
              class="text-xs leading-relaxed font-mono whitespace-pre-wrap break-all text-foreground"
            >{{ previewContent }}</pre>
          </div>
        </div>
      </Transition>
      <Transition name="fade">
        <div
          v-if="previewVisible"
          class="fixed inset-0 bg-black/30 z-40"
          @click="closePreview"
        />
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.slide-right-enter-active,
.slide-right-leave-active {
  transition: transform 0.25s ease;
}
.slide-right-enter-from,
.slide-right-leave-to {
  transform: translateX(100%);
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
