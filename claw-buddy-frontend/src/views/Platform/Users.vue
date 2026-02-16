<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Shield, User, ShieldCheck } from 'lucide-vue-next'
import api from '@/services/api'
import { useNotify } from '@/components/ui/notify'

const notify = useNotify()

interface UserItem {
  id: string
  name: string
  email: string | null
  role: string
  is_super_admin: boolean
  is_active: boolean
  current_org_id: string | null
  last_login_at: string | null
}

const users = ref<UserItem[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const res = await api.get('/auth/users')
    users.value = res.data.data ?? []
  } catch {
    notify.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
})

function formatDate(s: string | null) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN')
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div>
      <h1 class="text-xl font-bold">用户管理</h1>
      <p class="text-sm text-muted-foreground mt-1">平台所有注册用户</p>
    </div>

    <div class="border rounded-lg divide-y divide-border">
      <div
        v-for="u in users"
        :key="u.id"
        class="flex items-center justify-between px-4 py-3"
      >
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center">
            <User class="w-4 h-4 text-primary" />
          </div>
          <div>
            <div class="flex items-center gap-2">
              <span class="text-sm font-medium">{{ u.name }}</span>
              <Badge v-if="u.is_super_admin" variant="secondary" class="text-[10px] bg-amber-500/10 text-amber-400">
                <ShieldCheck class="w-3 h-3 mr-0.5" />
                超管
              </Badge>
            </div>
            <div class="text-xs text-muted-foreground">{{ u.email || u.id }}</div>
          </div>
        </div>
        <div class="flex items-center gap-4 text-xs text-muted-foreground">
          <span>最后登录: {{ formatDate(u.last_login_at) }}</span>
          <Badge :variant="u.is_active ? 'secondary' : 'destructive'" class="text-[10px]">
            {{ u.is_active ? '正常' : '禁用' }}
          </Badge>
        </div>
      </div>
      <div v-if="users.length === 0 && !loading" class="px-4 py-8 text-center text-sm text-muted-foreground">
        暂无用户
      </div>
    </div>
  </div>
</template>
