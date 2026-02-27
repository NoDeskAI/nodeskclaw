<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
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
  ChevronDown,
  X,
} from 'lucide-vue-next'
import api from '@/services/api'

const orgStore = useOrgStore()
const authStore = useAuthStore()
const { t } = useI18n()

const loading = ref(true)
const showAddDialog = ref(false)
const searchQuery = ref('')
const searchResults = ref<Array<{ id: string; name: string; email: string | null }>>([])
const searching = ref(false)
const selectedUser = ref<{ id: string; name: string; email: string | null } | null>(null)
const addRole = ref('member')
const addLoading = ref(false)
const actionLoading = ref<string | null>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null

const isOrgAdmin = computed(() => {
  const myMember = orgStore.members.find(m => m.user_id === authStore.user?.id)
  return myMember?.role === 'admin'
})

const filteredMembers = computed(() => {
  if (!searchQuery.value) return orgStore.members
  const q = searchQuery.value.toLowerCase()
  return orgStore.members.filter(
    m =>
      (m.user_name?.toLowerCase().includes(q)) ||
      (m.user_email?.toLowerCase().includes(q))
  )
})

onMounted(async () => {
  if (!orgStore.currentOrgId) {
    await orgStore.fetchMyOrg()
  }
  if (orgStore.currentOrgId) {
    await orgStore.fetchMembers()
  }
  loading.value = false
})

function debounceSearchUsers(q: string) {
  if (searchTimer) clearTimeout(searchTimer)
  if (!q || q.length < 2) {
    searchResults.value = []
    return
  }
  searching.value = true
  searchTimer = setTimeout(async () => {
    try {
      const res = await api.get('/auth/users', { params: { q } })
      searchResults.value = (res.data.data ?? []).filter(
        (u: any) => !orgStore.members.some(m => m.user_id === u.id)
      )
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function selectUser(user: { id: string; name: string; email: string | null }) {
  selectedUser.value = user
  searchResults.value = []
}

async function handleAddMember() {
  if (!selectedUser.value) return
  addLoading.value = true
  try {
    await orgStore.addMember(selectedUser.value.id, addRole.value)
    showAddDialog.value = false
    selectedUser.value = null
    addRole.value = 'member'
  } catch (e: any) {
    alert(e?.response?.data?.message || t('orgMembers.addFailed'))
  } finally {
    addLoading.value = false
  }
}

async function handleRoleChange(member: MemberInfo, newRole: string) {
  if (member.role === newRole) return
  actionLoading.value = member.id
  try {
    await orgStore.updateMemberRole(member.id, newRole)
  } catch (e: any) {
    alert(e?.response?.data?.message || t('orgMembers.updateRoleFailed'))
  } finally {
    actionLoading.value = null
  }
}

async function handleRemove(member: MemberInfo) {
  if (!confirm(t('orgMembers.removeConfirm', { name: member.user_name || member.user_email }))) return
  actionLoading.value = member.id
  try {
    await orgStore.removeMember(member.id)
  } catch (e: any) {
    alert(e?.response?.data?.message || t('orgMembers.removeFailed'))
  } finally {
    actionLoading.value = null
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-6 py-8">
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-xl font-bold">{{ t('orgMembers.title') }}</h1>
        <p class="text-sm text-muted-foreground mt-0.5">
          {{ t('orgMembers.subtitle', { orgName: orgStore.currentOrg?.name || t('orgMembers.orgFallback') }) }}
        </p>
      </div>
      <button
        v-if="isOrgAdmin"
        class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="showAddDialog = true"
      >
        <UserPlus class="w-4 h-4" />
        {{ t('orgMembers.addMember') }}
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
      <p class="text-xs text-muted-foreground mb-3">{{ t('orgMembers.memberCount', { count: filteredMembers.length }) }}</p>

      <div class="space-y-2">
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
                  v-if="member.role === 'admin'"
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

          <!-- Actions (admin only) -->
          <div v-if="isOrgAdmin && member.user_id !== authStore.user?.id" class="flex items-center gap-2">
            <div class="relative">
              <select
                :value="member.role"
                class="appearance-none bg-card border border-border rounded-md px-3 py-1.5 pr-7 text-xs focus:outline-none focus:ring-2 focus:ring-primary/30 cursor-pointer"
                :disabled="actionLoading === member.id"
                @change="(e) => handleRoleChange(member, (e.target as HTMLSelectElement).value)"
              >
                <option value="admin">{{ t('orgMembers.roleAdmin') }}</option>
                <option value="member">{{ t('orgMembers.roleMember') }}</option>
              </select>
              <ChevronDown class="w-3 h-3 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground" />
            </div>
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
      </div>

      <div v-if="filteredMembers.length === 0 && !loading" class="text-center py-12 text-muted-foreground text-sm">
        {{ t('orgMembers.noMatch') }}
      </div>
    </template>

    <!-- Add Member Dialog -->
    <Teleport to="body">
      <div
        v-if="showAddDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="showAddDialog = false"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-md p-6 space-y-4">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">{{ t('orgMembers.dialogTitle') }}</h3>
            <button class="text-muted-foreground hover:text-foreground" @click="showAddDialog = false">
              <X class="w-4 h-4" />
            </button>
          </div>

          <!-- User Search -->
          <div class="space-y-2">
            <label class="text-sm text-muted-foreground">{{ t('orgMembers.searchUserLabel') }}</label>
            <div v-if="selectedUser" class="flex items-center gap-2 p-2.5 rounded-lg border border-primary/30 bg-primary/5">
              <div class="w-7 h-7 rounded-full bg-primary/15 flex items-center justify-center text-xs font-medium text-primary">
                {{ selectedUser.name.charAt(0) }}
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium truncate">{{ selectedUser.name }}</p>
                <p class="text-xs text-muted-foreground truncate">{{ selectedUser.email || '-' }}</p>
              </div>
              <button class="text-muted-foreground hover:text-foreground" @click="selectedUser = null">
                <X class="w-3.5 h-3.5" />
              </button>
            </div>
            <div v-else class="relative">
              <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                :placeholder="t('orgMembers.searchUserPlaceholder')"
                class="w-full pl-9 pr-4 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                @input="(e) => debounceSearchUsers((e.target as HTMLInputElement).value)"
              />
              <!-- Search Results Dropdown -->
              <div
                v-if="searchResults.length > 0"
                class="absolute top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg max-h-48 overflow-y-auto z-10"
              >
                <button
                  v-for="u in searchResults"
                  :key="u.id"
                  class="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-accent text-left transition-colors"
                  @click="selectUser(u)"
                >
                  <div class="w-7 h-7 rounded-full bg-primary/15 flex items-center justify-center text-xs font-medium text-primary shrink-0">
                    {{ u.name.charAt(0) }}
                  </div>
                  <div class="min-w-0">
                    <p class="text-sm font-medium truncate">{{ u.name }}</p>
                    <p class="text-xs text-muted-foreground truncate">{{ u.email || '-' }}</p>
                  </div>
                </button>
              </div>
              <div v-if="searching" class="absolute top-full left-0 right-0 mt-1 bg-card border border-border rounded-lg shadow-lg p-4 text-center">
                <Loader2 class="w-4 h-4 animate-spin mx-auto text-muted-foreground" />
              </div>
            </div>
          </div>

          <!-- Role Select -->
          <div class="space-y-2">
            <label class="text-sm text-muted-foreground">{{ t('orgMembers.roleLabel') }}</label>
            <div class="relative">
              <select
                v-model="addRole"
                class="w-full appearance-none bg-background border border-border rounded-lg px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              >
                <option value="member">{{ t('orgMembers.roleMember') }}</option>
                <option value="admin">{{ t('orgMembers.roleAdmin') }}</option>
              </select>
              <ChevronDown class="w-4 h-4 absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground" />
            </div>
          </div>

          <!-- Actions -->
          <div class="flex justify-end gap-2 pt-2">
            <button
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showAddDialog = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
              :disabled="!selectedUser || addLoading"
              @click="handleAddMember"
            >
              <Loader2 v-if="addLoading" class="w-4 h-4 animate-spin" />
              {{ t('orgMembers.confirmAdd') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
