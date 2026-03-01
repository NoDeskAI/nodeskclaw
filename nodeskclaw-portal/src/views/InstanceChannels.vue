<script setup lang="ts">
import { ref, computed, watch, inject, type ComputedRef } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  Loader2, Radio, RefreshCw, Save, Trash2, Plus, ChevronDown, ChevronUp,
  Upload, Package, FolderGit2, AlertCircle, Check, Eye, EyeOff,
} from 'lucide-vue-next'
import api from '@/services/api'

const { t } = useI18n()
const instanceId = inject<ComputedRef<string>>('instanceId')!

interface SchemaField {
  key: string
  label: string
  type: string
  required: boolean
  placeholder?: string
  default?: string | boolean | null
  options?: { value: string; label: string }[]
}

interface AvailableChannel {
  id: string
  label: string
  description: string
  origin: string
  order: number
  has_schema: boolean
  schema?: SchemaField[]
}

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const successMsg = ref('')
const dirty = ref(false)

const availableChannels = ref<AvailableChannel[]>([])
const channelConfigs = ref<Record<string, Record<string, any>>>({})
const expandedChannels = ref<Set<string>>(new Set())
const editingConfigs = ref<Record<string, Record<string, any>>>({})
const visibleSecrets = ref<Set<string>>(new Set())

const customInstallOpen = ref(false)
const npmPackageName = ref('')
const npmInstalling = ref(false)
const uploadingFile = ref(false)
const deployingRepo = ref(false)

const SENSITIVE_KEYS = new Set([
  'appSecret', 'botToken', 'appToken', 'token', 'appPassword',
  'accessToken', 'encryptKey', 'verificationToken', 'apiKey',
  'serviceAccountKeyFile',
])

const configuredChannels = computed(() =>
  availableChannels.value.filter(ch => ch.id in channelConfigs.value)
)

const unconfiguredChannels = computed(() =>
  availableChannels.value.filter(ch => !(ch.id in channelConfigs.value))
)

function toggleExpand(channelId: string) {
  if (expandedChannels.value.has(channelId)) {
    expandedChannels.value.delete(channelId)
  } else {
    expandedChannels.value.add(channelId)
    if (!editingConfigs.value[channelId]) {
      editingConfigs.value[channelId] = { ...(channelConfigs.value[channelId] || {}) }
    }
  }
}

function toggleSecretVisibility(fieldKey: string) {
  if (visibleSecrets.value.has(fieldKey)) {
    visibleSecrets.value.delete(fieldKey)
  } else {
    visibleSecrets.value.add(fieldKey)
  }
}

function startConfiguring(channel: AvailableChannel) {
  if (!editingConfigs.value[channel.id]) {
    const defaults: Record<string, any> = {}
    if (channel.schema) {
      for (const field of channel.schema) {
        if (field.default !== undefined && field.default !== null) {
          defaults[field.key] = field.default
        }
      }
    }
    editingConfigs.value[channel.id] = defaults
  }
  if (!(channel.id in channelConfigs.value)) {
    channelConfigs.value[channel.id] = {}
  }
  expandedChannels.value.add(channel.id)
  dirty.value = true
}

function removeChannel(channelId: string) {
  delete channelConfigs.value[channelId]
  delete editingConfigs.value[channelId]
  expandedChannels.value.delete(channelId)
  dirty.value = true
}

function markDirty() {
  dirty.value = true
}

// JSON editor state for channels without schema
const jsonEditorValues = ref<Record<string, string>>({})
const jsonEditorErrors = ref<Record<string, string>>({})

function getJsonEditorValue(channelId: string): string {
  if (!(channelId in jsonEditorValues.value)) {
    jsonEditorValues.value[channelId] = JSON.stringify(
      editingConfigs.value[channelId] || {}, null, 2
    )
  }
  return jsonEditorValues.value[channelId]
}

function updateJsonEditor(channelId: string, value: string) {
  jsonEditorValues.value[channelId] = value
  jsonEditorErrors.value[channelId] = ''
  try {
    const parsed = JSON.parse(value)
    editingConfigs.value[channelId] = parsed
    markDirty()
  } catch {
    jsonEditorErrors.value[channelId] = 'JSON 格式错误'
  }
}

async function loadAll() {
  loading.value = true
  error.value = ''
  successMsg.value = ''

  try {
    const [channelsRes, configsRes] = await Promise.all([
      api.get(`/instances/${instanceId.value}/available-channels`),
      api.get(`/instances/${instanceId.value}/channel-configs`),
    ])

    availableChannels.value = channelsRes.data.data ?? []
    channelConfigs.value = configsRes.data.data ?? {}

    editingConfigs.value = {}
    for (const [cid, cfg] of Object.entries(channelConfigs.value)) {
      editingConfigs.value[cid] = { ...(cfg as Record<string, any>) }
    }

    jsonEditorValues.value = {}
    jsonEditorErrors.value = {}
    dirty.value = false
  } catch (e: any) {
    error.value = e?.response?.data?.message || t('channel.loadFailed')
  } finally {
    loading.value = false
  }
}

function buildSavePayload(): Record<string, Record<string, any>> {
  const configs: Record<string, Record<string, any>> = {}

  for (const [cid, editing] of Object.entries(editingConfigs.value)) {
    if (!expandedChannels.value.has(cid) && !(cid in channelConfigs.value)) continue

    const existing = channelConfigs.value[cid] || {}
    const merged: Record<string, any> = {}

    for (const [k, v] of Object.entries(editing)) {
      if (typeof v === 'string' && v.includes('***') && existing[k]) {
        merged[k] = existing[k]
      } else if (v !== undefined && v !== '') {
        merged[k] = v
      }
    }

    if (Object.keys(merged).length > 0 || cid in channelConfigs.value) {
      configs[cid] = merged
    }
  }

  for (const cid of Object.keys(channelConfigs.value)) {
    if (!(cid in configs) && !(cid in editingConfigs.value)) {
      configs[cid] = channelConfigs.value[cid]
    }
  }

  return configs
}

async function handleSave() {
  saving.value = true
  error.value = ''
  successMsg.value = ''

  try {
    const configs = buildSavePayload()
    const res = await api.put(`/instances/${instanceId.value}/channel-configs`, {
      configs,
    }, { timeout: 120000 })

    const result = res.data.data
    if (result?.status === 'ok') {
      successMsg.value = t('channel.saveSuccess')
    } else if (result?.status === 'timeout') {
      successMsg.value = t('channel.restartTimeout')
    } else {
      successMsg.value = t('channel.saved')
    }

    dirty.value = false
    await loadAll()
  } catch (e: any) {
    error.value = e?.response?.data?.message || t('channel.saveFailed')
  } finally {
    saving.value = false
  }
}

async function handleInstallNpm() {
  if (!npmPackageName.value.trim()) return
  npmInstalling.value = true
  error.value = ''

  try {
    await api.post(`/instances/${instanceId.value}/channels/install`, {
      package_name: npmPackageName.value.trim(),
    }, { timeout: 120000 })
    successMsg.value = t('channel.installSuccess')
    npmPackageName.value = ''
    await loadAll()
  } catch (e: any) {
    error.value = e?.response?.data?.message || t('channel.installFailed')
  } finally {
    npmInstalling.value = false
  }
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  uploadingFile.value = true
  error.value = ''

  try {
    const formData = new FormData()
    formData.append('file', input.files[0])
    await api.post(
      `/instances/${instanceId.value}/channels/upload`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 },
    )
    successMsg.value = t('channel.uploadSuccess')
    await loadAll()
  } catch (e: any) {
    error.value = e?.response?.data?.message || t('channel.uploadFailed')
  } finally {
    uploadingFile.value = false
    input.value = ''
  }
}

watch(() => instanceId.value, (val) => {
  if (val) loadAll()
}, { immediate: true })
</script>

<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="space-y-6">
      <!-- Header -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Radio class="w-4 h-4 text-blue-400" />
          <h2 class="text-sm font-medium">{{ t('channel.title') }}</h2>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-xs hover:bg-card transition-colors"
            :disabled="saving"
            @click="loadAll"
          >
            <RefreshCw class="w-3 h-3" />
            {{ t('channel.refresh') }}
          </button>
          <button
            v-if="dirty"
            :disabled="saving"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            @click="handleSave"
          >
            <Loader2 v-if="saving" class="w-3 h-3 animate-spin" />
            <Save v-else class="w-3 h-3" />
            {{ saving ? t('channel.saving') : t('channel.saveAndRestart') }}
          </button>
        </div>
      </div>

      <!-- Status messages -->
      <div v-if="saving" class="flex items-center gap-3 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20">
        <RefreshCw class="w-4 h-4 text-amber-500 animate-spin" />
        <span class="text-xs">{{ t('channel.restartingHint') }}</span>
      </div>
      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
      <p v-if="successMsg" class="text-sm text-green-500">{{ successMsg }}</p>

      <!-- Configured channels -->
      <div v-if="configuredChannels.length > 0" class="space-y-3">
        <p class="text-xs text-muted-foreground font-medium">{{ t('channel.configured') }}</p>
        <div
          v-for="ch in configuredChannels"
          :key="ch.id"
          class="rounded-lg border border-border bg-card overflow-hidden"
        >
          <!-- Channel header -->
          <div
            class="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
            @click="toggleExpand(ch.id)"
          >
            <div class="flex items-center gap-3">
              <div class="w-2 h-2 rounded-full bg-green-400"></div>
              <span class="font-medium text-sm">{{ ch.label }}</span>
              <span class="text-[10px] text-muted-foreground bg-muted/50 px-1.5 py-0.5 rounded">
                {{ ch.origin }}
              </span>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="text-muted-foreground hover:text-destructive transition-colors p-1"
                @click.stop="removeChannel(ch.id)"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
              <ChevronUp v-if="expandedChannels.has(ch.id)" class="w-4 h-4 text-muted-foreground" />
              <ChevronDown v-else class="w-4 h-4 text-muted-foreground" />
            </div>
          </div>

          <!-- Config form -->
          <div v-if="expandedChannels.has(ch.id)" class="px-4 pb-4 pt-1 border-t border-border space-y-3">
            <template v-if="ch.schema && ch.schema.length > 0">
              <div v-for="field in ch.schema" :key="field.key" class="space-y-1">
                <label class="text-xs text-muted-foreground">
                  {{ field.label }}
                  <span v-if="field.required" class="text-destructive">*</span>
                </label>

                <!-- Select -->
                <select
                  v-if="field.type === 'select'"
                  :value="editingConfigs[ch.id]?.[field.key] ?? field.default ?? ''"
                  class="w-full px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  @change="editingConfigs[ch.id][field.key] = ($event.target as HTMLSelectElement).value; markDirty()"
                >
                  <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>

                <!-- Boolean -->
                <label v-else-if="field.type === 'boolean'" class="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    :checked="editingConfigs[ch.id]?.[field.key] ?? field.default ?? false"
                    class="accent-primary"
                    @change="editingConfigs[ch.id][field.key] = ($event.target as HTMLInputElement).checked; markDirty()"
                  />
                  <span class="text-sm">{{ editingConfigs[ch.id]?.[field.key] ? t('channel.enabled') : t('channel.disabled') }}</span>
                </label>

                <!-- Password -->
                <div v-else-if="field.type === 'password'" class="relative">
                  <input
                    :type="visibleSecrets.has(`${ch.id}.${field.key}`) ? 'text' : 'password'"
                    :value="editingConfigs[ch.id]?.[field.key] ?? ''"
                    :placeholder="field.placeholder || ''"
                    class="w-full px-3 py-1.5 pr-9 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                    @input="editingConfigs[ch.id][field.key] = ($event.target as HTMLInputElement).value; markDirty()"
                  />
                  <button
                    class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    @click="toggleSecretVisibility(`${ch.id}.${field.key}`)"
                  >
                    <EyeOff v-if="visibleSecrets.has(`${ch.id}.${field.key}`)" class="w-3.5 h-3.5" />
                    <Eye v-else class="w-3.5 h-3.5" />
                  </button>
                </div>

                <!-- String (default) -->
                <input
                  v-else
                  type="text"
                  :value="editingConfigs[ch.id]?.[field.key] ?? ''"
                  :placeholder="field.placeholder || ''"
                  class="w-full px-3 py-1.5 rounded-md bg-background border border-border text-sm focus:outline-none focus:ring-1 focus:ring-primary/50"
                  @input="editingConfigs[ch.id][field.key] = ($event.target as HTMLInputElement).value; markDirty()"
                />
              </div>
            </template>

            <!-- JSON editor fallback -->
            <template v-else>
              <p class="text-xs text-muted-foreground">{{ t('channel.jsonEditorHint') }}</p>
              <textarea
                :value="getJsonEditorValue(ch.id)"
                rows="8"
                class="w-full px-3 py-2 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50 resize-y"
                @input="updateJsonEditor(ch.id, ($event.target as HTMLTextAreaElement).value)"
              ></textarea>
              <p v-if="jsonEditorErrors[ch.id]" class="text-xs text-destructive flex items-center gap-1">
                <AlertCircle class="w-3 h-3" />
                {{ jsonEditorErrors[ch.id] }}
              </p>
            </template>
          </div>
        </div>
      </div>

      <!-- Available channels grid -->
      <div v-if="unconfiguredChannels.length > 0" class="space-y-3">
        <p class="text-xs text-muted-foreground font-medium">{{ t('channel.available') }}</p>
        <div class="grid grid-cols-3 gap-2">
          <button
            v-for="ch in unconfiguredChannels"
            :key="ch.id"
            class="px-3 py-3 rounded-lg border border-border bg-card text-left hover:border-primary/50 hover:bg-primary/5 transition-colors"
            @click="startConfiguring(ch)"
          >
            <span class="text-sm font-medium block">{{ ch.label }}</span>
            <span class="text-[10px] text-muted-foreground">{{ ch.origin }}</span>
          </button>
        </div>
      </div>

      <!-- Custom install section -->
      <div class="space-y-3">
        <button
          class="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          @click="customInstallOpen = !customInstallOpen"
        >
          <Plus class="w-3.5 h-3.5" />
          {{ t('channel.customInstall') }}
          <ChevronDown class="w-3 h-3 transition-transform" :class="customInstallOpen ? 'rotate-180' : ''" />
        </button>

        <div v-if="customInstallOpen" class="space-y-4 p-4 rounded-lg border border-border bg-card">
          <!-- npm install -->
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              <Package class="w-3.5 h-3.5 text-muted-foreground" />
              <span class="text-xs font-medium">{{ t('channel.installNpm') }}</span>
            </div>
            <div class="flex gap-2">
              <input
                v-model="npmPackageName"
                type="text"
                :placeholder="t('channel.npmPlaceholder')"
                class="flex-1 px-3 py-1.5 rounded-md bg-background border border-border text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
                @keyup.enter="handleInstallNpm"
              />
              <button
                :disabled="npmInstalling || !npmPackageName.trim()"
                class="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition-colors"
                :class="npmPackageName.trim()
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'bg-muted text-muted-foreground'"
                @click="handleInstallNpm"
              >
                <Loader2 v-if="npmInstalling" class="w-3 h-3 animate-spin" />
                {{ t('channel.install') }}
              </button>
            </div>
          </div>

          <!-- Upload -->
          <div class="space-y-2">
            <div class="flex items-center gap-2">
              <Upload class="w-3.5 h-3.5 text-muted-foreground" />
              <span class="text-xs font-medium">{{ t('channel.uploadPlugin') }}</span>
            </div>
            <label
              class="flex items-center justify-center gap-2 px-4 py-3 rounded-md border border-dashed border-border text-xs text-muted-foreground hover:border-primary/50 hover:text-foreground transition-colors cursor-pointer"
            >
              <Loader2 v-if="uploadingFile" class="w-3.5 h-3.5 animate-spin" />
              <Upload v-else class="w-3.5 h-3.5" />
              {{ uploadingFile ? t('channel.uploading') : t('channel.uploadHint') }}
              <input
                type="file"
                accept=".tgz,.tar.gz,.zip"
                class="hidden"
                :disabled="uploadingFile"
                @change="handleUpload"
              />
            </label>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-if="!loading && availableChannels.length === 0 && !error"
        class="flex flex-col items-center gap-3 py-10 text-center"
      >
        <Radio class="w-8 h-8 text-muted-foreground/40" />
        <p class="text-sm text-muted-foreground">{{ t('channel.emptyHint') }}</p>
      </div>
    </div>
  </div>
</template>
