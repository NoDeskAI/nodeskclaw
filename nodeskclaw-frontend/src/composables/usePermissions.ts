import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

export const ORG_ROLES = ['viewer', 'member', 'operator', 'admin'] as const
export type OrgRole = (typeof ORG_ROLES)[number]

export const ROLE_LEVEL: Record<OrgRole, number> = {
  viewer: 10,
  member: 20,
  operator: 30,
  admin: 40,
}

export function usePermissions() {
  const auth = useAuthStore()

  const userRoleLevel = computed(() => {
    if (auth.user?.is_super_admin) return Infinity
    const role = auth.user?.org_role as OrgRole | null
    return role ? (ROLE_LEVEL[role] ?? 0) : 0
  })

  function isAtLeast(minRole: OrgRole): boolean {
    return userRoleLevel.value >= ROLE_LEVEL[minRole]
  }

  function canAccessRoute(minRole?: string): boolean {
    if (!minRole) return true
    if (minRole === 'super_admin') return !!auth.user?.is_super_admin
    return isAtLeast(minRole as OrgRole)
  }

  return { userRoleLevel, isAtLeast, canAccessRoute }
}
