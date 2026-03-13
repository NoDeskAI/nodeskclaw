import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { i18n } from '@/i18n'
import { eePortalRoutes, eeOrgSettingsChildren } from '@/router/ee-stub'

const ceRoutes: RouteRecordRaw[] = [
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
    path: '/force-change-password',
    name: 'ForceChangePassword',
    component: () => import('@/views/ForceChangePassword.vue'),
    meta: { requiresAuth: true, hideNav: true },
  },
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

      { path: 'channels', name: 'InstanceChannels', component: () => import('@/views/InstanceChannels.vue') },
      { path: 'settings', name: 'InstanceSettings', component: () => import('@/views/InstanceSettings.vue') },
      { path: 'files', name: 'InstanceFiles', component: () => import('@/views/InstanceFiles.vue') },
      { path: 'members', name: 'InstanceMembers', component: () => import('@/views/InstanceMembers.vue') },
    ],
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/views/Settings.vue'),
  },
  {
    path: '/org-settings',
    component: () => import('@/views/OrgSettings.vue'),
    redirect: { name: 'OrgInfo' },
    children: [
      { path: 'info', name: 'OrgInfo', component: () => import('@/views/OrgInfo.vue') },
      { path: 'clusters', name: 'OrgSettingsClusters', component: () => import('@/views/OrgSettingsClusters.vue'), meta: { ceOnly: true } },
      { path: 'registry', name: 'OrgSettingsRegistry', component: () => import('@/views/OrgSettingsRegistry.vue'), meta: { ceOnly: true } },
      { path: 'genes', name: 'OrgSettingsGenes', component: () => import('@/views/OrgSettingsGenes.vue') },
      { path: 'smtp', name: 'OrgSettingsSmtp', component: () => import('@/views/OrgSettingsSmtp.vue'), meta: { ceOnly: true } },
      { path: 'members', name: 'OrgMembers', component: () => import('@/views/OrgMembers.vue') },
      { path: 'audit', name: 'OrgSettingsAudit', component: () => import('@/views/OrgSettingsAudit.vue') },
      ...eeOrgSettingsChildren,
    ],
  },
  {
    path: '/clusters/:id',
    name: 'ClusterDetail',
    component: () => import('@/views/ClusterDetail.vue'),
    meta: { ceOnly: true },
  },
  {
    path: '/members',
    redirect: '/org-settings',
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
  {
    path: '/gene-market/template/:id',
    name: 'TemplateDetail',
    component: () => import('@/views/TemplateDetail.vue'),
  },
  {
    path: '/create',
    redirect: '/workspace/create',
  },
  {
    path: '/invite/:token',
    name: 'AcceptInvite',
    component: () => import('@/views/AcceptInvite.vue'),
    meta: { requiresAuth: false },
  },
]

const routes: RouteRecordRaw[] = [...ceRoutes, ...eePortalRoutes]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const token = localStorage.getItem('portal_token')
  const isLoginPage = to.path === '/login' || to.path.startsWith('/login/callback/')
  const isInvitePage = to.path.startsWith('/invite/')
  const isSetupPage = to.path === '/setup-org'

  if (isLoginPage || isInvitePage) {
    return next()
  }

  if (!token && to.meta.requiresAuth !== false) {
    return next('/login')
  }

  if (token) {
    const { useAuthStore } = await import('@/stores/auth')
    const authStore = useAuthStore()
    if (!authStore.systemInfo) {
      await authStore.fetchSystemInfo()
    }
    if (!authStore.user) {
      await authStore.fetchUser()
    }

    if (authStore.user?.must_change_password && to.path !== '/force-change-password') {
      return next('/force-change-password')
    }

    if (!isSetupPage && !to.meta.allowNoOrg && to.path !== '/force-change-password') {
      if (authStore.user && !authStore.user.current_org_id && router.hasRoute('OrgSetup')) {
        return next('/setup-org')
      }
    }

    if (to.meta.ceOnly && authStore.systemInfo?.edition === 'ee') {
      return next('/')
    }

    const requiredFeature = to.meta.requireFeature as string | undefined
    if (requiredFeature && authStore.systemInfo) {
      const feat = authStore.systemInfo.features.find((f: any) => f.id === requiredFeature)
      if (!feat?.enabled) {
        return next('/')
      }
    }
  }

  next()
})

router.afterEach(() => {
  const { t } = i18n.global
  document.title = t('common.appTitle')
})

export default router
