import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 导航守卫 — 未认证跳 /login
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const isLoginPage = to.path === '/login'

  if (isLoginPage) {
    // 已登录访问 login 页，跳到首页
    if (token) return next('/')
    return next()
  }

  // 未登录，跳 login（除非 meta.requiresAuth === false）
  if (!token && to.meta.requiresAuth !== false) {
    return next('/login')
  }

  next()
})

export default router
