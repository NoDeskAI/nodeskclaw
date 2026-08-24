<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { Loader2, Save, Plug, Eye, EyeOff, Container, AlertCircle, Cloud, Server } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'

const { t } = useI18n()
const toast = useToast()

const loading = ref(false)
const saving = ref(false)
const hasPassword = ref(false)
const showPassword = ref(false)
type RegistryMode = 'custom' | 'hosted'
const registryMode = ref<RegistryMode>('custom')
const persistedRegistryMode = ref<RegistryMode>('custom')
const dirty = ref(false)

const registryUsername = ref('')
const registryPassword = ref('')
const hostedRegistryUrl = ref('')
const hostedRegistryUsername = ref('')
const hostedRegistryHasPassword = ref(false)

interface EngineItem {
  runtime_id: string
  display_name: string
  image_registry_key: string
  default_registry_url: string
}

const engines = ref<EngineItem[]>([])
const engineRegistryUrls = ref<Record<string, string>>({})
const testingEngine = ref<string | null>(null)

const hostedRegistryConfigured = computed(() =>
  Boolean(
    hostedRegistryUrl.value.trim()
    && hostedRegistryUsername.value.trim()
    && hostedRegistryHasPassword.value,
  ),
)

function hostedRepository(runtimeId: string) {
  const root = hostedRegistryUrl.value.trim().replace(/^https?:\/\//, '').replace(/\/$/, '')
  return root ? `${root}/deskclaw-${runtimeId}` : ''
}

function registryBuildCommand(engine: EngineItem) {
  if (registryMode.value === 'hosted') {
    return `./build.sh ${engine.runtime_id} --registry ${hostedRegistryUrl.value.trim() || '<registry-root>'}`
  }
  return `./build.sh ${engine.runtime_id} --repository ${engineRegistryUrls.value[engine.runtime_id]?.trim() || '<repository>'}`
}

function markDirty() {
  dirty.value = true
}

function selectRegistryMode(mode: RegistryMode) {
  if (registryMode.value === mode) return
  registryMode.value = mode
  dirty.value = true
}

async function loadSettings() {
  loading.value = true
  try {
    const [settingsRes, enginesRes] = await Promise.all([
      api.get('/settings'),
      api.get('/engines'),
    ])
    const data = settingsRes.data.data as Record<string, string | null>
    engines.value = (enginesRes.data.data ?? []) as EngineItem[]

    registryMode.value = data.registry_mode === 'hosted' ? 'hosted' : 'custom'
    persistedRegistryMode.value = registryMode.value
    registryUsername.value = data.registry_username || ''
    registryPassword.value = ''
    hasPassword.value = data.registry_password === '******'
    hostedRegistryUrl.value = data.hosted_registry_url || ''
    hostedRegistryUsername.value = data.hosted_registry_username || ''
    hostedRegistryHasPassword.value = data.hosted_registry_password === '******'

    const urls: Record<string, string> = {}
    for (const eng of engines.value) {
      urls[eng.runtime_id] = data[eng.image_registry_key] || ''
    }
    engineRegistryUrls.value = urls
    dirty.value = false
  } catch {
    // first-time setup may have no config
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (registryMode.value === 'hosted' && !hostedRegistryConfigured.value) {
    toast.error(t('orgSettings.registryHostedNotConfigured'))
    return
  }
  if (
    registryMode.value === 'custom'
    && !Object.values(engineRegistryUrls.value).some(url => url.trim())
  ) {
    toast.error(t('orgSettings.registryFillRequired'))
    return
  }

  saving.value = true
  try {
    const passwordUpdated = Boolean(registryPassword.value)
    const promises: Promise<unknown>[] = []
    if (registryMode.value === 'custom') {
      for (const eng of engines.value) {
        const url = engineRegistryUrls.value[eng.runtime_id]?.trim() || null
        promises.push(api.put(`/settings/${eng.image_registry_key}`, { value: url }))
      }
      promises.push(api.put('/settings/registry_username', { value: registryUsername.value.trim() || null }))
      if (registryPassword.value) {
        promises.push(api.put('/settings/registry_password', { value: registryPassword.value }))
      }
    }
    await Promise.all(promises)
    await api.put('/settings/registry_mode', { value: registryMode.value })
    persistedRegistryMode.value = registryMode.value
    dirty.value = false
    registryPassword.value = ''
    if (passwordUpdated) hasPassword.value = true
    toast.success(t('orgSettings.registrySaved'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.registrySaveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleTestEngine(engineId: string) {
  if (dirty.value || registryMode.value !== persistedRegistryMode.value) {
    toast.error(t('orgSettings.registrySaveBeforeTest'))
    return
  }
  const url = engineRegistryUrls.value[engineId]?.trim()
  if (registryMode.value === 'custom' && !url) {
    toast.error(t('orgSettings.registryFillRequired'))
    return
  }

  testingEngine.value = engineId
  try {
    const params = registryMode.value === 'hosted'
      ? { runtime: engineId }
      : { registry_url: url, runtime: engineId }
    const res = await api.get('/registry/tags', { params })
    const tags = (res.data.data ?? []) as { tag: string }[]
    toast.success(t('orgSettings.registryTestSuccess', { count: tags.length }))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.registryTestFailed')))
  } finally {
    testingEngine.value = null
  }
}

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">{{ t('orgSettings.registryTitle') }}</h2>
      <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.registryDescription') }}</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <div v-if="engines.length === 0" class="text-center py-12 space-y-4">
        <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto">
          <Container class="w-6 h-6 text-muted-foreground" />
        </div>
        <div>
          <p class="text-sm font-medium">{{ t('orgSettings.registryEmpty') }}</p>
          <p class="text-xs text-muted-foreground mt-1">{{ t('orgSettings.registryEmptyHint') }}</p>
        </div>
      </div>

      <div v-else class="space-y-5">
        <div class="space-y-2">
          <label class="text-sm font-medium">{{ t('orgSettings.registryModeTitle') }}</label>
          <div class="grid gap-3 md:grid-cols-2">
            <button
              type="button"
              class="rounded-lg border p-4 text-left transition-colors"
              :class="registryMode === 'hosted' ? 'border-primary bg-primary/5' : 'border-border hover:border-muted-foreground/50'"
              @click="selectRegistryMode('hosted')"
            >
              <div class="flex items-start gap-3">
                <div class="rounded-md bg-primary/10 p-2 text-primary">
                  <Cloud class="h-4 w-4" />
                </div>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium">{{ t('orgSettings.registryHostedTitle') }}</span>
                    <Badge v-if="registryMode === 'hosted'" variant="secondary">{{ t('orgSettings.registryCurrent') }}</Badge>
                  </div>
                  <p class="mt-1 text-xs text-muted-foreground">{{ t('orgSettings.registryHostedDescription') }}</p>
                </div>
              </div>
            </button>
            <button
              type="button"
              class="rounded-lg border p-4 text-left transition-colors"
              :class="registryMode === 'custom' ? 'border-primary bg-primary/5' : 'border-border hover:border-muted-foreground/50'"
              @click="selectRegistryMode('custom')"
            >
              <div class="flex items-start gap-3">
                <div class="rounded-md bg-primary/10 p-2 text-primary">
                  <Server class="h-4 w-4" />
                </div>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium">{{ t('orgSettings.registryCustomTitle') }}</span>
                    <Badge v-if="registryMode === 'custom'" variant="secondary">{{ t('orgSettings.registryCurrent') }}</Badge>
                  </div>
                  <p class="mt-1 text-xs text-muted-foreground">{{ t('orgSettings.registryCustomDescription') }}</p>
                </div>
              </div>
            </button>
          </div>
        </div>

        <template v-if="registryMode === 'hosted'">
          <div
            class="rounded-lg border p-4"
            :class="hostedRegistryConfigured ? 'border-border' : 'border-destructive/40 bg-destructive/5'"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-sm font-medium">{{ t('orgSettings.registryHostedRoot') }}</p>
                <p class="mt-1 break-all font-mono text-sm text-muted-foreground">
                  {{ hostedRegistryUrl || t('orgSettings.registryNotConfigured') }}
                </p>
              </div>
              <Badge :variant="hostedRegistryConfigured ? 'secondary' : 'destructive'">
                {{ hostedRegistryConfigured ? t('orgSettings.registryConfigured') : t('orgSettings.registryNotConfigured') }}
              </Badge>
            </div>
            <div v-if="!hostedRegistryConfigured" class="mt-3 flex items-start gap-2 text-xs text-destructive">
              <AlertCircle class="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <p>{{ t('orgSettings.registryHostedNotConfiguredHint') }}</p>
            </div>
            <p v-else class="mt-3 text-xs text-muted-foreground">
              {{ t('orgSettings.registryManagedByDeploy') }}
            </p>
          </div>

          <div v-for="eng in engines" :key="eng.runtime_id" class="rounded-lg border border-border p-4 space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="text-sm font-medium">{{ eng.display_name }}</p>
                <p class="mt-1 break-all font-mono text-xs text-muted-foreground">
                  {{ hostedRepository(eng.runtime_id) || t('orgSettings.registryNotConfigured') }}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                :disabled="!hostedRegistryConfigured || dirty || registryMode !== persistedRegistryMode || testingEngine === eng.runtime_id"
                @click="handleTestEngine(eng.runtime_id)"
              >
                <Loader2 v-if="testingEngine === eng.runtime_id" class="w-3 h-3 mr-1 animate-spin" />
                <Plug v-else class="w-3 h-3 mr-1" />
                {{ t('orgSettings.registryTest') }}
              </Button>
            </div>
            <div>
              <p class="mb-1 text-xs text-muted-foreground">{{ t('orgSettings.registryBuildCommand') }}</p>
              <code class="block overflow-x-auto rounded bg-muted px-3 py-2 text-xs">{{ registryBuildCommand(eng) }}</code>
            </div>
          </div>
        </template>

        <template v-else>
          <div v-for="eng in engines" :key="eng.runtime_id" class="rounded-lg border border-border p-4 space-y-3">
            <div class="flex items-center justify-between gap-3">
              <label class="text-sm font-medium">{{ eng.display_name }}</label>
              <Button
                v-if="engineRegistryUrls[eng.runtime_id]?.trim()"
                variant="outline"
                size="sm"
                :disabled="dirty || registryMode !== persistedRegistryMode || testingEngine === eng.runtime_id"
                @click="handleTestEngine(eng.runtime_id)"
              >
                <Loader2 v-if="testingEngine === eng.runtime_id" class="w-3 h-3 mr-1 animate-spin" />
                <Plug v-else class="w-3 h-3 mr-1" />
                {{ t('orgSettings.registryTest') }}
              </Button>
            </div>
            <Input
              v-model="engineRegistryUrls[eng.runtime_id]"
              type="text"
              :placeholder="`cr.example.com/namespace/${eng.runtime_id}`"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              @update:model-value="markDirty"
            />
            <div>
              <p class="mb-1 text-xs text-muted-foreground">{{ t('orgSettings.registryBuildCommand') }}</p>
              <code class="block overflow-x-auto rounded bg-muted px-3 py-2 text-xs">{{ registryBuildCommand(eng) }}</code>
            </div>
          </div>

          <div class="border-t border-border pt-5 space-y-4">
            <p class="text-xs text-muted-foreground">{{ t('orgSettings.registryCredentialsHint') }}</p>

            <div class="space-y-1.5">
              <label class="text-sm font-medium">{{ t('orgSettings.registryUsername') }}</label>
              <Input
                v-model="registryUsername"
                type="text"
                :placeholder="t('orgSettings.registryUsernamePlaceholder')"
                class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                @update:model-value="markDirty"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium">
                {{ t('orgSettings.registryPassword') }}
                <span v-if="hasPassword" class="text-xs text-muted-foreground font-normal ml-1">
                  ({{ t('orgSettings.registryPasswordHint') }})
                </span>
              </label>
              <div class="relative">
                <Input
                  v-model="registryPassword"
                  :type="showPassword ? 'text' : 'password'"
                  :placeholder="hasPassword ? t('orgSettings.registryPasswordHint') : t('orgSettings.registryPasswordPlaceholder')"
                  class="w-full h-9 px-3 pr-10 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                  @update:model-value="markDirty"
                />
                <Button
                  variant="unstyled"
                  size="unstyled"
                  type="button"
                  tabindex="-1"
                  class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        </template>

        <p v-if="dirty" class="text-xs text-muted-foreground">{{ t('orgSettings.registrySaveBeforeTest') }}</p>

        <div class="flex items-center gap-3 pt-2">
          <Button
            variant="unstyled"
            size="unstyled"
            :disabled="saving || !dirty"
            class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            @click="handleSave"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ t('orgSettings.registrySave') }}
          </Button>
        </div>
      </div>
    </template>
  </div>
</template>
