import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    minRole?: string
  }
}

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/login/callback/:provider',
    name: 'OAuthCallback',
    component: () => import('@/views/OAuthCallback.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/no-access',
    name: 'NoAccess',
    component: () => import('@/views/NoAccess.vue'),
    meta: { minRole: 'viewer' },
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard/index.vue'),
    meta: { minRole: 'member' },
  },
  {
    path: '/instances',
    name: 'Instances',
    component: () => import('@/views/Instances/index.vue'),
    meta: { minRole: 'member' },
  },
  {
    path: '/instances/:id',
    name: 'InstanceDetail',
    component: () => import('@/views/Instances/Detail.vue'),
    meta: { minRole: 'member' },
  },
  {
    path: '/deploy',
    name: 'Deploy',
    component: () => import('@/views/Deploy/index.vue'),
    meta: { minRole: 'operator' },
  },
  {
    path: '/deploy/progress/:deployId',
    name: 'DeployProgress',
    component: () => import('@/views/Deploy/DeployProgress.vue'),
    meta: { minRole: 'operator' },
  },
  {
    path: '/instances/:id/logs',
    name: 'Logs',
    component: () => import('@/views/Logs/index.vue'),
    meta: { minRole: 'member' },
  },
  {
    path: '/instances/:id/monitor',
    name: 'Monitor',
    component: () => import('@/views/Monitor/index.vue'),
    meta: { minRole: 'member' },
  },
  {
    path: '/instances/:id/history',
    name: 'History',
    component: () => import('@/views/History/index.vue'),
    meta: { minRole: 'member' },
  },
  {
    path: '/events',
    name: 'Events',
    component: () => import('@/views/Events/index.vue'),
    meta: { minRole: 'member' },
  },
  {
    path: '/cluster',
    name: 'Cluster',
    component: () => import('@/views/Cluster/index.vue'),
    meta: { minRole: 'admin' },
  },
  {
    path: '/cluster/:id',
    name: 'ClusterDetail',
    component: () => import('@/views/Cluster/Detail.vue'),
    meta: { minRole: 'admin' },
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings/index.vue'),
    meta: { minRole: 'admin' },
  },
  {
    path: '/gene',
    name: 'Gene',
    component: () => import('@/views/Gene/index.vue'),
    meta: { minRole: 'admin' },
  },
  {
    path: '/members',
    name: 'Members',
    component: () => import('@/views/Members/index.vue'),
    meta: { minRole: 'admin' },
  },
  // ── 平台管理（超管） ──
  {
    path: '/platform/orgs',
    name: 'PlatformOrgs',
    component: () => import('@/views/Platform/Organizations.vue'),
    meta: { minRole: 'super_admin' },
  },
  {
    path: '/platform/orgs/:orgId/members',
    name: 'PlatformOrgMembers',
    component: () => import('@/views/Platform/OrgMembers.vue'),
    meta: { minRole: 'super_admin' },
  },
  {
    path: '/platform/orgs/:orgId/llm-keys',
    name: 'PlatformOrgLlmKeys',
    component: () => import('@/views/Platform/OrgLlmKeys.vue'),
    meta: { minRole: 'super_admin' },
  },
  {
    path: '/platform/users',
    name: 'PlatformUsers',
    component: () => import('@/views/Platform/Users.vue'),
    meta: { minRole: 'super_admin' },
  },
  {
    path: '/platform/plans',
    name: 'PlatformPlans',
    component: () => import('@/views/Platform/Plans.vue'),
    meta: { minRole: 'super_admin' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const token = localStorage.getItem('token')
  const isLoginPage = to.path === '/login' || to.path.startsWith('/login/callback/')

  if (isLoginPage) {
    return next()
  }

  if (!token && to.meta.requiresAuth !== false) {
    return next('/login')
  }

  const auth = useAuthStore()
  if (token && !auth.user) {
    await auth.fetchUser()
  }

  if (!auth.user) {
    return next('/login')
  }

  const { canAccessRoute } = usePermissions()
  const minRole = to.meta.minRole
  if (minRole && !canAccessRoute(minRole)) {
    return next('/no-access')
  }

  next()
})

export default router
