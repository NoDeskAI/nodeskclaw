<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Building2, Plus, Trash2, Pencil, Users, Database, Key } from 'lucide-vue-next'
import { useOrgStore, type OrgInfo } from '@/stores/org'
import { useNotify } from '@/components/ui/notify'
import { useRouter } from 'vue-router'

const orgStore = useOrgStore()
const notify = useNotify()
const router = useRouter()

const showCreate = ref(false)
const showEdit = ref(false)
const editingOrg = ref<OrgInfo | null>(null)

const createForm = ref({ name: '', slug: '', plan: 'free' })
const editForm = ref({ name: '', plan: '', max_instances: 0, max_storage_total: '', cluster_id: '' })

onMounted(() => {
  orgStore.fetchAllOrgs()
})

async function handleCreate() {
  try {
    await orgStore.createOrg(createForm.value)
    notify.success('组织创建成功')
    showCreate.value = false
    createForm.value = { name: '', slug: '', plan: 'free' }
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '创建失败')
  }
}

function openEdit(org: OrgInfo) {
  editingOrg.value = org
  editForm.value = {
    name: org.name,
    plan: org.plan,
    max_instances: org.max_instances,
    max_storage_total: org.max_storage_total || '500Gi',
    cluster_id: org.cluster_id || '',
  }
  showEdit.value = true
}

async function handleUpdate() {
  if (!editingOrg.value) return
  try {
    const data: Record<string, unknown> = {}
    if (editForm.value.name !== editingOrg.value.name) data.name = editForm.value.name
    if (editForm.value.plan !== editingOrg.value.plan) data.plan = editForm.value.plan
    if (editForm.value.max_instances !== editingOrg.value.max_instances)
      data.max_instances = editForm.value.max_instances
    if (editForm.value.max_storage_total !== (editingOrg.value.max_storage_total || '500Gi'))
      data.max_storage_total = editForm.value.max_storage_total
    if (editForm.value.cluster_id !== (editingOrg.value.cluster_id || ''))
      data.cluster_id = editForm.value.cluster_id || null

    await orgStore.updateOrg(editingOrg.value.id, data)
    notify.success('组织更新成功')
    showEdit.value = false
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '更新失败')
  }
}

async function handleDelete(org: OrgInfo) {
  if (!confirm(`确定删除组织「${org.name}」？`)) return
  try {
    await orgStore.deleteOrg(org.id)
    notify.success('组织已删除')
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '删除失败')
  }
}

const planColors: Record<string, string> = {
  free: 'bg-zinc-500/10 text-zinc-400',
  pro: 'bg-blue-500/10 text-blue-400',
  enterprise: 'bg-amber-500/10 text-amber-400',
}

const planLabels: Record<string, string> = {
  free: '免费版',
  pro: '专业版',
  enterprise: '企业版',
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-xl font-bold">组织管理</h1>
        <p class="text-sm text-muted-foreground mt-1">管理平台上的所有组织和租户</p>
      </div>
      <Button size="sm" @click="showCreate = true">
        <Plus class="w-4 h-4 mr-1" />
        创建组织
      </Button>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <Card
        v-for="org in orgStore.orgs"
        :key="org.id"
        class="hover:border-primary/30 transition-colors"
      >
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-2">
              <Building2 class="w-4 h-4 text-primary" />
              <CardTitle class="text-base">{{ org.name }}</CardTitle>
            </div>
            <Badge :class="planColors[org.plan] || 'bg-zinc-500/10 text-zinc-400'" variant="secondary">
              {{ planLabels[org.plan] || org.plan }}
            </Badge>
          </div>
          <p class="text-xs text-muted-foreground"><span class="opacity-60">标识符:</span> <span class="font-mono">{{ org.slug }}</span></p>
        </CardHeader>
        <CardContent class="space-y-3">
          <div class="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span class="text-muted-foreground">成员</span>
              <span class="ml-1 font-medium">{{ org.member_count ?? 0 }} 人</span>
            </div>
            <div>
              <span class="text-muted-foreground">实例上限</span>
              <span class="ml-1 font-medium">{{ org.max_instances }}</span>
            </div>
            <div>
              <span class="text-muted-foreground">CPU 上限</span>
              <span class="ml-1 font-medium">{{ org.max_cpu_total }}</span>
            </div>
            <div>
              <span class="text-muted-foreground">内存上限</span>
              <span class="ml-1 font-medium">{{ org.max_mem_total }}</span>
            </div>
            <div class="col-span-2">
              <span class="text-muted-foreground">存储上限</span>
              <span class="ml-1 font-medium">{{ org.max_storage_total }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2 pt-2 border-t border-border">
            <Button variant="ghost" size="sm" class="h-7 text-xs" @click="openEdit(org)">
              <Pencil class="w-3 h-3 mr-1" />
              编辑
            </Button>
            <Button
              variant="ghost"
              size="sm"
              class="h-7 text-xs"
              @click="router.push(`/platform/orgs/${org.id}/members`)"
            >
              <Users class="w-3 h-3 mr-1" />
              成员
            </Button>
            <Button
              variant="ghost"
              size="sm"
              class="h-7 text-xs"
              @click="router.push(`/platform/orgs/${org.id}/llm-keys`)"
            >
              <Key class="w-3 h-3 mr-1" />
              LLM Key
            </Button>
            <Button
              variant="ghost"
              size="sm"
              class="h-7 text-xs text-red-400 hover:text-red-300"
              @click="handleDelete(org)"
            >
              <Trash2 class="w-3 h-3 mr-1" />
              删除
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- 创建组织 -->
    <Dialog v-model:open="showCreate">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>创建组织</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <div class="space-y-2">
            <label class="text-sm font-medium">名称</label>
            <Input v-model="createForm.name" placeholder="e.g. 我的团队" />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">标识符（小写字母/数字/短横线，创建后不可更改）</label>
            <Input v-model="createForm.slug" placeholder="如 my-team" />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">套餐</label>
            <Select v-model="createForm.plan">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="free">免费版</SelectItem>
                <SelectItem value="pro">专业版</SelectItem>
                <SelectItem value="enterprise">企业版</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="showCreate = false">取消</Button>
          <Button @click="handleCreate">创建</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 编辑组织 -->
    <Dialog v-model:open="showEdit">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑组织</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <div class="space-y-2">
            <label class="text-sm font-medium">名称</label>
            <Input v-model="editForm.name" />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">套餐</label>
            <Select v-model="editForm.plan">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="free">免费版</SelectItem>
                <SelectItem value="pro">专业版</SelectItem>
                <SelectItem value="enterprise">企业版</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">实例上限</label>
            <Input v-model.number="editForm.max_instances" type="number" />
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium">存储上限</label>
            <Input v-model="editForm.max_storage_total" placeholder="如 500Gi" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="showEdit = false">取消</Button>
          <Button @click="handleUpdate">保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
