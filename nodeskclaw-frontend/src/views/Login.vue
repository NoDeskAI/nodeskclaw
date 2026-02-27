<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PawPrint } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const loading = ref(false)
const error = ref('')

// Feishu OAuth redirect URL
// 参考：https://passport.feishu.cn/suite/passport/oauth/authorize
function getFeishuAuthUrl() {
  const clientId = import.meta.env.VITE_FEISHU_APP_ID || ''
  const redirectUri = encodeURIComponent(window.location.origin + '/login')
  const state = Math.random().toString(36).substring(2)
  return `https://passport.feishu.cn/suite/passport/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&state=${state}`
}

function handleFeishuLogin() {
  window.location.href = getFeishuAuthUrl()
}

// Handle OAuth callback (code in URL query)
onMounted(async () => {
  const code = route.query.code as string
  if (code) {
    loading.value = true
    error.value = ''
    try {
      await authStore.feishuLogin(code)
      router.replace('/')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '登录失败'
      error.value = msg
    } finally {
      loading.value = false
    }
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background">
    <Card class="w-[400px]">
      <CardHeader class="text-center">
        <div class="flex items-center justify-center gap-2 mb-4">
          <PawPrint class="w-8 h-8 text-primary" />
          <span class="text-2xl font-bold">NoDeskClaw</span>
        </div>
        <CardTitle class="text-lg font-normal text-muted-foreground">
          One-click deploy, full control.
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-4">
        <p v-if="error" class="text-sm text-destructive text-center">{{ error }}</p>
        <p v-if="loading" class="text-sm text-muted-foreground text-center">登录中...</p>
        <Button
          class="w-full"
          size="lg"
          :disabled="loading"
          @click="handleFeishuLogin"
        >
          飞书账号登录
        </Button>
      </CardContent>
    </Card>
  </div>
</template>
