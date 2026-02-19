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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ArrowLeft, Plus, Pencil, Trash2, Key } from 'lucide-vue-next'
import { useNotify } from '@/components/ui/notify'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const notify = useNotify()

const orgId = computed(() => route.params.orgId as string)

interface OrgLlmKey {
  id: string
  org_id: string
  provider: string
  label: string
  api_key_masked: string
  base_url: string | null
  org_token_limit: number | null
  system_token_limit: number | null
  is_active: boolean
  usage_total_tokens: number
  created_by: string
}

const keys = ref<OrgLlmKey[]>([])
const loading = ref(true)

const PROVIDERS = ['openai', 'anthropic', 'gemini', 'openrouter']
const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  openrouter: 'OpenRouter',
}

const showCreate = ref(false)
const showEdit = ref(false)
const editingKey = ref<OrgLlmKey | null>(null)
const saving = ref(false)

const createForm = ref({
  provider: '',
  label: '',
  api_key: '',
  base_url: '',
  org_token_limit: '',
  system_token_limit: '',
})

const editForm = ref({
  label: '',
  api_key: '',
  base_url: '',
  org_token_limit: '',
  system_token_limit: '',
  is_active: true,
})

async function fetchKeys() {
  loading.value = true
  try {
    const res = await api.get(`/orgs/${orgId.value}/llm-keys`)
    keys.value = res.data.data ?? []
  } catch {
    notify.error('加载 Key 列表失败')
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  saving.value = true
  try {
    await api.post(`/orgs/${orgId.value}/llm-keys`, {
      provider: createForm.value.provider,
      label: createForm.value.label,
      api_key: createForm.value.api_key,
      base_url: createForm.value.base_url || undefined,
      org_token_limit: createForm.value.org_token_limit ? Number(createForm.value.org_token_limit) : undefined,
      system_token_limit: createForm.value.system_token_limit ? Number(createForm.value.system_token_limit) : undefined,
    })
    notify.success('Key 创建成功')
    showCreate.value = false
    createForm.value = { provider: '', label: '', api_key: '', base_url: '', org_token_limit: '', system_token_limit: '' }
    await fetchKeys()
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '创建失败')
  } finally {
    saving.value = false
  }
}

function openEdit(key: OrgLlmKey) {
  editingKey.value = key
  editForm.value = {
    label: key.label,
    api_key: '',
    base_url: key.base_url || '',
    org_token_limit: key.org_token_limit?.toString() ?? '',
    system_token_limit: key.system_token_limit?.toString() ?? '',
    is_active: key.is_active,
  }
  showEdit.value = true
}

async function handleEdit() {
  if (!editingKey.value) return
  saving.value = true
  try {
    const payload: Record<string, any> = { label: editForm.value.label, is_active: editForm.value.is_active }
    if (editForm.value.api_key) payload.api_key = editForm.value.api_key
    if (editForm.value.base_url !== (editingKey.value.base_url || '')) payload.base_url = editForm.value.base_url || null
    payload.org_token_limit = editForm.value.org_token_limit ? Number(editForm.value.org_token_limit) : null
    payload.system_token_limit = editForm.value.system_token_limit ? Number(editForm.value.system_token_limit) : null

    await api.patch(`/orgs/${orgId.value}/llm-keys/${editingKey.value.id}`, payload)
    notify.success('Key 更新成功')
    showEdit.value = false
    editingKey.value = null
    await fetchKeys()
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '更新失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(key: OrgLlmKey) {
  if (!confirm(`确定删除 Key「${key.label}」？已使用此 Key 的用户将无法继续调用对应 Provider。`)) return
  try {
    await api.delete(`/orgs/${orgId.value}/llm-keys/${key.id}`)
    notify.success('Key 已删除')
    await fetchKeys()
  } catch (e: any) {
    notify.error(e?.response?.data?.message || '删除失败')
  }
}

function formatTokens(n: number | null): string {
  if (n == null) return '不限'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toString()
}

function usagePercent(used: number, limit: number | null): number {
  if (!limit || limit === 0) return 0
  return Math.min(100, (used / limit) * 100)
}

onMounted(fetchKeys)
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <Button variant="ghost" size="icon" @click="router.push('/platform/orgs')">
          <ArrowLeft class="w-4 h-4" />
        </Button>
        <div>
          <h1 class="text-lg font-semibold flex items-center gap-2">
            <Key class="w-5 h-5" />
            组织 LLM Key 管理
          </h1>
          <p class="text-sm text-muted-foreground">管理该组织的大模型 API Key 和额度</p>
        </div>
      </div>
      <Button @click="showCreate = true">
        <Plus class="w-4 h-4 mr-1" />
        新增 Key
      </Button>
    </div>

    <!-- Key List -->
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Provider</TableHead>
          <TableHead>标签</TableHead>
          <TableHead>Key</TableHead>
          <TableHead>用量 / 组织额度</TableHead>
          <TableHead>系统额度</TableHead>
          <TableHead>状态</TableHead>
          <TableHead class="w-24">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow v-if="loading">
          <TableCell colspan="7" class="text-center text-muted-foreground py-8">加载中...</TableCell>
        </TableRow>
        <TableRow v-else-if="keys.length === 0">
          <TableCell colspan="7" class="text-center text-muted-foreground py-8">暂无 Key，点击右上角新增</TableCell>
        </TableRow>
        <TableRow v-for="key in keys" :key="key.id">
          <TableCell>
            <Badge variant="outline">{{ PROVIDER_LABELS[key.provider] || key.provider }}</Badge>
          </TableCell>
          <TableCell class="font-medium">{{ key.label }}</TableCell>
          <TableCell class="font-mono text-xs">{{ key.api_key_masked }}</TableCell>
          <TableCell>
            <div class="space-y-1">
              <div class="text-xs">
                {{ formatTokens(key.usage_total_tokens) }} / {{ formatTokens(key.org_token_limit) }}
              </div>
              <div class="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all"
                  :class="usagePercent(key.usage_total_tokens, key.org_token_limit) > 90 ? 'bg-destructive' : 'bg-primary'"
                  :style="{ width: usagePercent(key.usage_total_tokens, key.org_token_limit) + '%' }"
                />
              </div>
            </div>
          </TableCell>
          <TableCell class="text-xs">{{ formatTokens(key.system_token_limit) }}</TableCell>
          <TableCell>
            <Badge :variant="key.is_active ? 'default' : 'secondary'">
              {{ key.is_active ? '启用' : '禁用' }}
            </Badge>
          </TableCell>
          <TableCell>
            <div class="flex items-center gap-1">
              <Button variant="ghost" size="icon" class="h-7 w-7" @click="openEdit(key)">
                <Pencil class="w-3.5 h-3.5" />
              </Button>
              <Button variant="ghost" size="icon" class="h-7 w-7 text-destructive" @click="handleDelete(key)">
                <Trash2 class="w-3.5 h-3.5" />
              </Button>
            </div>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <!-- Create Dialog -->
    <Dialog :open="showCreate" @update:open="showCreate = $event">
      <DialogContent class="max-w-md">
        <DialogHeader>
          <DialogTitle>新增 LLM Key</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="space-y-1.5">
            <label class="text-sm font-medium">Provider</label>
            <Select v-model="createForm.provider">
              <SelectTrigger><SelectValue placeholder="选择 Provider" /></SelectTrigger>
              <SelectContent>
                <SelectItem v-for="p in PROVIDERS" :key="p" :value="p">{{ PROVIDER_LABELS[p] || p }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">标签</label>
            <Input v-model="createForm.label" placeholder="例如：市场部 OpenAI 主号" />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">API Key</label>
            <Input v-model="createForm.api_key" type="password" placeholder="sk-..." />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">Base URL（可选）</label>
            <Input v-model="createForm.base_url" placeholder="留空使用默认地址" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <label class="text-sm font-medium">组织额度（token 数）</label>
              <Input v-model="createForm.org_token_limit" type="number" placeholder="留空不限" />
            </div>
            <div class="space-y-1.5">
              <label class="text-sm font-medium">系统额度（token 数）</label>
              <Input v-model="createForm.system_token_limit" type="number" placeholder="留空不限" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showCreate = false">取消</Button>
          <Button :disabled="!createForm.provider || !createForm.label || !createForm.api_key || saving" @click="handleCreate">
            {{ saving ? '创建中...' : '创建' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Edit Dialog -->
    <Dialog :open="showEdit" @update:open="showEdit = $event">
      <DialogContent class="max-w-md">
        <DialogHeader>
          <DialogTitle>编辑 Key: {{ editingKey?.label }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="space-y-1.5">
            <label class="text-sm font-medium">标签</label>
            <Input v-model="editForm.label" />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">API Key（留空不修改）</label>
            <Input v-model="editForm.api_key" type="password" placeholder="留空保持不变" />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">Base URL</label>
            <Input v-model="editForm.base_url" placeholder="留空使用默认地址" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="space-y-1.5">
              <label class="text-sm font-medium">组织额度</label>
              <Input v-model="editForm.org_token_limit" type="number" placeholder="不限" />
            </div>
            <div class="space-y-1.5">
              <label class="text-sm font-medium">系统额度</label>
              <Input v-model="editForm.system_token_limit" type="number" placeholder="不限" />
            </div>
          </div>
          <div class="flex items-center gap-2">
            <input type="checkbox" id="edit-active" v-model="editForm.is_active" class="accent-primary" />
            <label for="edit-active" class="text-sm">启用</label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showEdit = false">取消</Button>
          <Button :disabled="saving" @click="handleEdit">
            {{ saving ? '保存中...' : '保存' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
