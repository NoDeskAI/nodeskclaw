<script setup lang="ts">
import { computed, onMounted, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Toaster } from '@/components/ui/sonner'
import { Notify } from '@/components/ui/notify'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useOrgStore } from '@/stores/org'
import { useGlobalSSE } from '@/composables/useGlobalSSE'
import { useTokenAlert } from '@/composables/useTokenAlert'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  LayoutGrid,
  Box,
  Activity,
  Server,
  Settings,
  Search,
  Bell,
  PawPrint,
  Building2,
  CreditCard,
  Users,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const clusterStore = useClusterStore()
const orgStore = useOrgStore()
const { sseConnected, clusterConnected, startGlobalSSE } = useGlobalSSE()
const { tokenWarning, startTokenAlert, stopTokenAlert } = useTokenAlert()

const isLoginPage = computed(() => route.path === '/login')
const isSuperAdmin = computed(() => authStore.user?.is_super_admin === true)

onMounted(async () => {
  if (authStore.isLoggedIn && !authStore.user) {
    await authStore.fetchUser()
  }
  if (authStore.isLoggedIn) {
    await clusterStore.fetchClusters()
    await orgStore.fetchMyOrgs()
  }
})

// 当集群选择变化时，重新连接全局 SSE + Token 告警轮询
watch(
  () => clusterStore.currentClusterId,
  (newId) => {
    if (newId && authStore.isLoggedIn) {
      startGlobalSSE(newId)
      startTokenAlert(newId)
    } else {
      stopTokenAlert()
    }
  },
  { immediate: true },
)

interface NavItem {
  label: string
  icon: Component
  path: string
}

const mainNavItems: NavItem[] = [
  { label: '总览', icon: LayoutGrid, path: '/' },
  { label: '实例', icon: Box, path: '/instances' },
  { label: '事件', icon: Activity, path: '/events' },
  { label: '集群', icon: Server, path: '/cluster' },
  { label: '设置', icon: Settings, path: '/settings' },
]

const platformNavItems = computed<NavItem[]>(() => {
  if (!isSuperAdmin.value) return []
  return [
    { label: '组织管理', icon: Building2, path: '/platform/orgs' },
    { label: '用户管理', icon: Users, path: '/platform/users' },
    { label: '套餐管理', icon: CreditCard, path: '/platform/plans' },
  ]
})

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

function navigateTo(path: string) {
  router.push(path)
}
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
      <aside class="w-[200px] shrink-0 border-r border-border bg-card flex flex-col">
        <!-- Logo -->
        <div class="h-14 flex items-center gap-2 px-4 border-b border-border">
          <PawPrint class="w-5 h-5 text-primary" />
          <span class="font-bold text-base">ClawBuddy</span>
        </div>

        <!-- 组织切换 -->
        <div v-if="orgStore.orgs.length > 1" class="px-2 pt-2">
          <Select
            :model-value="orgStore.currentOrgId ?? undefined"
            @update:model-value="(v: string) => orgStore.switchOrg(v)"
          >
            <SelectTrigger class="h-8 w-full text-xs border-dashed">
              <Building2 class="w-3 h-3 text-muted-foreground shrink-0" />
              <SelectValue placeholder="选择组织" />
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
            :class="[
              'w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors duration-150',
              isActive(item.path)
                ? 'bg-sidebar-accent text-primary font-medium'
                : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
            ]"
            @click="navigateTo(item.path)"
          >
            <component :is="item.icon" class="w-4 h-4" />
            {{ item.label }}
          </button>

          <!-- 平台管理（超管可见） -->
          <template v-if="platformNavItems.length > 0">
            <div class="pt-4 pb-1 px-3">
              <span class="text-[10px] font-semibold text-muted-foreground/60 uppercase tracking-wider">平台管理</span>
            </div>
            <button
              v-for="item in platformNavItems"
              :key="item.path"
              :class="[
                'w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors duration-150',
                isActive(item.path)
                  ? 'bg-sidebar-accent text-primary font-medium'
                  : 'text-muted-foreground hover:bg-sidebar-accent hover:text-foreground',
              ]"
              @click="navigateTo(item.path)"
            >
              <component :is="item.icon" class="w-4 h-4" />
              {{ item.label }}
            </button>
          </template>
        </nav>
      </aside>

      <!-- 主内容区 -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- 顶栏 -->
        <header class="h-14 flex items-center justify-between px-6 border-b border-border bg-background/80 backdrop-blur-sm">
          <div class="flex items-center gap-4">
            <!-- 集群选择 -->
            <div v-if="clusterStore.clusters.length > 0" class="flex items-center">
              <Select
                :model-value="clusterStore.currentClusterId ?? undefined"
                @update:model-value="(v: string) => clusterStore.selectCluster(v)"
              >
                <SelectTrigger class="h-8 w-auto gap-2 border-none bg-transparent shadow-none text-sm font-medium focus:ring-0 px-2">
                  <Server class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                  <SelectValue placeholder="选择集群" />
                </SelectTrigger>
                <SelectContent align="start">
                  <SelectItem v-for="c in clusterStore.clusters" :key="c.id" :value="c.id">
                    <div class="flex items-center gap-2">
                      <span
                        class="w-1.5 h-1.5 rounded-full shrink-0"
                        :class="c.status === 'connected' ? 'bg-green-400' : c.status === 'connecting' ? 'bg-yellow-400' : 'bg-red-400'"
                      />
                      <span>{{ c.name }}</span>
                      <span v-if="c.k8s_version" class="text-xs text-muted-foreground ml-1">{{ c.k8s_version }}</span>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div v-else class="flex items-center gap-2 text-sm text-muted-foreground px-2">
              <Server class="w-3.5 h-3.5" />
              <span>无集群</span>
            </div>
          </div>
          <div class="flex items-center gap-4">
            <!-- 搜索 -->
            <div class="flex items-center gap-2 px-3 py-1.5 rounded-md bg-card border border-border text-sm text-muted-foreground w-56 cursor-pointer">
              <Search class="w-4 h-4" />
              <span>搜索实例...</span>
            </div>
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
                alt="头像"
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
          集群 Token 已过期，K8s 操作已被阻止。请前往
          <button class="underline font-bold" @click="router.push('/cluster')">集群管理</button>
          更新 KubeConfig。
        </div>
        <div
          v-else-if="tokenWarning === 'warning'"
          class="px-4 py-2 text-sm font-medium text-center bg-yellow-500/15 text-yellow-400 border-b border-yellow-500/20"
        >
          集群 Token 即将过期（不足 6 小时），请及时更新 KubeConfig。
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
              {{
                clusterStore.clusters.length === 0 ? '无集群 - 请先添加集群'
                : (clusterConnected === true || clusterStore.currentCluster?.status === 'connected') ? `已连接: ${clusterStore.currentCluster?.name || ''}`
                : (clusterConnected === false || clusterStore.currentCluster?.status === 'disconnected') ? `集群断开: ${clusterStore.currentCluster?.name || ''}`
                : '连接中...'
              }}
            </span>
            <span v-if="clusterStore.clusters.length > 0" class="flex items-center gap-1.5">
              <span
                class="w-2 h-2 rounded-full inline-block"
                :class="sseConnected ? 'bg-green-400' : 'bg-zinc-500'"
              />
              SSE: {{ sseConnected ? '正常' : '未启动' }}
            </span>
          </div>
          <span>ClawBuddy v0.1.0</span>
        </footer>
      </div>
    </div>

    <!-- Toast (Sonner) -->
    <Toaster position="top-right" :theme="'dark'" />
    <!-- Notify -->
    <Notify />
  </template>
</template>
