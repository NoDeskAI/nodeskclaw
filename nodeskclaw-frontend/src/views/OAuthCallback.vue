<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const error = ref('')

onMounted(async () => {
  const provider = route.params.provider as string
  const code = new URLSearchParams(window.location.search).get('code')

  if (!provider || !code) {
    error.value = '回调参数缺失，请重新登录'
    return
  }

  try {
    await authStore.oauthLogin(provider, code)
    router.replace('/')
  } catch (e: any) {
    const msg = e instanceof Error ? e.message : '登录失败'
    error.value = msg
  }
})
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background">
    <div v-if="error" class="text-center space-y-4 max-w-sm px-4">
      <p class="text-sm text-destructive">{{ error }}</p>
      <button
        class="text-sm text-primary hover:text-primary/80 transition-colors"
        @click="router.replace('/login')"
      >
        返回登录页
      </button>
    </div>
    <p v-else class="text-sm text-muted-foreground">登录中...</p>
  </div>
</template>
