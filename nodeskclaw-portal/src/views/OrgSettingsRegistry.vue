<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { Loader2, Save, Plug, Eye, EyeOff, Container } from 'lucide-vue-next'

const { t } = useI18n()
const toast = useToast()

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const hasPassword = ref(false)
const showPassword = ref(false)

const registryUrl = ref('')
const registryUsername = ref('')
const registryPassword = ref('')

async function loadSettings() {
  loading.value = true
  try {
    const res = await api.get('/settings')
    const data = res.data.data as Record<string, string | null>
    registryUrl.value = data.image_registry || ''
    registryUsername.value = data.registry_username || ''
    registryPassword.value = ''
    hasPassword.value = data.registry_password === '******'
  } catch {
    // first-time setup may have no config
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (!registryUrl.value.trim()) {
    toast.error(t('orgSettings.registryFillRequired'))
    return
  }

  saving.value = true
  try {
    const promises = [
      api.put('/settings/image_registry', { value: registryUrl.value.trim() }),
      api.put('/settings/registry_username', { value: registryUsername.value.trim() || null }),
    ]
    if (registryPassword.value) {
      promises.push(api.put('/settings/registry_password', { value: registryPassword.value }))
    }
    await Promise.all(promises)
    registryPassword.value = ''
    if (registryUsername.value.trim() && registryPassword.value !== '') {
      hasPassword.value = true
    }
    await loadSettings()
    toast.success(t('orgSettings.registrySaved'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.registrySaveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  if (!registryUrl.value.trim()) {
    toast.error(t('orgSettings.registryFillRequired'))
    return
  }

  testing.value = true
  try {
    const res = await api.get('/registry/tags')
    const tags = (res.data.data ?? []) as { tag: string }[]
    toast.success(t('orgSettings.registryTestSuccess', { count: tags.length }))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e, t('orgSettings.registryTestFailed')))
  } finally {
    testing.value = false
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
      <div v-if="!registryUrl && !hasPassword" class="text-center py-12 space-y-4">
        <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto">
          <Container class="w-6 h-6 text-muted-foreground" />
        </div>
        <div>
          <p class="text-sm font-medium">{{ t('orgSettings.registryEmpty') }}</p>
          <p class="text-xs text-muted-foreground mt-1">{{ t('orgSettings.registryEmptyHint') }}</p>
        </div>
      </div>

      <div class="space-y-4">
        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.registryUrl') }}</label>
          <input
            v-model="registryUrl"
            type="text"
            placeholder="cr.example.com/namespace/openclaw"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
          <p class="text-xs text-muted-foreground">{{ t('orgSettings.registryUrlHint') }}</p>
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.registryUsername') }}</label>
          <input
            v-model="registryUsername"
            type="text"
            placeholder="username"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
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
            <input
              v-model="registryPassword"
              :type="showPassword ? 'text' : 'password'"
              :placeholder="hasPassword ? t('orgSettings.registryPasswordHint') : t('orgSettings.registryPasswordPlaceholder')"
              class="w-full h-9 px-3 pr-10 rounded-md border border-input bg-background text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
            <button
              type="button"
              tabindex="-1"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" class="w-4 h-4" />
              <Eye v-else class="w-4 h-4" />
            </button>
          </div>
        </div>

        <div class="flex items-center gap-3 pt-2">
          <button
            :disabled="saving"
            class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            @click="handleSave"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ t('orgSettings.registrySave') }}
          </button>

          <button
            v-if="registryUrl.trim()"
            :disabled="testing"
            class="h-9 px-4 rounded-md border border-input text-sm font-medium hover:bg-accent disabled:opacity-50 flex items-center gap-2"
            @click="handleTest"
          >
            <Loader2 v-if="testing" class="w-4 h-4 animate-spin" />
            <Plug v-else class="w-4 h-4" />
            {{ t('orgSettings.registryTest') }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
