<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PawPrint, Settings, LogOut, Users, BarChart3, Boxes, Server } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isLoginPage = computed(() => route.path === '/login')
const hideNav = computed(() => route.meta.hideNav === true)

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

  <template v-else-if="hideNav">
    <router-view />
  </template>

  <template v-else>
    <div class="min-h-screen flex flex-col">
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
                (route.path === '/' || route.path.startsWith('/workspace')) && !route.path.startsWith('/instances') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/')"
            >
              <Boxes class="w-4 h-4 inline mr-1.5" />
              工作区
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path.startsWith('/instances') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/instances')"
            >
              <Server class="w-4 h-4 inline mr-1.5" />
              实例
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/members' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/members')"
            >
              <Users class="w-4 h-4 inline mr-1.5" />
              成员
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/usage' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/usage')"
            >
              <BarChart3 class="w-4 h-4 inline mr-1.5" />
              用量
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

      <main class="flex-1">
        <router-view />
      </main>
    </div>
  </template>
</template>
