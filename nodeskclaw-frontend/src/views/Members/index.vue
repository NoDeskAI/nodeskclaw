<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Shield, ShieldCheck, Wrench, User, Plus, Trash2 } from 'lucide-vue-next'
import { useNotify } from '@/components/ui/notify'
import api from '@/services/api'

const { t } = useI18n()
const notify = useNotify()

interface AdminMember {
  id: string
  user_id: string
  org_id: string
  role: string
  user_name: string | null
  user_email: string | null
  user_avatar_url: string | null
  created_at: string
}

const members = ref<AdminMember[]>([])
const loading = ref(false)

const showAddDialog = ref(false)
const addForm = ref({ user_id: '', role: 'member' })
const addLoading = ref(false)

const searchResults = ref<{ id: string; name: string; email: string | null }[]>([])
const searchQuery = ref('')
const searching = ref(false)

async function fetchMembers() {
  loading.value = true
  try {
    const res = await api.get('/members')
    members.value = res.data.data ?? []
  } finally {
    loading.value = false
  }
}

async function searchUsers() {
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    return
  }
  searching.value = true
  try {
    const res = await api.get('/auth/users', { params: { q: searchQuery.value.trim() } })
    const existing = new Set(members.value.map(m => m.user_id))
    searchResults.value = (res.data.data ?? []).filter((u: any) => !existing.has(u.id))
  } finally {
    searching.value = false
  }
}

function selectUser(u: { id: string; name: string }) {
  addForm.value.user_id = u.id
  searchQuery.value = u.name
  searchResults.value = []
}

async function handleAdd() {
  if (!addForm.value.user_id) return
  addLoading.value = true
  try {
    await api.post('/members', addForm.value)
    notify.success(t('members.added'))
    showAddDialog.value = false
    addForm.value = { user_id: '', role: 'member' }
    searchQuery.value = ''
    await fetchMembers()
  } catch (e: any) {
    const msg = e?.response?.data?.detail?.message || t('members.add_failed')
    notify.error(msg)
  } finally {
    addLoading.value = false
  }
}

async function handleRoleChange(memberId: string, newRole: string) {
  try {
    await api.put(`/members/${memberId}`, { role: newRole })
    const idx = members.value.findIndex(m => m.id === memberId)
    if (idx >= 0) members.value[idx].role = newRole
    notify.success(t('members.role_updated'))
  } catch (e: any) {
    const msg = e?.response?.data?.detail?.message || t('members.role_update_failed')
    notify.error(msg)
  }
}

async function handleRemove(memberId: string) {
  try {
    await api.delete(`/members/${memberId}`)
    members.value = members.value.filter(m => m.id !== memberId)
    notify.success(t('members.removed'))
  } catch (e: any) {
    const msg = e?.response?.data?.detail?.message || t('members.remove_failed')
    notify.error(msg)
  }
}

const roleOptions = [
  { value: 'member', labelKey: 'members.role_member' },
  { value: 'operator', labelKey: 'members.role_operator' },
  { value: 'admin', labelKey: 'members.role_admin' },
]

function roleIcon(role: string) {
  switch (role) {
    case 'admin': return ShieldCheck
    case 'operator': return Wrench
    default: return Shield
  }
}

function roleBadgeVariant(role: string): 'default' | 'secondary' | 'outline' {
  switch (role) {
    case 'admin': return 'default'
    case 'operator': return 'secondary'
    default: return 'outline'
  }
}

onMounted(fetchMembers)
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">{{ t('members.title') }}</h1>
        <p class="text-sm text-muted-foreground mt-1">{{ t('members.description') }}</p>
      </div>
      <Button size="sm" @click="showAddDialog = true">
        <Plus class="w-4 h-4 mr-1" />
        {{ t('members.add') }}
      </Button>
    </div>

    <div class="border rounded-lg divide-y divide-border">
      <div
        v-for="member in members"
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
          <button
            class="p-1 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
            @click="handleRemove(member.id)"
          >
            <Trash2 class="w-4 h-4" />
          </button>
        </div>
      </div>
      <div v-if="!loading && members.length === 0" class="px-4 py-8 text-center text-sm text-muted-foreground">
        {{ t('members.empty') }}
      </div>
      <div v-if="loading" class="px-4 py-8 text-center text-sm text-muted-foreground">
        {{ t('members.loading') }}
      </div>
    </div>

    <Dialog v-model:open="showAddDialog">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{{ t('members.add_title') }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-4">
          <div class="relative">
            <Input
              v-model="searchQuery"
              :placeholder="t('members.search_user_placeholder')"
              @input="searchUsers"
            />
            <div
              v-if="searchResults.length > 0"
              class="absolute z-10 mt-1 w-full bg-popover border rounded-md shadow-md max-h-48 overflow-y-auto"
            >
              <div
                v-for="u in searchResults"
                :key="u.id"
                class="px-3 py-2 text-sm hover:bg-accent cursor-pointer"
                @click="selectUser(u)"
              >
                {{ u.name }} <span class="text-muted-foreground">{{ u.email || '' }}</span>
              </div>
            </div>
          </div>
          <Select v-model="addForm.role">
            <SelectTrigger class="w-full">
              <SelectValue :placeholder="t('members.select_role')" />
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
        <DialogFooter>
          <Button variant="outline" @click="showAddDialog = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="!addForm.user_id || addLoading" @click="handleAdd">{{ t('common.confirm') }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
