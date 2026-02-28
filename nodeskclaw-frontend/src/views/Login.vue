<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { PawPrint } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

function handleOAuthLogin(provider: string) {
  sessionStorage.setItem('oauth_provider', provider)
  if (provider === 'feishu') {
    const clientId = import.meta.env.VITE_FEISHU_APP_ID || ''
    const redirectUri = encodeURIComponent(window.location.origin + `/login/callback/${provider}`)
    const state = Math.random().toString(36).substring(2)
    window.location.href = `https://passport.feishu.cn/suite/passport/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&state=${state}`
  }
}
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
        <Button
          class="w-full"
          size="lg"
          @click="handleOAuthLogin('feishu')"
        >
          飞书账号登录
        </Button>
      </CardContent>
    </Card>
  </div>
</template>
