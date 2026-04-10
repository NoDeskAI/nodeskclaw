import { onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

let intervalId: ReturnType<typeof setInterval> | null = null
const prevDeployIds = ref<Set<string>>(new Set())

export function useDeployNotification() {
  const store = useWorkspaceStore()
  const authStore = useAuthStore()
  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toast = useToast()

  function shouldPoll() {
    return authStore.isLoggedIn && route.path !== '/login' && route.path !== '/setup-org'
  }

  async function tick() {
    if (!shouldPoll()) return
    const list = await store.refreshActiveTemplateDeploys()
    const curr = new Set(list.map((l) => l.id))
    for (const id of prevDeployIds.value) {
      if (!curr.has(id)) {
        try {
          const d = (await store.fetchWorkspaceDeploy(id)) as {
            status?: string
            workspace_id?: string | null
            workspace_name?: string
          }
          const wid = d.workspace_id
          const name = d.workspace_name || ''
          if (d.status === 'success') {
            toast.success(t('deployNotify.success', { name }), {
              duration: 8000,
              action: wid
                ? {
                    label: t('deployNotify.goTo'),
                    onClick: () => router.push(`/workspace/${wid}`),
                  }
                : undefined,
            })
          } else if (d.status === 'partial_success') {
            toast.info(t('deployNotify.partial', { name }), {
              duration: 8000,
              action: wid
                ? {
                    label: t('deployNotify.goTo'),
                    onClick: () => router.push(`/workspace/${wid}`),
                  }
                : undefined,
            })
          } else if (d.status === 'failed') {
            toast.error(t('deployNotify.failed', { name }))
          }
        } catch {
          /* ignore */
        }
      }
    }
    prevDeployIds.value = curr
  }

  function startInterval() {
    if (intervalId) return
    intervalId = setInterval(() => void tick(), 10000)
  }

  function stopInterval() {
    if (intervalId) {
      clearInterval(intervalId)
      intervalId = null
    }
    prevDeployIds.value = new Set()
  }

  watch(
    () => [authStore.isLoggedIn, route.path] as const,
    () => {
      if (shouldPoll()) {
        void tick()
        startInterval()
      } else {
        stopInterval()
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopInterval()
  })
}
