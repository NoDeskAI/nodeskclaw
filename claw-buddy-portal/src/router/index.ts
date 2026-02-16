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
    name: 'Home',
    component: () => import('@/views/Home.vue'),
  },
  {
    path: '/create',
    name: 'CreateInstance',
    component: () => import('@/views/CreateInstance.vue'),
  },
  {
    path: '/instances/:id',
    name: 'InstanceDetail',
    component: () => import('@/views/InstanceDetail.vue'),
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
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
