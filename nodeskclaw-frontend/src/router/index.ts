import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

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
    path: '/',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard/index.vue'),
  },
  {
    path: '/instances',
    name: 'Instances',
    component: () => import('@/views/Instances/index.vue'),
  },
  {
    path: '/instances/:id',
    name: 'InstanceDetail',
    component: () => import('@/views/Instances/Detail.vue'),
  },
  {
    path: '/deploy',
    name: 'Deploy',
    component: () => import('@/views/Deploy/index.vue'),
  },
  {
    path: '/deploy/progress/:deployId',
    name: 'DeployProgress',
    component: () => import('@/views/Deploy/DeployProgress.vue'),
  },
  {
    path: '/instances/:id/logs',
    name: 'Logs',
    component: () => import('@/views/Logs/index.vue'),
  },
  {
    path: '/instances/:id/monitor',
    name: 'Monitor',
    component: () => import('@/views/Monitor/index.vue'),
  },
  {
    path: '/instances/:id/history',
    name: 'History',
    component: () => import('@/views/History/index.vue'),
  },
  {
    path: '/events',
    name: 'Events',
    component: () => import('@/views/Events/index.vue'),
  },
  {
    path: '/cluster',
    name: 'Cluster',
    component: () => import('@/views/Cluster/index.vue'),
  },
  {
    path: '/cluster/:id',
    name: 'ClusterDetail',
    component: () => import('@/views/Cluster/Detail.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings/index.vue'),
  },
  {
    path: '/gene',
    name: 'Gene',
    component: () => import('@/views/Gene/index.vue'),
  },
  // ── 平台管理（超管） ──
  {
    path: '/platform/orgs',
    name: 'PlatformOrgs',
    component: () => import('@/views/Platform/Organizations.vue'),
  },
  {
    path: '/platform/orgs/:orgId/members',
    name: 'PlatformOrgMembers',
    component: () => import('@/views/Platform/OrgMembers.vue'),
  },
  {
    path: '/platform/orgs/:orgId/llm-keys',
    name: 'PlatformOrgLlmKeys',
    component: () => import('@/views/Platform/OrgLlmKeys.vue'),
  },
  {
    path: '/platform/users',
    name: 'PlatformUsers',
    component: () => import('@/views/Platform/Users.vue'),
  },
  {
    path: '/platform/plans',
    name: 'PlatformPlans',
    component: () => import('@/views/Platform/Plans.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const isLoginPage = to.path === '/login' || to.path.startsWith('/login/callback/')

  if (isLoginPage) {
    return next()
  }

  if (!token && to.meta.requiresAuth !== false) {
    return next('/login')
  }

  next()
})

export default router
