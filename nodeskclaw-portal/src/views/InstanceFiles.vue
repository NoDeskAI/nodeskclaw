<script setup lang="ts">
import { ref, onMounted, computed, watch, inject, type Ref, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ChevronRight, Download, File, FileCode, FileText,
  Folder, Loader2, Pencil, Save, Search, X,
} from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useToast } from '@/composables/useToast'
import { getRuntimeCaps } from '@/utils/runtimeCapabilities'

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

const instanceId = inject<Ref<string>>('instanceId')!
const instanceRuntime = inject<ComputedRef<string>>('instanceRuntime', computed(() => 'openclaw'))
const { t, locale } = useI18n()
const toast = useToast()

const dataRoot = computed(() => getRuntimeCaps(instanceRuntime.value).dataRoot)
const currentPath = ref('.openclaw')
const loading = ref(true)
const error = ref('')
const listing = ref<FileListing | null>(null)
const filterText = ref('')

const panelVisible = ref(false)
const panelLoading = ref(false)
const panelContent = ref('')
const panelOriginalContent = ref('')
const panelFileName = ref('')
const panelFilePath = ref('')
const panelError = ref('')
const panelTruncated = ref(false)
const panelBinary = ref(false)
const editing = ref(false)
const saving = ref(false)
const confirmVisible = ref(false)

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

const hasUnsavedChanges = computed(() => editing.value && panelContent.value !== panelOriginalContent.value)

watch(dataRoot, (root) => {
  if (currentPath.value === '.openclaw' || !currentPath.value) {
    currentPath.value = root
    fetchFiles()
  }
}, { immediate: true })

function breadcrumbLabel(part: string): string {
  return part === dataRoot.value ? t('instanceFiles.workspaceRoot') : part
}

async function fetchFiles() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(
      `/instances/${instanceId.value}/files`,
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
    openPanel(item)
  }
}

async function openPanel(item: FileItem) {
  panelVisible.value = true
  panelLoading.value = true
  panelContent.value = ''
  panelOriginalContent.value = ''
  panelError.value = ''
  panelFileName.value = item.name
  panelFilePath.value = `${currentPath.value}/${item.name}`
  panelTruncated.value = false
  panelBinary.value = false
  editing.value = false
  try {
    const { data } = await api.get(
      `/instances/${instanceId.value}/files/content`,
      { params: { path: panelFilePath.value } },
    )
    const result = data.data
    if (result.truncated) {
      panelTruncated.value = true
    } else if (result.binary) {
      panelBinary.value = true
    } else {
      panelContent.value = result.content ?? ''
      panelOriginalContent.value = panelContent.value
    }
  } catch (e: unknown) {
    panelError.value = resolveApiErrorMessage(e)
  } finally {
    panelLoading.value = false
  }
}

function closePanel() {
  panelVisible.value = false
  editing.value = false
}

function startEdit() {
  editing.value = true
}

function cancelEdit() {
  panelContent.value = panelOriginalContent.value
  editing.value = false
}

function requestSave() {
  confirmVisible.value = true
}

async function confirmSave() {
  confirmVisible.value = false
  saving.value = true
  try {
    await api.put(`/instances/${instanceId.value}/files/content`, {
      path: panelFilePath.value,
      content: panelContent.value,
    })
    panelOriginalContent.value = panelContent.value
    editing.value = false
    toast.success(t('instanceFiles.saveSuccess'))
    fetchFiles()
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('instanceFiles.saveFailed')))
  } finally {
    saving.value = false
  }
}

function cancelConfirm() {
  confirmVisible.value = false
}

async function downloadFile(item: FileItem) {
  const filePath = `${currentPath.value}/${item.name}`
  const url = `/api/v1/instances/${instanceId.value}/files/download?path=${encodeURIComponent(filePath)}`
  const token = localStorage.getItem('portal_token')
  if (!token) return
  try {
    const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) {
      const data = await res.json().catch(() => ({}))
      toast.error(data.message || t('instanceFiles.downloadFailed'))
      return
    }
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = blobUrl
    a.download = item.name
    a.click()
    URL.revokeObjectURL(blobUrl)
  } catch {
    toast.error(t('instanceFiles.downloadFailed'))
  }
}

onMounted(fetchFiles)
</script>

<template>
  <div>
    <!-- Breadcrumb -->
    <div class="flex items-center gap-1 mb-6 text-sm flex-wrap">
      <template v-if="listing">
        <template v-for="(part, idx) in listing.breadcrumb" :key="idx">
          <ChevronRight v-if="idx > 0" class="w-3 h-3 text-muted-foreground shrink-0" />
          <button
            v-if="idx < listing.breadcrumb.length - 1"
            class="text-muted-foreground hover:text-foreground transition-colors"
            @click="handleBreadcrumb(idx)"
          >
            {{ breadcrumbLabel(part) }}
          </button>
          <span v-else class="text-foreground font-medium">{{ breadcrumbLabel(part) }}</span>
        </template>
      </template>
    </div>

    <!-- Filter -->
    <div v-if="!loading && !error && listing" class="mb-4">
      <div class="relative max-w-xs">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          v-model="filterText"
          :placeholder="t('instanceFiles.filterPlaceholder')"
          class="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
      <span class="ml-2 text-sm text-muted-foreground">{{ t('instanceFiles.loading') }}</span>
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
      {{ t('instanceFiles.emptyDir') }}
    </div>

    <!-- File table -->
    <div v-else-if="listing" class="rounded-xl border border-border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border bg-card/60">
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">
              {{ t('instanceFiles.fileName') }}
            </th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground w-24">
              {{ t('instanceFiles.fileSize') }}
            </th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground w-44">
              {{ t('instanceFiles.fileModified') }}
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
                :title="t('instanceFiles.download')"
                @click.stop="downloadFile(item)"
              >
                <Download class="w-4 h-4" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Side panel (preview + edit) -->
    <Teleport to="body">
      <Transition name="slide-right">
        <div
          v-if="panelVisible"
          class="fixed inset-y-0 right-0 w-xl max-w-full bg-background border-l border-border shadow-xl z-50 flex flex-col"
        >
          <!-- Panel header -->
          <div class="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
            <div class="flex items-center gap-2 min-w-0">
              <h3 class="font-medium text-sm truncate">{{ panelFileName }}</h3>
              <span
                v-if="editing"
                class="text-xs px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500"
              >{{ t('instanceFiles.editing') }}</span>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <template v-if="!panelLoading && !panelTruncated && !panelBinary && !panelError">
                <template v-if="editing">
                  <button
                    class="px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-accent transition-colors"
                    @click="cancelEdit"
                  >{{ t('instanceFiles.cancelEdit') }}</button>
                  <button
                    class="px-3 py-1.5 rounded-lg text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors flex items-center gap-1 disabled:opacity-50"
                    :disabled="!hasUnsavedChanges || saving"
                    @click="requestSave"
                  >
                    <Loader2 v-if="saving" class="w-3 h-3 animate-spin" />
                    <Save v-else class="w-3 h-3" />
                    {{ t('instanceFiles.save') }}
                  </button>
                </template>
                <button
                  v-else
                  class="px-3 py-1.5 rounded-lg text-xs border border-border hover:bg-accent transition-colors flex items-center gap-1"
                  @click="startEdit"
                >
                  <Pencil class="w-3 h-3" />
                  {{ t('instanceFiles.edit') }}
                </button>
              </template>
              <button
                class="p-1 rounded hover:bg-accent transition-colors ml-1"
                @click="closePanel"
              >
                <X class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- Panel body -->
          <div class="flex-1 overflow-auto p-4">
            <div v-if="panelLoading" class="flex items-center justify-center py-10">
              <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
            </div>
            <div v-else-if="panelError" class="text-sm text-red-400">{{ panelError }}</div>
            <div v-else-if="panelTruncated" class="text-sm text-muted-foreground">
              {{ t('instanceFiles.fileTooLarge') }}
            </div>
            <div v-else-if="panelBinary" class="text-sm text-muted-foreground">
              {{ t('instanceFiles.binaryFile') }}
            </div>
            <textarea
              v-else-if="editing"
              v-model="panelContent"
              class="w-full h-full min-h-[60vh] text-xs leading-relaxed font-mono whitespace-pre bg-transparent text-foreground resize-none focus:outline-none"
            />
            <pre
              v-else
              class="text-xs leading-relaxed font-mono whitespace-pre-wrap break-all text-foreground"
            >{{ panelContent }}</pre>
          </div>
        </div>
      </Transition>
      <Transition name="fade">
        <div
          v-if="panelVisible"
          class="fixed inset-0 bg-black/30 z-40"
          @click="closePanel"
        />
      </Transition>
    </Teleport>

    <!-- Save confirmation dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="confirmVisible" class="fixed inset-0 z-60 flex items-center justify-center">
          <div class="fixed inset-0 bg-black/50" @click="cancelConfirm" />
          <div class="relative bg-background border border-border rounded-xl shadow-2xl max-w-md w-full mx-4 p-6">
            <h3 class="text-base font-semibold mb-3">{{ t('instanceFiles.confirmTitle') }}</h3>
            <p class="text-sm text-muted-foreground mb-2">
              {{ t('instanceFiles.confirmMessage', { path: panelFilePath }) }}
            </p>
            <div class="flex justify-end gap-2 mt-6">
              <button
                class="px-4 py-2 rounded-lg text-sm border border-border hover:bg-accent transition-colors"
                @click="cancelConfirm"
              >{{ t('common.cancel') }}</button>
              <button
                class="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                @click="confirmSave"
              >{{ t('instanceFiles.confirmSave') }}</button>
            </div>
          </div>
        </div>
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
