<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOrgStore, type MemberInfo } from '@/stores/org'
import { useAuthStore } from '@/stores/auth'
import {
  Users,
  UserPlus,
  Loader2,
  Search,
  Crown,
  Shield,
  Trash2,
  X,
  KeyRound,
  Copy,
  Check,
  Link,
  Mail,
  Clock,
  Plus,
} from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import CustomSelect from '@/components/shared/CustomSelect.vue'

const orgStore = useOrgStore()
const authStore = useAuthStore()
const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()

const loading = ref(true)
const searchQuery = ref('')
const actionLoading = ref<string | null>(null)

// invite dialog
const showInviteDialog = ref(false)
const inviteEmails = ref<string[]>([])
const inviteEmailInput = ref('')
const inviteRole = ref('member')
const inviteLoading = ref(false)
const inviteResults = ref<Array<{ email: string; status: string; invite_url?: string; email_sent?: boolean }>>([])
const showInviteResults = ref(false)
const copiedUrl = ref<string | null>(null)

// roles
const roles = ref<Array<{ id: string; name_key: string }>>([])

// pending invitations
const pendingInvitations = ref<Array<{
  id: string; email: string; role: string; status: string;
  created_at: string; expires_at: string; invite_url: string
}>>([])

// reset password
const showResetResultDialog = ref(false)
const resetResultName = ref('')
const resetResultPassword = ref('')
const resetCopied = ref(false)

const isOrgAdmin = computed(() => authStore.user?.portal_org_role === 'admin')

const roleOptions = computed(() =>
  roles.value.map(r => ({ value: r.id, label: t(r.name_key) }))
)

const filteredMembers = computed(() => {
  if (!searchQuery.value) return orgStore.members
  const q = searchQuery.value.toLowerCase()
  return orgStore.members.filter(
    m =>
      (m.user_name?.toLowerCase().includes(q)) ||
      (m.user_email?.toLowerCase().includes(q))
  )
})

const filteredPending = computed(() => {
  if (!searchQuery.value) return pendingInvitations.value.filter(i => i.status === 'pending')
  const q = searchQuery.value.toLowerCase()
  return pendingInvitations.value.filter(
    i => i.status === 'pending' && i.email.toLowerCase().includes(q)
  )
})

onMounted(async () => {
  if (!orgStore.currentOrgId) {
    await orgStore.fetchCurrentOrg()
  }
  if (orgStore.currentOrgId) {
    await Promise.all([
      orgStore.fetchMembers(),
      fetchRoles(),
      fetchPendingInvitations(),
    ])
  }
  loading.value = false
})

async function fetchRoles() {
  if (!orgStore.currentOrgId) return
  try {
    const res = await api.get(`/orgs/${orgStore.currentOrgId}/roles`)
    roles.value = res.data.data ?? []
  } catch {
    roles.value = [
      { id: 'admin', name_key: 'orgMembers.roleAdmin' },
      { id: 'member', name_key: 'orgMembers.roleMember' },
    ]
  }
}

async function fetchPendingInvitations() {
  if (!orgStore.currentOrgId || !isOrgAdmin.value) return
  try {
    const res = await api.get(`/orgs/${orgStore.currentOrgId}/invitations`)
    pendingInvitations.value = res.data.data ?? []
  } catch {
    pendingInvitations.value = []
  }
}

function addEmailTag() {
  const raw = inviteEmailInput.value.trim()
  if (!raw) return
  const parts = raw.split(/[,;\s]+/).filter(Boolean)
  for (const email of parts) {
    const normalized = email.toLowerCase().trim()
    if (normalized && !inviteEmails.value.includes(normalized)) {
      inviteEmails.value.push(normalized)
    }
  }
  inviteEmailInput.value = ''
}

function removeEmailTag(email: string) {
  inviteEmails.value = inviteEmails.value.filter(e => e !== email)
}

function handleEmailKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault()
    addEmailTag()
  }
  if (e.key === 'Backspace' && !inviteEmailInput.value && inviteEmails.value.length > 0) {
    inviteEmails.value.pop()
  }
}

function handleEmailPaste(e: ClipboardEvent) {
  e.preventDefault()
  const text = e.clipboardData?.getData('text') ?? ''
  const parts = text.split(/[,;\s]+/).filter(Boolean)
  for (const email of parts) {
    const normalized = email.toLowerCase().trim()
    if (normalized && !inviteEmails.value.includes(normalized)) {
      inviteEmails.value.push(normalized)
    }
  }
}

async function handleInvite() {
  addEmailTag()
  if (inviteEmails.value.length === 0) return
  inviteLoading.value = true
  try {
    const res = await api.post(`/orgs/${orgStore.currentOrgId}/members/invite`, {
      emails: inviteEmails.value,
      role: inviteRole.value,
    })
    inviteResults.value = res.data.data ?? []
    showInviteResults.value = true
    await Promise.all([
      orgStore.fetchMembers(),
      fetchPendingInvitations(),
    ])
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('orgMembers.inviteFailed')))
  } finally {
    inviteLoading.value = false
  }
}

function closeInviteDialog() {
  showInviteDialog.value = false
  inviteEmails.value = []
  inviteEmailInput.value = ''
  inviteRole.value = 'member'
  inviteResults.value = []
  showInviteResults.value = false
}

async function copyInviteUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url)
    copiedUrl.value = url
    setTimeout(() => { copiedUrl.value = null }, 2000)
  } catch {
    toast.error('Copy failed')
  }
}

async function cancelInvitation(id: string) {
  if (!orgStore.currentOrgId) return
  actionLoading.value = id
  try {
    await api.delete(`/orgs/${orgStore.currentOrgId}/invitations/${id}`)
    pendingInvitations.value = pendingInvitations.value.filter(i => i.id !== id)
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('orgMembers.cancelInviteFailed')))
  } finally {
    actionLoading.value = null
  }
}

async function handleRoleChange(member: MemberInfo, newRole: string) {
  if (member.role === newRole) return
  actionLoading.value = member.id
  try {
    await orgStore.updateMemberRole(member.id, newRole)
  } catch (e: any) {
    toast.error(e?.response?.data?.message || t('orgMembers.updateRoleFailed'))
  } finally {
    actionLoading.value = null
  }
}

async function handleRemove(member: MemberInfo) {
  const ok = await confirm({
    title: t('orgMembers.removeMemberTitle'),
    description: t('orgMembers.removeConfirm', { name: member.user_name || member.user_email }),
    variant: 'danger',
  })
  if (!ok) return
  actionLoading.value = member.id
  try {
    await orgStore.removeMember(member.id)
  } catch (e: any) {
    toast.error(e?.response?.data?.message || t('orgMembers.removeFailed'))
  } finally {
    actionLoading.value = null
  }
}

async function handleResetPassword(member: MemberInfo) {
  const name = member.user_name || member.user_email || member.user_id
  const ok = await confirm({
    title: t('orgMembers.resetPassword'),
    description: t('orgMembers.resetPasswordConfirm', { name }),
    variant: 'danger',
  })
  if (!ok) return
  actionLoading.value = member.id
  try {
    const res = await api.post(`/orgs/${orgStore.currentOrgId}/members/${member.user_id}/reset-password`)
    resetResultName.value = name
    resetResultPassword.value = res.data.data.password
    resetCopied.value = false
    showResetResultDialog.value = true
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('orgMembers.resetPasswordFailed')))
  } finally {
    actionLoading.value = null
  }
}

async function copyPassword() {
  try {
    await navigator.clipboard.writeText(resetResultPassword.value)
    resetCopied.value = true
    setTimeout(() => { resetCopied.value = false }, 2000)
  } catch {
    toast.error('Copy failed')
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-base font-semibold">{{ t('orgMembers.title') }}</h2>
        <p class="text-sm text-muted-foreground mt-0.5">
          {{ t('orgMembers.subtitle', { orgName: orgStore.currentOrg?.name || t('orgMembers.orgFallback') }) }}
        </p>
      </div>
      <button
        v-if="isOrgAdmin"
        class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="showInviteDialog = true"
      >
        <UserPlus class="w-4 h-4" />
        {{ t('orgMembers.inviteMember') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <!-- No Org -->
    <div v-else-if="!orgStore.currentOrg" class="text-center py-20 space-y-3">
      <Users class="w-12 h-12 mx-auto text-muted-foreground/40" />
      <p class="text-muted-foreground">{{ t('orgMembers.noOrg') }}</p>
    </div>

    <!-- Members List -->
    <template v-else>
      <!-- Search -->
      <div class="relative mb-4">
        <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="t('orgMembers.searchPlaceholder')"
          class="w-full pl-9 pr-4 py-2 rounded-lg border border-border bg-card text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>

      <!-- Member Count -->
      <p class="text-xs text-muted-foreground mb-3">
        {{ t('orgMembers.memberCount', { count: filteredMembers.length }) }}
      </p>

      <div class="space-y-2">
        <!-- Active Members -->
        <div
          v-for="member in filteredMembers"
          :key="member.id"
          class="flex items-center justify-between p-4 rounded-xl border border-border bg-card"
        >
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-full bg-primary/15 flex items-center justify-center text-sm font-medium text-primary shrink-0 overflow-hidden">
              <img v-if="member.user_avatar_url" :src="member.user_avatar_url" class="w-9 h-9 rounded-full" alt="" />
              <span v-else>{{ (member.user_name || '?').charAt(0) }}</span>
            </div>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-medium text-sm">{{ member.user_name || t('orgMembers.unknownUser') }}</span>
                <span
                  v-if="member.user_id === authStore.user?.id"
                  class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/15 text-primary"
                >{{ t('orgMembers.me') }}</span>
                <span
                  v-if="member.is_super_admin"
                  class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-500/15 text-red-400"
                >
                  <Crown class="w-3 h-3" />
                  {{ t('orgMembers.roleSuperAdmin') }}
                </span>
                <span
                  v-else-if="member.role === 'admin'"
                  class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-400"
                >
                  <Crown class="w-3 h-3" />
                  {{ t('orgMembers.roleAdmin') }}
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-500/10 text-blue-400"
                >
                  <Shield class="w-3 h-3" />
                  {{ t('orgMembers.roleMember') }}
                </span>
              </div>
              <p class="text-xs text-muted-foreground mt-0.5">{{ member.user_email || '-' }}</p>
            </div>
          </div>

          <!-- Actions (admin only, not self) -->
          <div v-if="isOrgAdmin && member.user_id !== authStore.user?.id" class="flex items-center gap-2">
            <CustomSelect
              :model-value="member.role"
              :options="roleOptions"
              size="xs"
              :disabled="actionLoading === member.id"
              @update:model-value="(v: string | null) => handleRoleChange(member, v!)"
            />
            <button
              v-if="member.role !== 'admin'"
              class="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
              :disabled="actionLoading === member.id"
              :title="t('orgMembers.resetPassword')"
              @click="handleResetPassword(member)"
            >
              <KeyRound class="w-4 h-4" />
            </button>
            <button
              class="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
              :disabled="actionLoading === member.id"
              @click="handleRemove(member)"
            >
              <Loader2 v-if="actionLoading === member.id" class="w-4 h-4 animate-spin" />
              <Trash2 v-else class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Pending Invitations -->
        <template v-if="isOrgAdmin && filteredPending.length > 0">
          <p class="text-xs text-muted-foreground mt-4 mb-2">{{ t('orgMembers.pendingInvitations', { count: filteredPending.length }) }}</p>
          <div
            v-for="inv in filteredPending"
            :key="inv.id"
            class="flex items-center justify-between p-4 rounded-xl border border-dashed border-border bg-card/50"
          >
            <div class="flex items-center gap-3">
              <div class="w-9 h-9 rounded-full bg-muted flex items-center justify-center text-sm text-muted-foreground shrink-0">
                <Mail class="w-4 h-4" />
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <span class="font-medium text-sm text-muted-foreground">{{ inv.email }}</span>
                  <span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-yellow-500/15 text-yellow-500">
                    <Clock class="w-3 h-3" />
                    {{ t('orgMembers.pending') }}
                  </span>
                </div>
                <p class="text-xs text-muted-foreground mt-0.5">{{ t(roles.find(r => r.id === inv.role)?.name_key || 'orgMembers.roleMember') }}</p>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                :title="t('orgMembers.copyInviteLink')"
                @click="copyInviteUrl(inv.invite_url)"
              >
                <Check v-if="copiedUrl === inv.invite_url" class="w-4 h-4 text-green-500" />
                <Link v-else class="w-4 h-4" />
              </button>
              <button
                class="p-1.5 rounded-md text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                :disabled="actionLoading === inv.id"
                @click="cancelInvitation(inv.id)"
              >
                <Loader2 v-if="actionLoading === inv.id" class="w-4 h-4 animate-spin" />
                <X v-else class="w-4 h-4" />
              </button>
            </div>
          </div>
        </template>
      </div>

      <div v-if="filteredMembers.length === 0 && filteredPending.length === 0 && !loading" class="text-center py-12 text-muted-foreground text-sm">
        {{ t('orgMembers.noMatch') }}
      </div>
    </template>

    <!-- Invite Member Dialog -->
    <Teleport to="body">
      <div
        v-if="showInviteDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="closeInviteDialog"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-md p-6 space-y-4">
          <!-- Header -->
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ t('orgMembers.inviteDialogTitle') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="closeInviteDialog">
              <X class="w-4 h-4" />
            </button>
          </div>

          <template v-if="!showInviteResults">
            <!-- Email Input -->
            <div class="space-y-2">
              <label class="text-sm text-muted-foreground">{{ t('orgMembers.emailLabel') }}</label>
              <div class="min-h-[42px] flex flex-wrap gap-1.5 p-2 rounded-lg border border-border bg-background focus-within:ring-2 focus-within:ring-primary/30">
                <span
                  v-for="email in inviteEmails"
                  :key="email"
                  class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-medium"
                >
                  {{ email }}
                  <button class="hover:text-red-400" @click="removeEmailTag(email)">
                    <X class="w-3 h-3" />
                  </button>
                </span>
                <input
                  v-model="inviteEmailInput"
                  type="text"
                  :placeholder="inviteEmails.length === 0 ? t('orgMembers.emailPlaceholder') : ''"
                  class="flex-1 min-w-[120px] bg-transparent text-sm outline-none"
                  @keydown="handleEmailKeydown"
                  @paste="handleEmailPaste"
                  @blur="addEmailTag"
                />
              </div>
              <p class="text-xs text-muted-foreground">{{ t('orgMembers.emailHint') }}</p>
            </div>

            <!-- Role Select -->
            <div class="space-y-2">
              <label class="text-sm text-muted-foreground">{{ t('orgMembers.roleLabel') }}</label>
              <CustomSelect v-model="inviteRole" :options="roleOptions" trigger-class="w-full justify-between" />
            </div>

            <!-- Actions -->
            <div class="flex justify-end gap-2 pt-2">
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
                @click="closeInviteDialog"
              >
                {{ t('common.cancel') }}
              </button>
              <button
                class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                :disabled="inviteEmails.length === 0 && !inviteEmailInput.trim() || inviteLoading"
                @click="handleInvite"
              >
                <Loader2 v-if="inviteLoading" class="w-4 h-4 animate-spin" />
                {{ t('orgMembers.sendInvite') }}
              </button>
            </div>
          </template>

          <!-- Invite Results -->
          <template v-else>
            <div class="space-y-3 max-h-[300px] overflow-y-auto">
              <div
                v-for="result in inviteResults"
                :key="result.email"
                class="flex items-center justify-between p-3 rounded-lg border border-border"
              >
                <div class="flex items-center gap-2 min-w-0">
                  <span class="text-sm truncate">{{ result.email }}</span>
                  <span
                    v-if="result.status === 'invited'"
                    class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-green-500/15 text-green-500"
                  >{{ t('orgMembers.inviteSent') }}</span>
                  <span
                    v-else-if="result.status === 'already_member'"
                    class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-yellow-500/15 text-yellow-500"
                  >{{ t('orgMembers.alreadyMember') }}</span>
                  <span
                    v-else-if="result.status === 'already_invited'"
                    class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-500/15 text-blue-400"
                  >{{ t('orgMembers.alreadyInvited') }}</span>
                </div>
                <button
                  v-if="result.invite_url"
                  class="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                  :title="t('orgMembers.copyInviteLink')"
                  @click="copyInviteUrl(result.invite_url)"
                >
                  <Check v-if="copiedUrl === result.invite_url" class="w-4 h-4 text-green-500" />
                  <Copy v-else class="w-4 h-4" />
                </button>
              </div>
            </div>
            <div class="flex justify-between items-center pt-2">
              <button
                class="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
                @click="inviteEmails = []; inviteResults = []; showInviteResults = false"
              >
                <Plus class="w-4 h-4" />
                {{ t('orgMembers.inviteMore') }}
              </button>
              <button
                class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
                @click="closeInviteDialog"
              >
                {{ t('common.close') }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </Teleport>

    <!-- Reset Password Result Dialog -->
    <Teleport to="body">
      <div
        v-if="showResetResultDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-sm p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ t('orgMembers.resetPasswordSuccess') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="showResetResultDialog = false">
              <X class="w-4 h-4" />
            </button>
          </div>

          <p class="text-sm text-muted-foreground">
            {{ t('orgMembers.resetPasswordResult', { name: resetResultName }) }}
          </p>

          <div class="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-border bg-background font-mono text-sm">
            <span class="flex-1 select-all">{{ resetResultPassword }}</span>
            <button
              class="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
              @click="copyPassword"
            >
              <Check v-if="resetCopied" class="w-4 h-4 text-green-500" />
              <Copy v-else class="w-4 h-4" />
            </button>
          </div>

          <p class="text-xs text-muted-foreground">
            {{ t('orgMembers.resetPasswordHint') }}
          </p>

          <div class="flex justify-end">
            <button
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showResetResultDialog = false"
            >
              {{ t('common.close') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
