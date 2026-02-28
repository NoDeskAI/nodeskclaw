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
    path: '/setup-org',
    name: 'OrgSetup',
    component: () => import('@/views/OrgSetupView.vue'),
    meta: { requiresAuth: true, allowNoOrg: true },
  },
  // Workspace routes (new primary pages)
  {
    path: '/',
    name: 'WorkspaceList',
    component: () => import('@/views/WorkspaceList.vue'),
  },
  {
    path: '/workspace/create',
    name: 'CreateWorkspace',
    component: () => import('@/views/CreateWorkspace.vue'),
  },
  {
    path: '/workspace/:id',
    name: 'WorkspaceView',
    component: () => import('@/views/WorkspaceView.vue'),
    meta: { hideNav: true },
  },
  {
    path: '/workspace/:id/settings',
    name: 'WorkspaceSettings',
    component: () => import('@/views/WorkspaceSettings.vue'),
  },
  {
    path: '/workspace/:id/add-agent',
    name: 'AddAgent',
    component: () => import('@/views/AddAgent.vue'),
  },
  // Instance routes
  {
    path: '/instances',
    name: 'InstanceList',
    component: () => import('@/views/InstanceList.vue'),
  },
  {
    path: '/instances/create',
    name: 'CreateInstance',
    component: () => import('@/views/CreateInstance.vue'),
  },
  {
    path: '/instances/deploy/:deployId',
    name: 'DeployProgress',
    component: () => import('@/views/DeployProgress.vue'),
  },
  {
    path: '/instances/:id',
    component: () => import('@/views/InstanceLayout.vue'),
    children: [
      { path: '', name: 'InstanceDetail', component: () => import('@/views/InstanceDetail.vue') },
      { path: 'genes', name: 'InstanceGenes', component: () => import('@/views/InstanceGenes.vue') },
      { path: 'evolution', name: 'EvolutionLog', component: () => import('@/views/EvolutionLog.vue') },
      { path: 'mcp', name: 'InstanceMcp', component: () => import('@/views/InstanceMcp.vue') },
      { path: 'settings', name: 'InstanceSettings', component: () => import('@/views/InstanceSettings.vue') },
    ],
  },
  // Kept pages
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
  },
  {
    path: '/members',
    name: 'OrgMembers',
    component: () => import('@/views/OrgMembers.vue'),
  },
  {
    path: '/usage',
    name: 'OrgUsage',
    component: () => import('@/views/OrgUsage.vue'),
  },
  {
    path: '/gene-market',
    name: 'GeneMarket',
    component: () => import('@/views/GeneMarket.vue'),
  },
  {
    path: '/gene-market/gene/:id',
    name: 'GeneDetail',
    component: () => import('@/views/GeneDetail.vue'),
  },
  {
    path: '/gene-market/genome/:id',
    name: 'GenomeDetail',
    component: () => import('@/views/GenomeDetail.vue'),
  },
  // Legacy redirects
  {
    path: '/create',
    redirect: '/workspace/create',
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const token = localStorage.getItem('portal_token')
  const isLoginPage = to.path === '/login' || to.path.startsWith('/login/callback/')
  const isSetupPage = to.path === '/setup-org'

  if (isLoginPage) {
    return next()
  }

  if (!token && to.meta.requiresAuth !== false) {
    return next('/login')
  }

  if (token && !isSetupPage && !to.meta.allowNoOrg) {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    if (!authStore.user) {
      await authStore.fetchUser()
    }
    if (authStore.user && !authStore.user.current_org_id) {
      return next('/setup-org')
    }
  }

  next()
})

export default router
