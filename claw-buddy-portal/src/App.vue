<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PawPrint, Home, Plus, Settings, LogOut } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isLoginPage = computed(() => route.path === '/login')

onMounted(async () => {
  if (authStore.isLoggedIn && !authStore.user) {
    await authStore.fetchUser()
  }
})

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<template>
  <template v-if="isLoginPage">
    <router-view />
  </template>

  <template v-else>
    <div class="min-h-screen flex flex-col">
      <!-- 顶部导航栏 -->
      <header class="h-14 flex items-center justify-between px-6 border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-50">
        <div class="flex items-center gap-6">
          <div class="flex items-center gap-2 cursor-pointer" @click="router.push('/')">
            <PawPrint class="w-5 h-5 text-primary" />
            <span class="font-bold text-base">ClawBuddy</span>
          </div>
          <nav class="flex items-center gap-1">
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/')"
            >
              <Home class="w-4 h-4 inline mr-1.5" />
              我的实例
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/create' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/create')"
            >
              <Plus class="w-4 h-4 inline mr-1.5" />
              创建实例
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/settings' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/settings')"
            >
              <Settings class="w-4 h-4 inline mr-1.5" />
              设置
            </button>
          </nav>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-sm text-muted-foreground">{{ authStore.user?.name }}</span>
          <button class="text-muted-foreground hover:text-foreground transition-colors" @click="handleLogout">
            <LogOut class="w-4 h-4" />
          </button>
        </div>
      </header>

      <!-- 页面内容 -->
      <main class="flex-1">
        <router-view />
      </main>
    </div>
  </template>
</template>
