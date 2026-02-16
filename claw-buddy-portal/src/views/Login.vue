<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PawPrint, Loader2 } from 'lucide-vue-next'
import api from '@/services/api'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const loading = ref(false)
const error = ref('')

const feishuAppId = ref('')
const feishuRedirectUri = encodeURIComponent(window.location.origin + '/login')

onMounted(async () => {
  // 获取飞书 App ID
  try {
    const res = await api.get('/settings/feishu-app-id')
    feishuAppId.value = res.data.data?.app_id || ''
  } catch {
    // ignore
  }

  // 飞书 SSO 回调
  const code = route.query.code as string
  if (code) {
    loading.value = true
    try {
      await authStore.feishuLogin(code)
      router.replace('/')
    } catch (e: any) {
      error.value = e?.response?.data?.message || '登录失败'
    } finally {
      loading.value = false
    }
  }
})

function loginWithFeishu() {
  if (!feishuAppId.value) {
    error.value = '飞书 App ID 未配置'
    return
  }
  window.location.href = `https://passport.feishu.cn/suite/passport/oauth/authorize?client_id=${feishuAppId.value}&redirect_uri=${feishuRedirectUri}&response_type=code&state=portal`
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center">
    <div class="w-full max-w-sm px-6 space-y-8 text-center">
      <div class="flex flex-col items-center gap-3">
        <PawPrint class="w-12 h-12 text-primary" />
        <h1 class="text-2xl font-bold">ClawBuddy</h1>
        <p class="text-sm text-muted-foreground">一键部署你的 AI 助手</p>
      </div>

      <div v-if="loading" class="flex items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 class="w-4 h-4 animate-spin" />
        登录中...
      </div>

      <div v-else class="space-y-4">
        <button
          class="w-full py-2.5 px-4 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors"
          @click="loginWithFeishu"
        >
          飞书登录
        </button>
        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
      </div>
    </div>
  </div>
</template>
