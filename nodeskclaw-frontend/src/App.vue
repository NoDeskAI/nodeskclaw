<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { getCurrentLocale, setCurrentLocale } from '@/i18n'
import { Toaster } from '@/components/ui/sonner'
import { Notify } from '@/components/ui/notify'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useOrgStore } from '@/stores/org'
import { useGlobalSSE } from '@/composables/useGlobalSSE'
import { useTokenAlert } from '@/composables/useTokenAlert'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import LocaleSelect from '@/components/shared/LocaleSelect.vue'
import {
  LayoutGrid,
  Box,
  Activity,
  Server,
  Settings,
  Bell,
  PanelLeftClose,
  PanelLeftOpen,
  PawPrint,
  Building2,
  CreditCard,
  Users,
  Dna,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const authStore = useAuthStore()
const clusterStore = useClusterStore()
const orgStore = useOrgStore()
const { sseConnected, sseConnecting, clusterConnected, startGlobalSSE, stopGlobalSSE } = useGlobalSSE()
const { tokenWarning, startTokenAlert, stopTokenAlert } = useTokenAlert()
const locale = ref(getCurrentLocale())
const activeClusterId = computed(() => clusterStore.currentCluster?.id ?? clusterStore.currentClusterId)

const isLoginPage = computed(() => route.path === '/login')
const isSuperAdmin = computed(() => authStore.user?.is_super_admin === true)

onMounted(async () => {
  if (authStore.isLoggedIn && !authStore.user) {
    await authStore.fetchUser()
  }
  if (authStore.isLoggedIn) {
    void clusterStore.fetchClusters()
    void orgStore.fetchMyOrgs()
  }
})

// 当集群选择变化时，重新连接全局 SSE + Token 告警轮询
watch(
  [activeClusterId, () => authStore.isLoggedIn],
  ([clusterId, isLoggedIn]) => {
    if (clusterId && isLoggedIn) {
      startGlobalSSE(clusterId)
      startTokenAlert(clusterId)
    } else {
      stopGlobalSSE()
      stopTokenAlert()
    }
  },
  { immediate: true },
)

// SSE 断连恢复：仅在 FatalSSEError 导致 SSE 彻底停止（非连接中）时才重试
const SSE_RECOVERY_INTERVAL_MS = 30_000
let sseRecoveryTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  sseRecoveryTimer = setInterval(() => {
    const clusterId = activeClusterId.value
    if (clusterId && authStore.isLoggedIn && !sseConnected.value && !sseConnecting.value) {
      startGlobalSSE(clusterId)
    }
  }, SSE_RECOVERY_INTERVAL_MS)
})

onUnmounted(() => {
  if (sseRecoveryTimer) {
    clearInterval(sseRecoveryTimer)
    sseRecoveryTimer = null
  }
})

interface NavItem {
  label: string
  icon: Component
  path: string
}

const mainNavItems = computed<NavItem[]>(() => [
  { label: t('nav.dashboard'), icon: LayoutGrid, path: '/' },
  { label: t('nav.instances'), icon: Box, path: '/instances' },
  { label: t('nav.events'), icon: Activity, path: '/events' },
  { label: t('nav.clusters'), icon: Server, path: '/cluster' },
  { label: t('nav.geneOps'), icon: Dna, path: '/gene' },
  { label: t('nav.settings'), icon: Settings, path: '/settings' },
])

const platformNavItems = computed<NavItem[]>(() => {
  if (!isSuperAdmin.value) return []
  return [
    { label: t('nav.organizations'), icon: Building2, path: '/platform/orgs' },
    { label: t('nav.users'), icon: Users, path: '/platform/users' },
    { label: t('nav.plans'), icon: CreditCard, path: '/platform/plans' },
  ]
})

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

const sidebarCollapsed = ref(false)

function navigateTo(path: string) {
  router.push(path)
}

function onLocaleChange(value: string) {
  locale.value = setCurrentLocale(value)
}

const isClusterConnected = computed(() => {
  return clusterConnected.value === true || clusterStore.currentCluster?.status === 'connected'
})

const isClusterDisconnected = computed(() => {
  return clusterConnected.value === false || clusterStore.currentCluster?.status === 'disconnected'
})

const clusterStatusText = computed(() => {
  if (clusterStore.clusters.length === 0) {
    return t('adminApp.footerNoCluster')
  }
  const clusterName = clusterStore.currentCluster?.name || ''
  if (isClusterConnected.value) {
    return t('adminApp.footerConnected', { name: clusterName })
  }
  if (isClusterDisconnected.value) {
    return t('adminApp.footerDisconnected', { name: clusterName })
  }
  return t('adminApp.footerConnecting')
})

const sseStatusText = computed(() => {
  let status: string
  if (sseConnected.value) {
    status = t('adminApp.footerSseNormal')
  } else if (sseConnecting.value) {
    status = t('adminApp.footerSseConnecting')
  } else {
    status = t('adminApp.footerSseStopped')
  }
  return t('adminApp.footerSse', { status })
})
</script>

<template>
  <!-- 登录页：无 Layout -->
  <template v-if="isLoginPage">
    <router-view />
  </template>

  <!-- 主布局 -->
  <template v-else>
    <div class="flex h-screen overflow-hidden">
      <!-- 侧边栏 -->
      <aside
        :class="[
          'shrink-0 border-r border-border bg-card flex flex-col transition-all duration-200',
          sidebarCollapsed ? 'w-[56px]' : 'w-[200px]',
        ]"
      >
        <!-- Logo -->
        <div class="h-14 flex items-center gap-2 px-4 border-b border-border overflow-hidden">
          <PawPrint class="w-5 h-5 text-primary shrink-0" />
          <span v-if="!sidebarCollapsed" class="font-bold text-base whitespace-nowrap">NoDeskClaw</span>
        </div>

        <!-- 组织切换 -->
        <div v-if="orgStore.orgs.length > 1 && !sidebarCollapsed" class="px-2 pt-2">
          <Select
            :model-value="orgStore.currentOrgId ?? undefined"
            @update:model-value="(v: string) => orgStore.switchOrg(v)"
          >
            <SelectTrigger class="h-8 w-full text-xs border-dashed">
              <Building2 class="w-3 h-3 text-muted-foreground shrink-0" />
              <SelectValue :placeholder="t('adminApp.selectOrg')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="o in orgStore.orgs" :key="o.id" :value="o.id">
                {{ o.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <!-- 导航 -->
        <nav class="flex-1 py-2 space-y-0.5 px-2">
          <button
            v-for="item in mainNavItems"
            :key="item.path"
            :title="sidebarCollapsed ? item.label : undefined"
            :class="[
              'w-full flex items-center rounded-md text-sm transition-colors duration-150',
              sidebarCollapsed ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-2',
              isActive(item.path)
                ? 'bg-sidebar-accent text-primary font-medium'
                : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
            ]"
            @click="navigateTo(item.path)"
          >
            <component :is="item.icon" class="w-4 h-4 shrink-0" />
            <span v-if="!sidebarCollapsed">{{ item.label }}</span>
          </button>

          <!-- 平台管理（超管可见） -->
          <template v-if="platformNavItems.length > 0">
            <div class="pt-4 pb-1" :class="sidebarCollapsed ? 'px-0' : 'px-3'">
              <span v-if="!sidebarCollapsed" class="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider">{{ t('nav.platform') }}</span>
              <div v-else class="border-t border-border mx-2" />
            </div>
            <button
              v-for="item in platformNavItems"
              :key="item.path"
              :title="sidebarCollapsed ? item.label : undefined"
              :class="[
                'w-full flex items-center rounded-md text-sm transition-colors duration-150',
                sidebarCollapsed ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-2',
                isActive(item.path)
                  ? 'bg-sidebar-accent text-primary font-medium'
                  : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
              ]"
              @click="navigateTo(item.path)"
            >
              <component :is="item.icon" class="w-4 h-4 shrink-0" />
              <span v-if="!sidebarCollapsed">{{ item.label }}</span>
            </button>
          </template>
        </nav>
      </aside>

      <!-- 主内容区 -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- 顶栏 -->
        <header class="h-14 flex items-center justify-between px-6 border-b border-border bg-background/80 backdrop-blur-sm">
          <div class="flex items-center gap-3">
            <button
              class="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              :title="sidebarCollapsed ? t('adminApp.expandSidebar') : t('adminApp.collapseSidebar')"
              @click="sidebarCollapsed = !sidebarCollapsed"
            >
              <PanelLeftOpen v-if="sidebarCollapsed" class="w-4 h-4" />
              <PanelLeftClose v-else class="w-4 h-4" />
            </button>
            <span class="text-sm font-medium text-muted-foreground">{{ t('nav.adminConsole') }}</span>
          </div>
          <div class="flex items-center gap-4">
            <LocaleSelect :model-value="locale" @update:model-value="onLocaleChange" />
            <!-- 通知 -->
            <button class="relative text-muted-foreground hover:text-foreground transition-colors" @click="router.push('/events')">
              <Bell class="w-4 h-4" />
            </button>
            <!-- 头像 -->
            <div
              class="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-sm text-primary cursor-pointer"
              @click="router.push('/settings')"
            >
              <img
                v-if="authStore.user?.avatar_url"
                :src="authStore.user.avatar_url"
                class="w-8 h-8 rounded-full"
                :alt="t('adminApp.avatarAlt')"
              />
              <span v-else>{{ authStore.user?.name?.charAt(0) || 'U' }}</span>
            </div>
          </div>
        </header>

        <!-- Token 过期告警横幅 -->
        <div
          v-if="tokenWarning === 'expired'"
          class="px-4 py-2 text-sm font-medium text-center bg-red-500/15 text-red-400 border-b border-red-500/20"
        >
          {{ t('adminApp.tokenExpiredPrefix') }}
          <button class="underline font-bold" @click="router.push('/cluster')">{{ t('adminApp.tokenExpiredAction') }}</button>
          {{ t('adminApp.tokenExpiredSuffix') }}
        </div>
        <div
          v-else-if="tokenWarning === 'warning'"
          class="px-4 py-2 text-sm font-medium text-center bg-yellow-500/15 text-yellow-400 border-b border-yellow-500/20"
        >
          {{ t('adminApp.tokenExpiring') }}
        </div>

        <!-- 页面内容 -->
        <main class="flex-1 overflow-y-auto">
          <router-view />
        </main>

        <!-- 底栏 - 真实连接状态 -->
        <footer class="h-8 flex items-center justify-between px-6 text-xs text-muted-foreground border-t border-border bg-card">
          <div class="flex items-center gap-4">
            <span class="flex items-center gap-1.5">
              <span
                class="w-2 h-2 rounded-full inline-block"
                :class="
                  clusterStore.clusters.length === 0 ? 'bg-zinc-500'
                  : (clusterConnected === true || clusterStore.currentCluster?.status === 'connected') ? 'bg-green-400'
                  : (clusterConnected === false || clusterStore.currentCluster?.status === 'disconnected') ? 'bg-red-400'
                  : 'bg-yellow-400'
                "
              />
              {{ clusterStatusText }}
            </span>
            <span v-if="clusterStore.clusters.length > 0" class="flex items-center gap-1.5">
              <span
                class="w-2 h-2 rounded-full inline-block"
                :class="sseConnected ? 'bg-green-400' : sseConnecting ? 'bg-amber-400 animate-pulse' : 'bg-zinc-500'"
              />
              {{ sseStatusText }}
            </span>
          </div>
          <span>NoDeskClaw v0.1.0</span>
        </footer>
      </div>
    </div>

    <!-- Toast (Sonner) -->
    <Toaster position="top-right" :theme="'dark'" />
    <!-- Notify -->
    <Notify />
  </template>
</template>
