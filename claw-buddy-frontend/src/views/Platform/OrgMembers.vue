<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
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
import { ArrowLeft, Plus, Trash2, Shield, User } from 'lucide-vue-next'
import { useOrgStore } from '@/stores/org'
import { useNotify } from '@/components/ui/notify'

const route = useRoute()
const router = useRouter()
const orgStore = useOrgStore()
const notify = useNotify()

const orgId = computed(() => route.params.orgId as string)
const org = computed(() => orgStore.orgs.find(o => o.id === orgId.value))

const showAdd = ref(false)
const addForm = ref({ user_id: '', role: 'member' })

onMounted(async () => {
  if (orgStore.orgs.length === 0) await orgStore.fetchAllOrgs()
  await orgStore.fetchMembers(orgId.value)
})

async function handleAdd() {
  try {
    await orgStore.addMember(orgId.value, addForm.value.user_id, addForm.value.role)
    notify.success('成员已添加')
    showAdd.value = false
    addForm.value = { user_id: '', role: 'member' }
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
        <Button size="sm" @click="showAdd = true">
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
          <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
            <User class="w-4 h-4 text-primary" />
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
          <div class="space-y-2">
            <label class="text-sm font-medium">用户 ID</label>
            <Input v-model="addForm.user_id" placeholder="输入用户 ID" />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">角色</label>
            <Select v-model="addForm.role">
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
          <Button @click="handleAdd">添加</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
