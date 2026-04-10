<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { getCurrentLocale, setCurrentLocale } from '@/i18n'
import { Settings, LogOut, Boxes, Server, FlaskConical, User, Loader2, BarChart3 } from 'lucide-vue-next'
import { useFeature } from '@/composables/useFeature'
import LocaleSelect from '@/components/shared/LocaleSelect.vue'
import ToastContainer from '@/components/shared/ToastContainer.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import { useDeployNotification } from '@/composables/useDeployNotification'
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const isLoginPage = computed(() => route.path === '/login')
const hideNav = computed(() => route.meta.hideNav === true)
const isSetupPage = computed(() => route.path === '/setup-org')
const showUserMenu = ref(false)
const userMenuRef = ref<HTMLElement>()
const locale = ref(getCurrentLocale())
const appVersion = __APP_VERSION__
const { isEnabled: isPerformanceEnabled } = useFeature('performance_analytics')

useDeployNotification()

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

async function handleLogout() {
  showUserMenu.value = false
  await authStore.logout()
  router.push('/login')
}

function navigateFromMenu(path: string) {
  showUserMenu.value = false
  router.push(path)
}

function onLocaleChange(value: string) {
  locale.value = setCurrentLocale(value)
}
</script>

<template>
  <ToastContainer />
  <ConfirmDialog />

  <template v-if="isLoginPage">
    <router-view />
  </template>

  <template v-else-if="hideNav">
    <router-view />
  </template>

  <template v-else-if="authStore.isLoggedIn && authStore.user">
    <div class="min-h-screen flex flex-col">
      <header class="h-14 flex items-center justify-between px-6 border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-50">
        <div class="flex items-center gap-6 min-w-0">
          <div class="flex items-center gap-2 shrink-0 cursor-pointer" @click="router.push('/')">
            <img src="/logo.png" alt="DeskClaw" class="w-5 h-5" />
            <span class="font-bold text-base">DeskClaw</span>
            <span class="px-1.5 py-0.5 text-[10px] font-semibold leading-none rounded bg-primary/15 text-primary">{{ appVersion }}</span>
          </div>
          <nav v-if="!isSetupPage" class="flex items-center gap-1 overflow-x-auto min-w-0">
            <button
              :class="[
                'shrink-0 whitespace-nowrap px-3 py-1.5 rounded-md text-sm transition-colors',
                (route.path === '/' || route.path.startsWith('/workspace')) && !route.path.startsWith('/instances') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/')"
            >
              <Boxes class="w-4 h-4 inline mr-1.5" />
              <span class="hidden lg:inline">{{ t('common.workspace') }}</span>
              <span class="lg:hidden">{{ t('nav.workspace') }}</span>
            </button>
            <button
              :class="[
                'shrink-0 whitespace-nowrap px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path.startsWith('/instances') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/instances')"
            >
              <Server class="w-4 h-4 inline mr-1.5" />
              {{ t('common.instance') }}
            </button>
            <button
              :class="[
                'shrink-0 whitespace-nowrap px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path.startsWith('/gene-market') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/gene-market')"
            >
              <FlaskConical class="w-4 h-4 inline mr-1.5" />
              <span class="hidden lg:inline">{{ t('common.geneMarket') }}</span>
              <span class="lg:hidden">{{ t('nav.geneMarket') }}</span>
            </button>
            <button
              v-if="isPerformanceEnabled"
              :class="[
                'shrink-0 whitespace-nowrap px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path.startsWith('/agent-performance') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/agent-performance')"
            >
              <BarChart3 class="w-4 h-4 inline mr-1.5" />
              <span class="hidden lg:inline">{{ t('agentPerformance.navTitle') }}</span>
              <span class="lg:hidden">{{ t('nav.agentPerformance') }}</span>
            </button>
            <button
              v-if="authStore.user?.portal_org_role === 'admin'"
              :class="[
                'shrink-0 whitespace-nowrap px-3 py-1.5 rounded-md text-sm transition-colors',
                route.path.startsWith('/org-settings') ? 'bg-primary/10 text-primary font-medium' : 'text-muted-foreground hover:text-foreground',
              ]"
              @click="router.push('/org-settings')"
            >
              <Settings class="w-4 h-4 inline mr-1.5" />
              <span class="hidden lg:inline">{{ t('orgSettings.navTitle') }}</span>
              <span class="lg:hidden">{{ t('nav.orgSettings') }}</span>
            </button>
          </nav>
        </div>
        <div class="flex items-center gap-3">
          <LocaleSelect :model-value="locale" @update:model-value="onLocaleChange" />
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
                v-if="!isSetupPage"
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

  <template v-else-if="route.meta.requiresAuth === false">
    <router-view />
  </template>

  <template v-else>
    <div class="h-screen flex items-center justify-center">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>
  </template>
</template>
