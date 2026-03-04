<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/components/ui/toast'
import { useOrgStore } from '@/stores/org'
import { useAuthStore } from '@/stores/auth'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { Loader2, Trash2, Send, Save, Eye, EyeOff, MailPlus } from 'lucide-vue-next'

const { t } = useI18n()
const { toast } = useToast()
const orgStore = useOrgStore()
const authStore = useAuthStore()

interface SmtpConfig {
  id: string
  smtp_host: string
  smtp_port: number
  smtp_username: string
  smtp_password_masked: string
  from_email: string
  from_name: string | null
  use_tls: boolean
}

const loading = ref(false)
const saving = ref(false)
const testing = ref(false)
const deleting = ref(false)
const hasConfig = ref(false)

const form = ref({
  smtp_host: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  from_email: '',
  from_name: '',
  use_tls: true,
})

const showPassword = ref(false)
const passwordPlaceholder = ref('')
const testEmail = ref('')

async function fetchConfig() {
  if (!orgStore.currentOrg) return
  loading.value = true
  try {
    const res = await api.get(`/org-settings/${orgStore.currentOrg.id}/smtp-config`)
    const cfg: SmtpConfig | null = res.data.data
    if (cfg) {
      hasConfig.value = true
      form.value.smtp_host = cfg.smtp_host
      form.value.smtp_port = cfg.smtp_port
      form.value.smtp_username = cfg.smtp_username
      form.value.smtp_password = ''
      passwordPlaceholder.value = cfg.smtp_password_masked
      form.value.from_email = cfg.from_email
      form.value.from_name = cfg.from_name || ''
      form.value.use_tls = cfg.use_tls
    } else {
      hasConfig.value = false
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function handleSave() {
  if (!orgStore.currentOrg || saving.value) return

  if (!form.value.smtp_host || !form.value.smtp_username || !form.value.from_email) {
    toast({ title: t('orgSettings.smtpFillRequired'), variant: 'destructive' })
    return
  }

  if (!hasConfig.value && !form.value.smtp_password) {
    toast({ title: t('orgSettings.smtpPasswordRequired'), variant: 'destructive' })
    return
  }

  saving.value = true
  try {
    const payload: Record<string, any> = { ...form.value }
    if (hasConfig.value && !payload.smtp_password) {
      delete payload.smtp_password
    }
    await api.put(`/org-settings/${orgStore.currentOrg.id}/smtp-config`, payload)
    toast({ title: t('orgSettings.smtpSaved') })
    await fetchConfig()
  } catch (e: any) {
    toast({ title: resolveApiErrorMessage(e, t('orgSettings.smtpSaveFailed')), variant: 'destructive' })
  } finally {
    saving.value = false
  }
}

async function handleTest() {
  if (!orgStore.currentOrg || testing.value) return
  const email = testEmail.value || authStore.user?.email
  if (!email) {
    toast({ title: t('orgSettings.smtpTestEmailRequired'), variant: 'destructive' })
    return
  }
  testing.value = true
  try {
    await api.post(`/org-settings/${orgStore.currentOrg.id}/smtp-config/test`, { recipient_email: email })
    toast({ title: t('orgSettings.smtpTestSent') })
  } catch (e: any) {
    toast({ title: resolveApiErrorMessage(e, t('orgSettings.smtpTestFailed')), variant: 'destructive' })
  } finally {
    testing.value = false
  }
}

async function handleDelete() {
  if (!orgStore.currentOrg || deleting.value) return
  deleting.value = true
  try {
    await api.delete(`/org-settings/${orgStore.currentOrg.id}/smtp-config`)
    toast({ title: t('orgSettings.smtpDeleted') })
    hasConfig.value = false
    form.value = { smtp_host: '', smtp_port: 587, smtp_username: '', smtp_password: '', from_email: '', from_name: '', use_tls: true }
    passwordPlaceholder.value = ''
  } catch (e: any) {
    toast({ title: resolveApiErrorMessage(e, t('orgSettings.smtpDeleteFailed')), variant: 'destructive' })
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  if (!orgStore.currentOrg) orgStore.fetchMyOrg().then(fetchConfig)
  else fetchConfig()
  testEmail.value = authStore.user?.email || ''
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h2 class="text-lg font-semibold">{{ t('orgSettings.smtpTitle') }}</h2>
      <p class="text-sm text-muted-foreground mt-1">{{ t('orgSettings.smtpDescription') }}</p>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <!-- 空状态 -->
      <div v-if="!hasConfig && !form.smtp_host" class="text-center py-12 space-y-4">
        <div class="w-12 h-12 rounded-full bg-muted flex items-center justify-center mx-auto">
          <MailPlus class="w-6 h-6 text-muted-foreground" />
        </div>
        <div>
          <p class="text-sm font-medium">{{ t('orgSettings.smtpEmpty') }}</p>
          <p class="text-xs text-muted-foreground mt-1">{{ t('orgSettings.smtpEmptyHint') }}</p>
        </div>
      </div>

      <!-- SMTP 表单 -->
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpHost') }}</label>
            <input
              v-model="form.smtp_host"
              type="text"
              placeholder="smtp.example.com"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpPort') }}</label>
            <input
              v-model.number="form.smtp_port"
              type="number"
              placeholder="587"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.smtpUsername') }}</label>
          <input
            v-model="form.smtp_username"
            type="text"
            placeholder="user@example.com"
            class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
          />
        </div>

        <div class="space-y-1.5">
          <label class="text-sm font-medium">{{ t('orgSettings.smtpPassword') }}</label>
          <div class="relative">
            <input
              v-model="form.smtp_password"
              :type="showPassword ? 'text' : 'password'"
              :placeholder="passwordPlaceholder || t('orgSettings.smtpPasswordPlaceholder')"
              class="w-full h-9 px-3 pr-10 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
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
          <p v-if="hasConfig" class="text-xs text-muted-foreground">{{ t('orgSettings.smtpPasswordHint') }}</p>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpFromEmail') }}</label>
            <input
              v-model="form.from_email"
              type="email"
              placeholder="noreply@example.com"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">{{ t('orgSettings.smtpFromName') }}</label>
            <input
              v-model="form.from_name"
              type="text"
              :placeholder="t('orgSettings.smtpFromNamePlaceholder')"
              class="w-full h-9 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
            />
          </div>
        </div>

        <div class="flex items-center gap-2">
          <input
            id="use-tls"
            v-model="form.use_tls"
            type="checkbox"
            class="h-4 w-4 rounded border-input"
          />
          <label for="use-tls" class="text-sm font-medium">{{ t('orgSettings.smtpUseTls') }}</label>
        </div>

        <!-- 操作按钮 -->
        <div class="flex items-center gap-3 pt-2">
          <button
            :disabled="saving"
            class="h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 disabled:opacity-50 flex items-center gap-2"
            @click="handleSave"
          >
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
            <Save v-else class="w-4 h-4" />
            {{ t('orgSettings.smtpSave') }}
          </button>

          <template v-if="hasConfig">
            <div class="flex items-center gap-2">
              <input
                v-model="testEmail"
                type="email"
                :placeholder="t('orgSettings.smtpTestEmailPlaceholder')"
                class="h-9 w-52 px-3 rounded-md border border-input bg-background text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
              />
              <button
                :disabled="testing"
                class="h-9 px-4 rounded-md border border-input text-sm font-medium hover:bg-accent disabled:opacity-50 flex items-center gap-2"
                @click="handleTest"
              >
                <Loader2 v-if="testing" class="w-4 h-4 animate-spin" />
                <Send v-else class="w-4 h-4" />
                {{ t('orgSettings.smtpTest') }}
              </button>
            </div>

            <button
              :disabled="deleting"
              class="h-9 px-4 rounded-md border border-destructive/50 text-destructive text-sm font-medium hover:bg-destructive/10 disabled:opacity-50 flex items-center gap-2 ml-auto"
              @click="handleDelete"
            >
              <Loader2 v-if="deleting" class="w-4 h-4 animate-spin" />
              <Trash2 v-else class="w-4 h-4" />
              {{ t('orgSettings.smtpDelete') }}
            </button>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
