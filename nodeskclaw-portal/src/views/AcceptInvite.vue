<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { Loader2, Building2, Eye, EyeOff } from 'lucide-vue-next'
import axios from 'axios'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const token = route.params.token as string

const loading = ref(true)
const submitting = ref(false)
const error = ref('')

const inviteInfo = ref<{
  org_name: string
  org_id: string
  email: string
  role: string
  expired: boolean
  already_registered: boolean
} | null>(null)

const form = ref({
  name: '',
  password: '',
  confirmPassword: '',
})
const showPassword = ref(false)
const showConfirmPassword = ref(false)

const apiBase = import.meta.env.VITE_API_BASE_URL || '/api/v1'

onMounted(async () => {
  try {
    const res = await axios.get(`${apiBase}/invite/${token}`)
    inviteInfo.value = res.data.data
  } catch (e: any) {
    error.value = e?.response?.data?.detail?.message || t('acceptInvite.invalidLink')
  } finally {
    loading.value = false
  }
})

async function handleAccept() {
  if (!inviteInfo.value) return

  if (!inviteInfo.value.already_registered) {
    if (!form.value.name.trim()) {
      error.value = t('acceptInvite.nameRequired')
      return
    }
    if (form.value.password.length < 6) {
      error.value = t('acceptInvite.passwordTooShort')
      return
    }
    if (form.value.password !== form.value.confirmPassword) {
      error.value = t('acceptInvite.passwordMismatch')
      return
    }
  }

  error.value = ''
  submitting.value = true

  try {
    const res = await axios.post(`${apiBase}/invite/accept`, {
      token,
      name: form.value.name || inviteInfo.value.email.split('@')[0],
      password: form.value.password || 'placeholder-for-existing-user',
    })

    const data = res.data.data
    if (data.access_token) {
      localStorage.setItem('token', data.access_token)
      if (data.refresh_token) {
        localStorage.setItem('refreshToken', data.refresh_token)
      }
      await authStore.fetchUser()
      router.push('/')
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail?.message || t('acceptInvite.acceptFailed')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background px-4">
    <div class="w-full max-w-md">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-20">
        <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
      </div>

      <!-- Error (invalid link) -->
      <div v-else-if="!inviteInfo" class="text-center space-y-4">
        <div class="w-16 h-16 mx-auto rounded-full bg-red-500/10 flex items-center justify-center">
          <Building2 class="w-8 h-8 text-red-400" />
        </div>
        <h1 class="text-xl font-semibold">{{ t('acceptInvite.invalidTitle') }}</h1>
        <p class="text-sm text-muted-foreground">{{ error || t('acceptInvite.invalidLink') }}</p>
        <button
          class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          @click="router.push('/login')"
        >
          {{ t('acceptInvite.goToLogin') }}
        </button>
      </div>

      <!-- Expired -->
      <div v-else-if="inviteInfo.expired" class="text-center space-y-4">
        <div class="w-16 h-16 mx-auto rounded-full bg-yellow-500/10 flex items-center justify-center">
          <Building2 class="w-8 h-8 text-yellow-400" />
        </div>
        <h1 class="text-xl font-semibold">{{ t('acceptInvite.expiredTitle') }}</h1>
        <p class="text-sm text-muted-foreground">{{ t('acceptInvite.expiredDesc') }}</p>
        <button
          class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          @click="router.push('/login')"
        >
          {{ t('acceptInvite.goToLogin') }}
        </button>
      </div>

      <!-- Accept Form -->
      <div v-else class="space-y-6">
        <div class="text-center space-y-2">
          <div class="w-16 h-16 mx-auto rounded-full bg-primary/10 flex items-center justify-center">
            <Building2 class="w-8 h-8 text-primary" />
          </div>
          <h1 class="text-xl font-semibold">{{ t('acceptInvite.title') }}</h1>
          <p class="text-sm text-muted-foreground">
            {{ t('acceptInvite.subtitle', { orgName: inviteInfo.org_name }) }}
          </p>
        </div>

        <div class="rounded-xl border border-border bg-card p-5 space-y-4">
          <!-- Invite Details -->
          <div class="space-y-2">
            <div class="flex items-center justify-between text-sm">
              <span class="text-muted-foreground">{{ t('acceptInvite.org') }}</span>
              <span class="font-medium">{{ inviteInfo.org_name }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-muted-foreground">{{ t('acceptInvite.email') }}</span>
              <span class="font-medium">{{ inviteInfo.email }}</span>
            </div>
            <div class="flex items-center justify-between text-sm">
              <span class="text-muted-foreground">{{ t('acceptInvite.role') }}</span>
              <span class="font-medium">{{ inviteInfo.role === 'admin' ? t('orgMembers.roleAdmin') : t('orgMembers.roleMember') }}</span>
            </div>
          </div>

          <div class="border-t border-border" />

          <!-- Existing User -->
          <template v-if="inviteInfo.already_registered">
            <p class="text-sm text-muted-foreground">{{ t('acceptInvite.alreadyRegistered') }}</p>
          </template>

          <!-- New User Registration -->
          <template v-else>
            <div class="space-y-3">
              <div>
                <label class="block text-sm text-muted-foreground mb-1.5">{{ t('acceptInvite.nameLabel') }}</label>
                <input
                  v-model="form.name"
                  type="text"
                  :placeholder="t('acceptInvite.namePlaceholder')"
                  class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
              </div>
              <div>
                <label class="block text-sm text-muted-foreground mb-1.5">{{ t('acceptInvite.passwordLabel') }}</label>
                <div class="relative">
                  <input
                    v-model="form.password"
                    :type="showPassword ? 'text' : 'password'"
                    :placeholder="t('acceptInvite.passwordPlaceholder')"
                    class="w-full px-3 py-2 pr-10 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                  <button
                    type="button"
                    class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    @click="showPassword = !showPassword"
                  >
                    <EyeOff v-if="showPassword" class="w-4 h-4" />
                    <Eye v-else class="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-sm text-muted-foreground mb-1.5">{{ t('acceptInvite.confirmPasswordLabel') }}</label>
                <div class="relative">
                  <input
                    v-model="form.confirmPassword"
                    :type="showConfirmPassword ? 'text' : 'password'"
                    :placeholder="t('acceptInvite.confirmPasswordPlaceholder')"
                    class="w-full px-3 py-2 pr-10 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                  />
                  <button
                    type="button"
                    class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    @click="showConfirmPassword = !showConfirmPassword"
                  >
                    <EyeOff v-if="showConfirmPassword" class="w-4 h-4" />
                    <Eye v-else class="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          </template>

          <!-- Error -->
          <p v-if="error" class="text-sm text-red-400">{{ error }}</p>

          <!-- Submit -->
          <button
            class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
            :disabled="submitting"
            @click="handleAccept"
          >
            <Loader2 v-if="submitting" class="w-4 h-4 animate-spin" />
            {{ inviteInfo.already_registered ? t('acceptInvite.joinOrg') : t('acceptInvite.registerAndJoin') }}
          </button>
        </div>

        <p class="text-center text-xs text-muted-foreground">
          {{ t('acceptInvite.hasAccount') }}
          <router-link to="/login" class="text-primary hover:underline">{{ t('acceptInvite.login') }}</router-link>
        </p>
      </div>
    </div>
  </div>
</template>
