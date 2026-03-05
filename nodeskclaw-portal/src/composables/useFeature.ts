import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

export function useFeature(featureId: string) {
  const authStore = useAuthStore()

  const isEnabled = computed(() => {
    const info = authStore.systemInfo
    if (!info) return false
    if (info.edition === 'ee') return true
    const feature = info.features.find(f => f.id === featureId)
    return feature?.enabled ?? false
  })

  return { isEnabled }
}

export function useEdition() {
  const authStore = useAuthStore()

  const edition = computed(() => authStore.systemInfo?.edition ?? 'ce')
  const isEE = computed(() => edition.value === 'ee')

  return { edition, isEE }
}
