<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { getCurrentLocale, setCurrentLocale } from '@/i18n'
import { PawPrint, Settings, LogOut, Users, BarChart3, Boxes, Server, FlaskConical, User, Languages, ChevronDown } from 'lucide-vue-next'
import ToastContainer from '@/components/shared/ToastContainer.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const isLoginPage = computed(() => route.path === '/login')
const hideNav = computed(() => route.meta.hideNav === true)
const showUserMenu = ref(false)
const userMenuRef = ref<HTMLElement>()
const locale = ref(getCurrentLocale())

function onDocumentClick(e: MouseEvent) {
  if (showUserMenu.value && userMenuRef.value && !userMenuRef.value.contains(e.target as Node)) {
    showUserMenu.value = false
  }
}

onMounted(async () => {
  document.addEventListener('click', onDocumentClick)
  if (authStore.isLoggedIn && !authStore.user) {
    await authStore.fetchUser()
  }
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
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

function onLocaleChange(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  locale.value = setCurrentLocale(value)
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
              {{ t('common.workspace') }}
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path.startsWith('/instances') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/instances')"
            >
              <Server class="w-4 h-4 inline mr-1.5" />
              {{ t('common.instance') }}
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/members' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/members')"
            >
              <Users class="w-4 h-4 inline mr-1.5" />
              {{ t('common.members') }}
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path === '/usage' ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/usage')"
            >
              <BarChart3 class="w-4 h-4 inline mr-1.5" />
              {{ t('common.usage') }}
            </button>
            <button
              :class="[
                'px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path.startsWith('/gene-market') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/gene-market')"
            >
              <FlaskConical class="w-4 h-4 inline mr-1.5" />
              {{ t('common.geneMarket') }}
            </button>
          </nav>
        </div>
        <div class="flex items-center gap-3">
          <div class="relative">
            <Languages class="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <select
              class="h-8 w-[116px] appearance-none rounded-md border border-border bg-card pl-7 pr-6 text-xs font-medium text-foreground"
              :value="locale"
              @change="onLocaleChange"
            >
              <option value="zh-CN">🇨🇳 ZH-CN</option>
              <option value="en-US">🇺🇸 EN-US</option>
            </select>
            <ChevronDown class="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          </div>
          <div class="relative" ref="userMenuRef">
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
              class="absolute right-0 top-full mt-2 w-64 bg-card border border-border rounded-xl shadow-xl z-10 py-1 origin-top-right"
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
                {{ t('common.settings') }}
              </button>
              <button
                class="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-red-400 hover:bg-muted/50 transition-colors"
                @click="handleLogout"
              >
                <LogOut class="w-4 h-4" />
                {{ t('common.logout') }}
              </button>
            </div>
          </Transition>
        </div>
        </div>
      </header>

      <main class="flex-1">
        <router-view />
      </main>
    </div>
  </template>
</template>
