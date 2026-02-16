<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PawPrint, Loader2, Zap, Shield, Globe, Sparkles } from 'lucide-vue-next'
import api from '@/services/api'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const loading = ref(false)
const error = ref('')

const feishuAppId = ref('')
const feishuRedirectUri = encodeURIComponent(window.location.origin + '/login')

onMounted(async () => {
  try {
    const res = await api.get('/settings/feishu-app-id')
    feishuAppId.value = res.data.data?.app_id || ''
  } catch {
    // ignore
  }

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

const features = [
  { icon: Zap, title: '一键部署', desc: '零配置启动你的 AI 助手' },
  { icon: Shield, title: '企业级安全', desc: '多租户隔离，数据独占' },
  { icon: Globe, title: '即开即用', desc: '自动域名，HTTPS 就绪' },
  { icon: Sparkles, title: '弹性扩展', desc: '按需选择规格，灵活升降配' },
]
</script>

<template>
  <div class="min-h-screen flex">
    <!-- 左侧品牌区 -->
    <div class="hidden lg:flex lg:w-[55%] relative overflow-hidden bg-gradient-to-br from-primary/20 via-background to-background">
      <!-- 装饰背景 -->
      <div class="absolute inset-0">
        <div class="absolute top-1/4 left-1/4 w-96 h-96 rounded-full bg-primary/5 blur-3xl" />
        <div class="absolute bottom-1/4 right-1/4 w-64 h-64 rounded-full bg-primary/8 blur-3xl" />
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full border border-primary/5" />
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full border border-primary/8" />
      </div>

      <!-- 品牌内容 -->
      <div class="relative z-10 flex flex-col justify-center px-16 xl:px-24">
        <div class="flex items-center gap-3 mb-6">
          <div class="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center">
            <PawPrint class="w-6 h-6 text-primary" />
          </div>
          <span class="text-xl font-bold tracking-tight">ClawBuddy</span>
        </div>

        <h1 class="text-4xl xl:text-5xl font-bold leading-tight mb-4">
          你的 AI 助手<br />
          <span class="text-primary">云端部署平台</span>
        </h1>
        <p class="text-base text-muted-foreground max-w-md mb-12">
          基于 OpenClaw 的 SaaS 部署平台，让每个人都能拥有自己的 AI 助手。无需运维经验，一键创建，即刻使用。
        </p>

        <!-- 特性网格 -->
        <div class="grid grid-cols-2 gap-4 max-w-md">
          <div
            v-for="f in features"
            :key="f.title"
            class="flex items-start gap-3 p-3 rounded-xl bg-card/40 backdrop-blur-sm border border-border/50"
          >
            <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
              <component :is="f.icon" class="w-4 h-4 text-primary" />
            </div>
            <div>
              <div class="text-sm font-medium">{{ f.title }}</div>
              <div class="text-xs text-muted-foreground mt-0.5">{{ f.desc }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧登录区 -->
    <div class="flex-1 flex items-center justify-center px-6">
      <div class="w-full max-w-sm space-y-8">
        <!-- 移动端 Logo -->
        <div class="flex flex-col items-center gap-3 lg:hidden">
          <div class="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center">
            <PawPrint class="w-7 h-7 text-primary" />
          </div>
          <span class="text-xl font-bold">ClawBuddy</span>
        </div>

        <!-- 登录表单 -->
        <div class="space-y-2 text-center lg:text-left">
          <h2 class="text-2xl font-bold">欢迎回来</h2>
          <p class="text-sm text-muted-foreground">登录以管理你的 AI 助手实例</p>
        </div>

        <div v-if="loading" class="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
          <Loader2 class="w-5 h-5 animate-spin text-primary" />
          <span>正在登录...</span>
        </div>

        <div v-else class="space-y-4">
          <!-- 飞书登录 -->
          <button
            class="w-full py-3 px-4 rounded-xl bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-all hover:shadow-lg hover:shadow-primary/20 flex items-center justify-center gap-2"
            @click="loginWithFeishu"
          >
            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none">
              <path d="M4.5 3L10.5 7.5L6 13.5L19.5 10.5L13.5 16.5L18 21L4.5 3Z" fill="currentColor" opacity="0.9"/>
            </svg>
            使用飞书账号登录
          </button>

          <p v-if="error" class="text-sm text-destructive text-center bg-destructive/10 rounded-lg py-2 px-3">{{ error }}</p>

          <!-- 分割线 -->
          <div class="relative py-2">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-border" />
            </div>
            <div class="relative flex justify-center">
              <span class="bg-background px-3 text-xs text-muted-foreground">企业 SSO 登录</span>
            </div>
          </div>

          <p class="text-xs text-center text-muted-foreground leading-relaxed">
            使用飞书企业账号安全登录，首次登录将自动创建账户并加入组织
          </p>
        </div>

        <!-- 底部 -->
        <div class="pt-8 text-center">
          <p class="text-[11px] text-muted-foreground/50">
            ClawBuddy &copy; 2025 &middot; Powered by OpenClaw
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
