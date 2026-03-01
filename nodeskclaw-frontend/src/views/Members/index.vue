<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Shield, ShieldCheck, Eye, Wrench, User } from 'lucide-vue-next'
import { useOrgStore } from '@/stores/org'
import { useAuthStore } from '@/stores/auth'
import { useNotify } from '@/components/ui/notify'

const { t } = useI18n()
const orgStore = useOrgStore()
const authStore = useAuthStore()
const notify = useNotify()

const loading = ref(false)

const currentOrgId = computed(() => authStore.user?.current_org_id)

onMounted(async () => {
  if (currentOrgId.value) {
    loading.value = true
    try {
      await orgStore.fetchMembers(currentOrgId.value)
    } finally {
      loading.value = false
    }
  }
})

const roleOptions = [
  { value: 'viewer', labelKey: 'members.role_viewer' },
  { value: 'member', labelKey: 'members.role_member' },
  { value: 'operator', labelKey: 'members.role_operator' },
  { value: 'admin', labelKey: 'members.role_admin' },
]

function roleIcon(role: string) {
  switch (role) {
    case 'admin': return ShieldCheck
    case 'operator': return Wrench
    case 'member': return Shield
    default: return Eye
  }
}

function roleBadgeVariant(role: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (role) {
    case 'admin': return 'default'
    case 'operator': return 'secondary'
    default: return 'outline'
  }
}

async function handleRoleChange(membershipId: string, newRole: string) {
  if (!currentOrgId.value) return
  try {
    await orgStore.updateMemberRole(currentOrgId.value, membershipId, newRole)
    notify.success(t('members.role_updated'))
  } catch (e: any) {
    const msg = e?.response?.data?.detail?.message || e?.response?.data?.message || t('members.role_update_failed')
    notify.error(msg)
  }
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div>
      <h1 class="text-xl font-bold">{{ t('members.title') }}</h1>
      <p class="text-sm text-muted-foreground mt-1">{{ t('members.description') }}</p>
    </div>

    <div class="border rounded-lg divide-y divide-border">
      <div
        v-for="member in orgStore.members"
        :key="member.id"
        class="flex items-center justify-between px-4 py-3"
      >
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden">
            <img v-if="member.user_avatar_url" :src="member.user_avatar_url" class="w-8 h-8 rounded-full" alt="" />
            <User v-else class="w-4 h-4 text-primary" />
          </div>
          <div>
            <div class="text-sm font-medium">{{ member.user_name || member.user_id }}</div>
            <div class="text-xs text-muted-foreground">{{ member.user_email || '-' }}</div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <Badge :variant="roleBadgeVariant(member.role)" class="hidden sm:inline-flex gap-1">
            <component :is="roleIcon(member.role)" class="w-3 h-3" />
            {{ t(`members.role_${member.role}`) }}
          </Badge>
          <Select
            :model-value="member.role"
            @update:model-value="(v: string) => handleRoleChange(member.id, v)"
          >
            <SelectTrigger class="h-7 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem
                v-for="opt in roleOptions"
                :key="opt.value"
                :value="opt.value"
              >
                {{ t(opt.labelKey) }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      <div v-if="!loading && orgStore.members.length === 0" class="px-4 py-8 text-center text-sm text-muted-foreground">
        {{ t('members.empty') }}
      </div>
      <div v-if="loading" class="px-4 py-8 text-center text-sm text-muted-foreground">
        {{ t('members.loading') }}
      </div>
    </div>
  </div>
</template>
