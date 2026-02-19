import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false },
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
    name: 'InstanceDetail',
    component: () => import('@/views/InstanceDetail.vue'),
  },
  {
    path: '/instances/:id/settings',
    name: 'InstanceSettings',
    component: () => import('@/views/InstanceSettings.vue'),
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

router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('portal_token')
  const isLoginPage = to.path === '/login'

  if (isLoginPage) {
    if (token) return next('/')
    return next()
  }

  if (!token && to.meta.requiresAuth !== false) {
    return next('/login')
  }

  next()
})

export default router
