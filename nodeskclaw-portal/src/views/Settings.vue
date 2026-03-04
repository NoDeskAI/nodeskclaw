<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { User, LogOut, Eye, EyeOff, KeyRound } from 'lucide-vue-next'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()
const toast = useToast()

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}

const hasPassword = computed(() => authStore.user?.has_password ?? false)

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const showOldPassword = ref(false)
const showNewPassword = ref(false)
const showConfirmPassword = ref(false)
const saving = ref(false)

const passwordTooShort = computed(() => newPassword.value.length > 0 && newPassword.value.length < 6)
const passwordMismatch = computed(() => confirmPassword.value.length > 0 && newPassword.value !== confirmPassword.value)

const canSubmit = computed(() => {
  if (saving.value) return false
  if (newPassword.value.length < 6) return false
  if (newPassword.value !== confirmPassword.value) return false
  if (hasPassword.value && !oldPassword.value) return false
  return true
})

async function handleSubmit() {
  if (!canSubmit.value) return
  saving.value = true
  try {
    await api.put('/auth/me/password', {
      old_password: hasPassword.value ? oldPassword.value : undefined,
      new_password: newPassword.value,
    })
    toast.success(t('settings.passwordChanged'))
    oldPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    await authStore.fetchUser()
  } catch (err) {
    toast.error(resolveApiErrorMessage(err))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <h1 class="text-xl font-bold mb-6">{{ t('common.settings') }}</h1>

    <!-- 用户信息 -->
    <div class="p-4 rounded-xl border border-border bg-card space-y-4">
      <div class="flex items-center gap-4">
        <div class="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
          <img
            v-if="authStore.user?.avatar_url"
            :src="authStore.user.avatar_url"
            class="w-14 h-14 rounded-full"
            alt="头像"
          />
          <User v-else class="w-7 h-7 text-primary" />
        </div>
        <div>
          <div class="font-medium text-lg">{{ authStore.user?.name }}</div>
          <div class="text-sm text-muted-foreground">{{ authStore.user?.email || '-' }}</div>
        </div>
      </div>
    </div>

    <!-- 密码管理 -->
    <div class="mt-6 p-4 rounded-xl border border-border bg-card space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <KeyRound class="w-4 h-4 text-muted-foreground" />
          <span class="font-medium">{{ t('settings.password') }}</span>
        </div>
        <span
          class="text-xs px-2 py-0.5 rounded-full"
          :class="hasPassword ? 'bg-green-500/10 text-green-600' : 'bg-muted text-muted-foreground'"
        >
          {{ hasPassword ? t('settings.passwordSet') : t('settings.passwordNotSet') }}
        </span>
      </div>

      <p v-if="!hasPassword" class="text-sm text-muted-foreground">
        {{ t('settings.passwordNotSetHint') }}
      </p>

      <form class="space-y-3" @submit.prevent="handleSubmit">
        <!-- 当前密码（仅已设置密码时显示） -->
        <div v-if="hasPassword">
          <label class="block text-sm text-muted-foreground mb-1">{{ t('settings.currentPassword') }}</label>
          <div class="relative">
            <input
              v-model="oldPassword"
              :type="showOldPassword ? 'text' : 'password'"
              class="w-full px-3 py-2 pr-10 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <button
              type="button"
              tabindex="-1"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              @click="showOldPassword = !showOldPassword"
            >
              <EyeOff v-if="showOldPassword" class="w-4 h-4" />
              <Eye v-else class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- 新密码 -->
        <div>
          <label class="block text-sm text-muted-foreground mb-1">{{ t('settings.newPassword') }}</label>
          <div class="relative">
            <input
              v-model="newPassword"
              :type="showNewPassword ? 'text' : 'password'"
              class="w-full px-3 py-2 pr-10 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <button
              type="button"
              tabindex="-1"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              @click="showNewPassword = !showNewPassword"
            >
              <EyeOff v-if="showNewPassword" class="w-4 h-4" />
              <Eye v-else class="w-4 h-4" />
            </button>
          </div>
          <p v-if="passwordTooShort" class="mt-1 text-xs text-red-500">
            {{ t('settings.passwordTooShort') }}
          </p>
        </div>

        <!-- 确认密码 -->
        <div>
          <label class="block text-sm text-muted-foreground mb-1">{{ t('settings.confirmPassword') }}</label>
          <div class="relative">
            <input
              v-model="confirmPassword"
              :type="showConfirmPassword ? 'text' : 'password'"
              class="w-full px-3 py-2 pr-10 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            />
            <button
              type="button"
              tabindex="-1"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              @click="showConfirmPassword = !showConfirmPassword"
            >
              <EyeOff v-if="showConfirmPassword" class="w-4 h-4" />
              <Eye v-else class="w-4 h-4" />
            </button>
          </div>
          <p v-if="passwordMismatch" class="mt-1 text-xs text-red-500">
            {{ t('settings.passwordMismatch') }}
          </p>
        </div>

        <div class="flex justify-end pt-1">
          <button
            type="submit"
            :disabled="!canSubmit"
            class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {{ saving ? t('settings.saving') : (hasPassword ? t('settings.changePassword') : t('settings.setPassword')) }}
          </button>
        </div>
      </form>
    </div>

    <!-- 操作 -->
    <div class="mt-6 space-y-3">
      <button
        class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-border bg-card text-sm hover:bg-card/80 transition-colors text-red-400"
        @click="handleLogout"
      >
        <LogOut class="w-4 h-4" />
        {{ t('common.logout') }}
      </button>
    </div>
  </div>
</template>
