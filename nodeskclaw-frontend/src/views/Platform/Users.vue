<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { User, ShieldCheck, Search, Plus, Loader2, ShieldOff, Ban, CheckCircle, X } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import api from '@/services/api'
import { useNotify } from '@/components/ui/notify'
import { resolveApiErrorMessage } from '@/i18n/error'

const notify = useNotify()
const authStore = useAuthStore()

interface StaffItem {
  id: string
  name: string
  email: string | null
  avatar_url: string | null
  role: string
  is_super_admin: boolean
  is_active: boolean
  current_org_id: string | null
  last_login_at: string | null
}

const staff = ref<StaffItem[]>([])
const loading = ref(false)
const searchQuery = ref('')
const actionLoading = ref<string | null>(null)

// 添加运维人员
const showAdd = ref(false)
const addSearchQuery = ref('')
const addSearchResults = ref<StaffItem[]>([])
const addSearching = ref(false)
const selectedUser = ref<StaffItem | null>(null)
let addSearchTimer: ReturnType<typeof setTimeout> | null = null

async function fetchStaff() {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (searchQuery.value.trim()) params.q = searchQuery.value.trim()
    const res = await api.get('/auth/staff', { params })
    staff.value = res.data.data ?? []
  } catch {
    notify.error('加载运维人员列表失败')
  } finally {
    loading.value = false
  }
}

onMounted(fetchStaff)

let searchTimer: ReturnType<typeof setTimeout> | null = null
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(fetchStaff, 300)
})

function formatDate(s: string | null) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN')
}

async function toggleActive(user: StaffItem) {
  const newActive = !user.is_active
  const label = newActive ? '启用' : '禁用'
  if (!confirm(`确定${label}运维人员「${user.name}」？`)) return

  actionLoading.value = user.id
  try {
    const res = await api.put(`/auth/staff/${user.id}?is_active=${newActive}`)
    const idx = staff.value.findIndex(s => s.id === user.id)
    if (idx >= 0) staff.value[idx] = res.data.data
    notify.success(`已${label}`)
  } catch (e: any) {
    notify.error(resolveApiErrorMessage(e, `${label}失败`))
  } finally {
    actionLoading.value = null
  }
}

async function removeAdmin(user: StaffItem) {
  if (!confirm(`确定取消「${user.name}」的超管权限？该用户将不再出现在运维人员列表中。`)) return

  actionLoading.value = user.id
  try {
    await api.put(`/auth/staff/${user.id}?is_super_admin=false`)
    staff.value = staff.value.filter(s => s.id !== user.id)
    notify.success('已取消超管权限')
  } catch (e: any) {
    notify.error(resolveApiErrorMessage(e, '操作失败'))
  } finally {
    actionLoading.value = null
  }
}

// 添加运维人员搜索
function handleAddSearch() {
  if (addSearchTimer) clearTimeout(addSearchTimer)
  selectedUser.value = null
  if (!addSearchQuery.value.trim() || addSearchQuery.value.trim().length < 2) {
    addSearchResults.value = []
    return
  }
  addSearching.value = true
  addSearchTimer = setTimeout(async () => {
    try {
      const res = await api.get('/auth/users', { params: { q: addSearchQuery.value.trim() } })
      const allUsers: StaffItem[] = res.data.data ?? []
      addSearchResults.value = allUsers.filter(u => !u.is_super_admin)
    } catch {
      addSearchResults.value = []
    } finally {
      addSearching.value = false
    }
  }, 300)
}

function selectAddUser(user: StaffItem) {
  selectedUser.value = user
  addSearchResults.value = []
}

async function handleAddStaff() {
  if (!selectedUser.value) return
  actionLoading.value = 'add'
  try {
    await api.put(`/auth/staff/${selectedUser.value.id}?is_super_admin=true`)
    notify.success(`已将「${selectedUser.value.name}」设为运维人员`)
    showAdd.value = false
    selectedUser.value = null
    addSearchQuery.value = ''
    await fetchStaff()
  } catch (e: any) {
    notify.error(resolveApiErrorMessage(e, '操作失败'))
  } finally {
    actionLoading.value = null
  }
}

function openAddDialog() {
  showAdd.value = true
  addSearchQuery.value = ''
  selectedUser.value = null
  addSearchResults.value = []
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">运维人员</h1>
        <p class="text-sm text-muted-foreground mt-1">管理平台内部运维团队</p>
      </div>
      <Button size="sm" @click="openAddDialog">
        <Plus class="w-4 h-4 mr-1" />
        添加运维人员
      </Button>
    </div>

    <!-- 搜索 -->
    <div class="relative">
      <Search class="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
      <Input
        v-model="searchQuery"
        placeholder="搜索运维人员..."
        class="pl-9"
      />
    </div>

    <!-- 列表 -->
    <div class="border rounded-lg divide-y divide-border">
      <div
        v-for="u in staff"
        :key="u.id"
        class="flex items-center justify-between px-4 py-3"
      >
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden">
            <img v-if="u.avatar_url" :src="u.avatar_url" class="w-8 h-8 rounded-full" alt="" />
            <User v-else class="w-4 h-4 text-primary" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium">{{ u.name }}</span>
              <Badge variant="secondary" class="text-[10px] bg-amber-500/10 text-amber-400">
                <ShieldCheck class="w-3 h-3 mr-0.5" />
                超管
              </Badge>
              <Badge v-if="!u.is_active" variant="destructive" class="text-[10px]">
                已禁用
              </Badge>
            </div>
            <div class="text-xs text-muted-foreground">{{ u.email || '-' }}</div>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-muted-foreground hidden md:inline">
            最后登录: {{ formatDate(u.last_login_at) }}
          </span>
          <!-- 禁用/启用 -->
          <Button
            variant="ghost"
            size="sm"
            class="h-7 text-xs"
            :disabled="actionLoading === u.id"
            @click="toggleActive(u)"
          >
            <Loader2 v-if="actionLoading === u.id" class="w-3 h-3 mr-1 animate-spin" />
            <template v-else>
              <Ban v-if="u.is_active" class="w-3 h-3 mr-1" />
              <CheckCircle v-else class="w-3 h-3 mr-1" />
            </template>
            {{ u.is_active ? '禁用' : '启用' }}
          </Button>
          <!-- 取消超管（不能对自己操作） -->
          <Button
            v-if="u.id !== authStore.user?.id"
            variant="ghost"
            size="sm"
            class="h-7 text-xs text-red-400 hover:text-red-300"
            :disabled="actionLoading === u.id"
            @click="removeAdmin(u)"
          >
            <ShieldOff class="w-3 h-3 mr-1" />
            取消超管
          </Button>
        </div>
      </div>
      <div v-if="staff.length === 0 && !loading" class="px-4 py-8 text-center text-sm text-muted-foreground">
        暂无运维人员
      </div>
      <div v-if="loading" class="px-4 py-8 flex items-center justify-center">
        <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
      </div>
    </div>

    <!-- 添加运维人员 -->
    <Dialog v-model:open="showAdd">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>添加运维人员</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <p class="text-sm text-muted-foreground">搜索平台用户，将其设为超管</p>

          <!-- 已选中 -->
          <div v-if="selectedUser" class="flex items-center gap-2 p-2.5 rounded-lg border border-primary/30 bg-primary/5">
            <div class="w-7 h-7 rounded-full bg-primary/15 flex items-center justify-center overflow-hidden shrink-0">
              <img v-if="selectedUser.avatar_url" :src="selectedUser.avatar_url" class="w-7 h-7 rounded-full" alt="" />
              <User v-else class="w-3.5 h-3.5 text-primary" />
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium truncate">{{ selectedUser.name }}</p>
              <p class="text-xs text-muted-foreground truncate">{{ selectedUser.email || '-' }}</p>
            </div>
            <button class="text-muted-foreground hover:text-foreground shrink-0" @click="selectedUser = null">
              <X class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- 搜索 -->
          <div v-else class="relative">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              v-model="addSearchQuery"
              placeholder="输入名称或邮箱搜索用户"
              class="pl-9"
              @input="handleAddSearch"
            />
            <Loader2 v-if="addSearching" class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 animate-spin text-muted-foreground" />

            <!-- 搜索结果 -->
            <div
              v-if="addSearchResults.length > 0"
              class="border rounded-lg divide-y divide-border max-h-48 overflow-y-auto mt-2"
            >
              <button
                v-for="u in addSearchResults"
                :key="u.id"
                class="w-full flex items-center gap-3 px-3 py-2 hover:bg-accent transition-colors text-left"
                @click="selectAddUser(u)"
              >
                <div class="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center overflow-hidden shrink-0">
                  <img v-if="u.avatar_url" :src="u.avatar_url" class="w-7 h-7 rounded-full" alt="" />
                  <User v-else class="w-3.5 h-3.5 text-primary" />
                </div>
                <div class="min-w-0">
                  <div class="text-sm font-medium truncate">{{ u.name }}</div>
                  <div class="text-xs text-muted-foreground truncate">{{ u.email || '-' }}</div>
                </div>
              </button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="showAdd = false">取消</Button>
          <Button :disabled="!selectedUser || actionLoading === 'add'" @click="handleAddStaff">
            <Loader2 v-if="actionLoading === 'add'" class="w-4 h-4 mr-1 animate-spin" />
            设为超管
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
