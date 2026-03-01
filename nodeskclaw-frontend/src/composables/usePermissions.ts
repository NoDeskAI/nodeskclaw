import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

export const ADMIN_ROLES = ['member', 'operator', 'admin'] as const
export type AdminRole = (typeof ADMIN_ROLES)[number]

export const ROLE_LEVEL: Record<AdminRole, number> = {
  member: 10,
  operator: 20,
  admin: 30,
}

export function usePermissions() {
  const auth = useAuthStore()

  const userRoleLevel = computed(() => {
    if (auth.user?.is_super_admin) return Infinity
    const role = auth.user?.org_role as AdminRole | null
    return role ? (ROLE_LEVEL[role] ?? 0) : 0
  })

  const hasAdminAccess = computed(() => {
    return auth.user?.is_super_admin || !!auth.user?.org_role
  })

  function isAtLeast(minRole: AdminRole): boolean {
    return userRoleLevel.value >= ROLE_LEVEL[minRole]
  }

  function canAccessRoute(minRole?: string): boolean {
    if (!minRole) return true
    if (minRole === 'super_admin') return !!auth.user?.is_super_admin
    return isAtLeast(minRole as AdminRole)
  }

  return { userRoleLevel, hasAdminAccess, isAtLeast, canAccessRoute }
}
