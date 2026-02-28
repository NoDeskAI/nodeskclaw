<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { resolveApiErrorMessage } from '@/i18n/error'
import { Loader2 } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const { t } = useI18n()

const error = ref('')

onMounted(async () => {
  const provider = route.params.provider as string
  const code = new URLSearchParams(window.location.search).get('code')

  if (!provider || !code) {
    error.value = t('auth.callbackMissingParams')
    return
  }

  try {
    const data = await authStore.oauthLogin(provider, code)
    if (data.needs_org_setup) {
      router.replace('/setup-org')
    } else {
      router.replace('/')
    }
  } catch (e: any) {
    error.value = resolveApiErrorMessage(e, t('auth.loginFailed'))
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background">
    <div v-if="error" class="text-center space-y-4 max-w-sm px-4">
      <p class="text-sm text-destructive bg-destructive/10 rounded-lg py-3 px-4 border border-destructive/20">
        {{ error }}
      </p>
      <button
        class="text-sm text-primary hover:text-primary/80 transition-colors"
        @click="router.replace('/login')"
      >
        {{ t('auth.backToLogin') }}
      </button>
    </div>
    <div v-else class="flex items-center gap-3 text-muted-foreground">
      <Loader2 class="w-5 h-5 animate-spin" />
      <span class="text-sm">{{ t('auth.loggingIn') }}</span>
    </div>
  </div>
</template>
