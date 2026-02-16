<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ArrowLeft, Plus, Trash2, Shield, User, Search, Loader2 } from 'lucide-vue-next'
import { useOrgStore } from '@/stores/org'
import { useNotify } from '@/components/ui/notify'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const orgStore = useOrgStore()
const notify = useNotify()

const orgId = computed(() => route.params.orgId as string)
const org = computed(() => orgStore.orgs.find(o => o.id === orgId.value))

const showAdd = ref(false)
const addRole = ref('member')

// 用户搜索
const searchQuery = ref('')
const searchResults = ref<Array<{ id: string; name: string; email: string | null; avatar_url: string | null }>>([])
const searching = ref(false)
const selectedUser = ref<{ id: string; name: string; email: string | null } | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | null = null

function handleSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  selectedUser.value = null
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    return
  }
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      const res = await api.get('/auth/users', { params: { q: searchQuery.value.trim() } })
      searchResults.value = (res.data.data ?? []).slice(0, 10)
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function selectUser(user: { id: string; name: string; email: string | null }) {
  selectedUser.value = user
  searchQuery.value = user.name + (user.email ? ` (${user.email})` : '')
  searchResults.value = []
}

onMounted(async () => {
  if (orgStore.orgs.length === 0) await orgStore.fetchAllOrgs()
  await orgStore.fetchMembers(orgId.value)
})

async function handleAdd() {
  if (!selectedUser.value) {
    notify.error('请先搜索并选择一个用户')
    return
  }
  try {
    await orgStore.addMember(orgId.value, selectedUser.value.id, addRole.value)
    notify.success('成员已添加')
    showAdd.value = false
    searchQuery.value = ''
    selectedUser.value = null
    addRole.value = 'member'
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '添加失败')
  }
}

async function handleRoleChange(membershipId: string, role: string) {
  try {
    await orgStore.updateMemberRole(orgId.value, membershipId, role)
    notify.success('角色已更新')
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '更新失败')
  }
}

async function handleRemove(membershipId: string) {
  if (!confirm('确定移除该成员？')) return
  try {
    await orgStore.removeMember(orgId.value, membershipId)
    notify.success('成员已移除')
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '移除失败')
  }
}

function openAddDialog() {
  showAdd.value = true
  searchQuery.value = ''
  selectedUser.value = null
  searchResults.value = []
  addRole.value = 'member'
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center gap-4">
      <Button variant="ghost" size="sm" @click="router.push('/platform/orgs')">
        <ArrowLeft class="w-4 h-4" />
      </Button>
      <div>
        <h1 class="text-xl font-bold">{{ org?.name || '...' }} - 成员管理</h1>
        <p class="text-sm text-muted-foreground mt-0.5">管理组织成员及其角色</p>
      </div>
      <div class="ml-auto">
        <Button size="sm" @click="openAddDialog">
          <Plus class="w-4 h-4 mr-1" />
          添加成员
        </Button>
      </div>
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
          <Select
            :model-value="member.role"
            @update:model-value="(v: string) => handleRoleChange(member.id, v)"
          >
            <SelectTrigger class="h-7 w-28 text-xs">
              <Shield v-if="member.role === 'admin'" class="w-3 h-3 mr-1 text-amber-400" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="admin">管理员</SelectItem>
              <SelectItem value="member">成员</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="sm"
            class="h-7 text-red-400 hover:text-red-300"
            @click="handleRemove(member.id)"
          >
            <Trash2 class="w-3 h-3" />
          </Button>
        </div>
      </div>
      <div v-if="orgStore.members.length === 0" class="px-4 py-8 text-center text-sm text-muted-foreground">
        暂无成员
      </div>
    </div>

    <!-- 添加成员 -->
    <Dialog v-model:open="showAdd">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>添加成员</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <!-- 用户搜索 -->
          <div class="space-y-2">
            <label class="text-sm font-medium">搜索用户</label>
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                v-model="searchQuery"
                placeholder="输入名称、邮箱或手机号搜索"
                class="pl-9"
                @input="handleSearchInput"
              />
              <Loader2 v-if="searching" class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-muted-foreground" />
            </div>
            <!-- 搜索结果下拉 -->
            <div
              v-if="searchResults.length > 0 && !selectedUser"
              class="border rounded-lg divide-y divide-border max-h-48 overflow-y-auto"
            >
              <button
                v-for="u in searchResults"
                :key="u.id"
                class="w-full flex items-center gap-3 px-3 py-2 hover:bg-accent transition-colors text-left"
                @click="selectUser(u)"
              >
                <div class="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <img v-if="u.avatar_url" :src="u.avatar_url" class="w-7 h-7 rounded-full" />
                  <User v-else class="w-3.5 h-3.5 text-primary" />
                </div>
                <div class="min-w-0">
                  <div class="text-sm font-medium truncate">{{ u.name }}</div>
                  <div class="text-xs text-muted-foreground truncate">{{ u.email || '-' }}</div>
                </div>
              </button>
            </div>
            <!-- 选中用户提示 -->
            <div v-if="selectedUser" class="flex items-center gap-2 text-sm text-green-400">
              <User class="w-3.5 h-3.5" />
              已选择: {{ selectedUser.name }}
            </div>
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">角色</label>
            <Select v-model="addRole">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">管理员</SelectItem>
                <SelectItem value="member">成员</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="showAdd = false">取消</Button>
          <Button :disabled="!selectedUser" @click="handleAdd">添加</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
