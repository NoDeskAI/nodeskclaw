<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PawPrint, Settings, LogOut, Users, BarChart3, Boxes, Server, Dna, FlaskConical, User } from 'lucide-vue-next'
import ToastContainer from '@/components/shared/ToastContainer.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isLoginPage = computed(() => route.path === '/login')
const hideNav = computed(() => route.meta.hideNav === true)
const showUserMenu = ref(false)

onMounted(async () => {
  if (authStore.isLoggedIn && !authStore.user) {
    await authStore.fetchUser()
  }
})

function handleLogout() {
  showUserMenu.value = false
  authStore.logout()
  router.push('/login')
}

function navigateFromMenu(path: string) {
  showUserMenu.value = false
  router.push(path)
}
</script>

<template>
  <ToastContainer />

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
                route.path.startsWith('/gene-market') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/gene-market')"
            >
              <FlaskConical class="w-4 h-4 inline mr-1.5" />
              基因市场
            </button>
            <button
              v-if="authStore.isLoggedIn"
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/admin/genes' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/admin/genes')"
            >
              <Dna class="w-4 h-4 inline mr-1.5" />
              基因运营
            </button>
          </nav>
        </div>
        <div class="relative">
          <button
            class="w-8 h-8 rounded-full overflow-hidden flex items-center justify-center bg-primary/10 hover:ring-2 hover:ring-primary/30 transition-all"
            @click="showUserMenu = !showUserMenu"
          >
            <img
              v-if="authStore.user?.avatar_url"
              :src="authStore.user.avatar_url"
              class="w-8 h-8 rounded-full object-cover"
              alt=""
            />
            <User v-else class="w-4 h-4 text-primary" />
          </button>

          <Teleport to="body">
            <div v-if="showUserMenu" class="fixed inset-0 z-99" @click="showUserMenu = false" />
          </Teleport>

          <Transition
            enter-active-class="transition duration-150 ease-out"
            enter-from-class="opacity-0 scale-95 -translate-y-1"
            enter-to-class="opacity-100 scale-100 translate-y-0"
            leave-active-class="transition duration-100 ease-in"
            leave-from-class="opacity-100 scale-100 translate-y-0"
            leave-to-class="opacity-0 scale-95 -translate-y-1"
          >
            <div
              v-if="showUserMenu"
              class="absolute right-0 top-full mt-2 w-64 bg-card border border-border rounded-xl shadow-xl z-100 py-1 origin-top-right"
            >
              <div class="px-4 py-3 flex items-center gap-3">
                <div class="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <img
                    v-if="authStore.user?.avatar_url"
                    :src="authStore.user.avatar_url"
                    class="w-10 h-10 rounded-full object-cover"
                    alt=""
                  />
                  <User v-else class="w-5 h-5 text-primary" />
                </div>
                <div class="min-w-0">
                  <div class="font-medium text-sm truncate">{{ authStore.user?.name }}</div>
                  <div class="text-xs text-muted-foreground truncate">{{ authStore.user?.email || '-' }}</div>
                </div>
              </div>
              <div class="h-px bg-border mx-2" />
              <button
                class="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-muted/50 transition-colors"
                @click="navigateFromMenu('/settings')"
              >
                <Settings class="w-4 h-4 text-muted-foreground" />
                设置
              </button>
              <button
                class="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-400 hover:bg-muted/50 transition-colors"
                @click="handleLogout"
              >
                <LogOut class="w-4 h-4" />
                退出登录
              </button>
            </div>
          </Transition>
        </div>
      </header>

      <main class="flex-1">
        <router-view />
      </main>
    </div>
  </template>
</template>
