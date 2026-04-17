import { onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useWorkspaceStore } from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

let timerId: ReturnType<typeof setTimeout> | null = null
let ticking = false
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
    if (ticking) return
    ticking = true
    try {
      if (!shouldPoll()) return
      let list: Awaited<ReturnType<typeof store.fetchActiveWorkspaceDeploys>>
      try {
        list = await store.fetchActiveWorkspaceDeploys()
        store.activeTemplateDeploys = list
      } catch {
        return
      }
      const TERMINAL = new Set(['success', 'partial_success', 'failed'])
      const curr = new Set(list.map((l) => l.id))
      const nextPrev = new Set(curr)
      for (const id of prevDeployIds.value) {
        if (!curr.has(id)) {
          try {
            const d = (await store.fetchWorkspaceDeploy(id)) as {
              status?: string
              workspace_id?: string | null
              workspace_name?: string
            }
            if (TERMINAL.has(d.status || '')) {
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
            } else {
              nextPrev.add(id)
            }
          } catch {
            nextPrev.add(id)
          }
        }
      }
      prevDeployIds.value = nextPrev
    } finally {
      ticking = false
    }
  }

  function scheduleNext() {
    if (timerId) return
    timerId = setTimeout(async () => {
      timerId = null
      await tick()
      if (shouldPoll()) scheduleNext()
    }, 10000)
  }

  function stopTimer() {
    if (timerId) {
      clearTimeout(timerId)
      timerId = null
    }
    prevDeployIds.value = new Set()
  }

  watch(
    () => [authStore.isLoggedIn, route.path] as const,
    () => {
      if (shouldPoll()) {
        void tick()
        scheduleNext()
      } else {
        stopTimer()
      }
    },
    { immediate: true },
  )

  onUnmounted(() => {
    stopTimer()
  })
}
