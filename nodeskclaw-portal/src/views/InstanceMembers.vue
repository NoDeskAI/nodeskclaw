<script setup lang="ts">
import { ref, inject, computed, watch, onMounted } from 'vue'
import type { Ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { UserPlus, Loader2, Trash2, Search } from 'lucide-vue-next'
import api from '@/services/api'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import CustomSelect from '@/components/shared/CustomSelect.vue'

const { t } = useI18n()
const toast = useToast()
const { confirm } = useConfirm()

const instanceId = inject<Ref<string>>('instanceId')!
const myRole = inject<Ref<string | null>>('myInstanceRole', ref(null))

const isAdmin = computed(() => myRole.value === 'admin')

interface MemberInfo {
  id: string
  instance_id: string
  user_id: string
  role: string
  user_name: string | null
  user_email: string | null
  user_avatar_url: string | null
  created_at: string
}

interface SearchUser {
  user_id: string
  name: string | null
  email: string | null
  avatar_url: string | null
}

const members = ref<MemberInfo[]>([])
const loading = ref(true)
const error = ref('')

const showAddDialog = ref(false)
const searchQuery = ref('')
const searchResults = ref<SearchUser[]>([])
const searching = ref(false)
const addRole = ref('viewer')
const addingUserId = ref<string | null>(null)

const roleKeys = ['admin', 'editor', 'user', 'viewer']

function roleLabel(role: string): string {
  const map: Record<string, string> = {
    admin: t('instanceMembers.roleAdmin'),
    editor: t('instanceMembers.roleEditor'),
    user: t('instanceMembers.roleUser'),
    viewer: t('instanceMembers.roleViewer'),
  }
  return map[role] ?? role
}

const roleOptions = computed(() =>
  roleKeys.map(r => ({ value: r, label: roleLabel(r) }))
)

async function fetchMembers() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.get(`/instances/${instanceId.value}/members`)
    members.value = res.data.data ?? []
  } catch (e) {
    error.value = resolveApiErrorMessage(e, t('instanceMembers.loadFailed'))
  } finally {
    loading.value = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(doSearch, 300)
}

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    searchResults.value = []
    return
  }
  searching.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}/members/search-users`, { params: { q } })
    searchResults.value = res.data.data ?? []
  } catch {
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

async function addMember(userId: string) {
  addingUserId.value = userId
  try {
    await api.post(`/instances/${instanceId.value}/members`, {
      user_id: userId,
      role: addRole.value,
    })
    toast.success(t('instanceMembers.addSuccess'))
    showAddDialog.value = false
    searchQuery.value = ''
    searchResults.value = []
    addRole.value = 'viewer'
    await fetchMembers()
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('instanceMembers.addFailed')))
  } finally {
    addingUserId.value = null
  }
}

async function updateRole(member: MemberInfo, newRole: string) {
  if (newRole === member.role) return
  try {
    await api.put(`/instances/${instanceId.value}/members/${member.id}`, { role: newRole })
    member.role = newRole
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('instanceMembers.updateFailed')))
  }
}

async function removeMember(member: MemberInfo) {
  const name = member.user_name || member.user_email || member.user_id
  const ok = await confirm({
    title: t('instanceMembers.removeMemberTitle'),
    description: t('instanceMembers.removeConfirm', { name }),
    variant: 'danger',
  })
  if (!ok) return
  try {
    await api.delete(`/instances/${instanceId.value}/members/${member.id}`)
    toast.success(t('instanceMembers.removeSuccess'))
    await fetchMembers()
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('instanceMembers.removeFailed')))
  }
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleDateString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
  })
}

onMounted(fetchMembers)
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold">{{ t('instanceMembers.title') }}</h2>
        <p class="text-sm text-muted-foreground mt-0.5">{{ t('instanceMembers.subtitle') }}</p>
      </div>
      <button
        v-if="isAdmin"
        class="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
        @click="showAddDialog = true"
      >
        <UserPlus class="w-4 h-4" />
        {{ t('instanceMembers.addMember') }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex justify-center py-12">
      <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-center py-12">
      <p class="text-sm text-red-400">{{ error }}</p>
    </div>

    <!-- Members table -->
    <div v-else class="rounded-xl border border-border overflow-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border bg-card/60">
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceMembers.colUser') }}</th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceMembers.colRole') }}</th>
            <th class="text-left px-4 py-3 font-medium text-muted-foreground">{{ t('instanceMembers.colJoined') }}</th>
            <th v-if="isAdmin" class="text-right px-4 py-3 font-medium text-muted-foreground">{{ t('instanceMembers.colActions') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="m in members"
            :key="m.id"
            class="border-b border-border last:border-b-0"
          >
            <td class="px-4 py-3">
              <div class="flex items-center gap-3">
                <div class="w-8 h-8 rounded-full bg-muted flex items-center justify-center text-xs font-medium shrink-0">
                  <img v-if="m.user_avatar_url" :src="m.user_avatar_url" class="w-8 h-8 rounded-full object-cover" />
                  <span v-else>{{ (m.user_name || m.user_email || '?')[0].toUpperCase() }}</span>
                </div>
                <div class="min-w-0">
                  <div class="font-medium truncate">{{ m.user_name || t('instanceMembers.unknownUser') }}</div>
                  <div class="text-xs text-muted-foreground truncate">{{ m.user_email }}</div>
                </div>
              </div>
            </td>
            <td class="px-4 py-3">
              <CustomSelect
                v-if="isAdmin"
                :model-value="m.role"
                :options="roleOptions"
                @update:model-value="(v: string | null) => updateRole(m, v!)"
              />
              <span v-else class="text-sm">{{ roleLabel(m.role) }}</span>
            </td>
            <td class="px-4 py-3 text-muted-foreground">{{ formatTime(m.created_at) }}</td>
            <td v-if="isAdmin" class="px-4 py-3 text-right">
              <button
                class="p-1.5 rounded-lg text-muted-foreground hover:text-red-400 hover:bg-red-400/10 transition-colors"
                @click="removeMember(m)"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Add member dialog -->
    <Teleport to="body">
      <div
        v-if="showAddDialog"
        class="fixed inset-0 z-50 flex items-center justify-center"
      >
        <div class="absolute inset-0 bg-black/50" @click="showAddDialog = false" />
        <div class="relative bg-card border border-border rounded-2xl shadow-xl w-full max-w-md p-6 space-y-4">
          <h3 class="text-lg font-semibold">{{ t('instanceMembers.addMember') }}</h3>

          <!-- Search -->
          <div class="relative">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              v-model="searchQuery"
              type="text"
              class="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
              :placeholder="t('instanceMembers.searchPlaceholder')"
              @input="onSearchInput"
            />
          </div>

          <!-- Role selector -->
          <div class="flex items-center gap-2">
            <span class="text-sm text-muted-foreground">{{ t('instanceMembers.roleLabel') }}:</span>
            <CustomSelect v-model="addRole" :options="roleOptions" />
          </div>

          <!-- Search results -->
          <div class="max-h-60 overflow-y-auto space-y-1">
            <div v-if="searching" class="flex justify-center py-4">
              <Loader2 class="w-4 h-4 animate-spin text-muted-foreground" />
            </div>
            <template v-else-if="searchResults.length > 0">
              <div
                v-for="u in searchResults"
                :key="u.user_id"
                class="flex items-center justify-between px-3 py-2 rounded-lg hover:bg-accent/50 transition-colors"
              >
                <div class="flex items-center gap-3 min-w-0">
                  <div class="w-7 h-7 rounded-full bg-muted flex items-center justify-center text-xs font-medium shrink-0">
                    <img v-if="u.avatar_url" :src="u.avatar_url" class="w-7 h-7 rounded-full object-cover" />
                    <span v-else>{{ (u.name || u.email || '?')[0].toUpperCase() }}</span>
                  </div>
                  <div class="min-w-0">
                    <div class="text-sm font-medium truncate">{{ u.name || t('instanceMembers.unknownUser') }}</div>
                    <div class="text-xs text-muted-foreground truncate">{{ u.email }}</div>
                  </div>
                </div>
                <button
                  class="shrink-0 px-3 py-1 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                  :disabled="addingUserId === u.user_id"
                  @click="addMember(u.user_id)"
                >
                  <Loader2 v-if="addingUserId === u.user_id" class="w-3 h-3 animate-spin" />
                  <span v-else>{{ t('instanceMembers.add') }}</span>
                </button>
              </div>
            </template>
            <div v-else-if="searchQuery.trim()" class="text-center py-4 text-sm text-muted-foreground">
              {{ t('instanceMembers.noSearchResults') }}
            </div>
          </div>

          <!-- Close -->
          <div class="flex justify-end">
            <button
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
              @click="showAddDialog = false"
            >
              {{ t('instanceMembers.close') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
