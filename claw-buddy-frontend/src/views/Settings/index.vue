<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { LogOut, User, Package, Save, Plug, Loader2 } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import api from '@/services/api'

const authStore = useAuthStore()
const router = useRouter()

// ── 镜像仓库配置 ──
const registryUrl = ref('')
const registryUrlDirty = ref(false)
const registrySaving = ref(false)
const registryTesting = ref(false)
const registryTags = ref<string[]>([])
const registryStatus = ref<'idle' | 'connected' | 'error'>('idle')
const registryError = ref('')
const settingsLoading = ref(false)

async function handleLogout() {
  await authStore.logout()
  toast.success('已登出')
  router.push('/login')
}

/** 从后端加载当前配置 */
async function loadSettings() {
  settingsLoading.value = true
  try {
    const res = await api.get('/settings')
    const data = res.data.data as Record<string, string | null>
    registryUrl.value = data.image_registry || ''
    registryUrlDirty.value = false
  } catch {
    // 首次可能没有配置，不报错
  } finally {
    settingsLoading.value = false
  }
}

/** 保存镜像仓库地址到数据库 */
async function handleSaveRegistry() {
  registrySaving.value = true
  try {
    await api.put('/settings/image_registry', {
      value: registryUrl.value.trim() || null,
    })
    registryUrlDirty.value = false
    toast.success('镜像仓库地址已保存')
    // 保存后自动测试连接
    await handleTestRegistry()
  } catch {
    toast.error('保存失败')
  } finally {
    registrySaving.value = false
  }
}

/** 测试镜像仓库连通性 */
async function handleTestRegistry() {
  registryTesting.value = true
  registryStatus.value = 'idle'
  registryError.value = ''
  registryTags.value = []
  try {
    const params = registryUrl.value.trim() ? { registry_url: registryUrl.value.trim() } : {}
    const res = await api.get('/registry/tags', { params })
    const tags = res.data.data as { tag: string }[]
    registryTags.value = tags.map((t) => t.tag)
    if (tags.length > 0) {
      registryStatus.value = 'connected'
    } else if (!registryUrl.value.trim()) {
      registryStatus.value = 'idle'
    } else {
      registryStatus.value = 'connected'
      registryError.value = '连接成功，但仓库中暂无 Tag'
    }
  } catch {
    registryStatus.value = 'error'
    registryError.value = '仓库不可达或地址错误'
  } finally {
    registryTesting.value = false
  }
}

function onRegistryInput(val: string | number) {
  registryUrl.value = String(val)
  registryUrlDirty.value = true
}

onMounted(async () => {
  await loadSettings()
  // 加载完配置后，如果已有地址则自动测试一次
  if (registryUrl.value.trim()) {
    await handleTestRegistry()
  }
})
</script>

<template>
  <div class="p-6 space-y-6 max-w-2xl">
    <h1 class="text-2xl font-bold">设置</h1>

    <!-- 用户信息 -->
    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <User class="w-5 h-5" />
          账号信息
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-3">
        <template v-if="authStore.user">
          <div class="flex items-center gap-3">
            <img
              v-if="authStore.user.avatar_url"
              :src="authStore.user.avatar_url"
              class="w-10 h-10 rounded-full"
              alt="头像"
            />
            <div
              v-else
              class="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold"
            >
              {{ authStore.user.name?.charAt(0) || '?' }}
            </div>
            <div>
              <div class="font-medium">{{ authStore.user.name }}</div>
              <div class="text-sm text-muted-foreground">{{ authStore.user.email || '无邮箱' }}</div>
            </div>
            <Badge variant="secondary" class="ml-auto">{{ authStore.user.role }}</Badge>
          </div>
        </template>
        <p v-else class="text-sm text-muted-foreground">未登录</p>

        <Button variant="destructive" class="mt-4" @click="handleLogout">
          <LogOut class="w-4 h-4 mr-2" />
          退出登录
        </Button>
      </CardContent>
    </Card>

    <!-- 镜像仓库 -->
    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <Package class="w-5 h-5" />
          镜像仓库
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-4">
        <!-- 地址输入 -->
        <div>
          <label class="text-sm font-medium mb-1.5 block">仓库地址</label>
          <div class="flex gap-2">
            <Input
              :model-value="registryUrl"
              placeholder="如：registry.example.com/org/image"
              class="flex-1 font-mono text-sm"
              :disabled="settingsLoading"
              @update:model-value="onRegistryInput"
            />
            <Button
              variant="outline"
              size="sm"
              :disabled="registryTesting || !registryUrl.trim()"
              class="shrink-0"
              @click="handleTestRegistry"
            >
              <Loader2 v-if="registryTesting" class="w-3.5 h-3.5 mr-1 animate-spin" />
              <Plug v-else class="w-3.5 h-3.5 mr-1" />
              测试连接
            </Button>
            <Button
              size="sm"
              :disabled="registrySaving || !registryUrlDirty"
              class="shrink-0"
              @click="handleSaveRegistry"
            >
              <Loader2 v-if="registrySaving" class="w-3.5 h-3.5 mr-1 animate-spin" />
              <Save v-else class="w-3.5 h-3.5 mr-1" />
              保存
            </Button>
          </div>
          <p class="text-xs text-muted-foreground mt-1">
            Docker Registry v2 地址，如 https://registry.example.com/org/image
          </p>
        </div>

        <!-- 连接状态 -->
        <div v-if="registryStatus === 'connected' && registryTags.length > 0">
          <div class="flex items-center gap-1.5 text-sm mb-2">
            <span class="w-2 h-2 rounded-full bg-green-400 inline-block" />
            仓库已连接，共 <span class="font-medium">{{ registryTags.length }}</span> 个可用 Tag
          </div>
          <div class="flex flex-wrap gap-1.5">
            <Badge
              v-for="tag in registryTags.slice(0, 20)"
              :key="tag"
              variant="secondary"
              class="text-xs font-mono"
            >
              {{ tag }}
            </Badge>
            <span v-if="registryTags.length > 20" class="text-xs text-muted-foreground self-center">
              ... 及其他 {{ registryTags.length - 20 }} 个
            </span>
          </div>
        </div>

        <div v-else-if="registryStatus === 'connected' && registryError" class="flex items-center gap-1.5 text-sm text-yellow-400">
          <span class="w-2 h-2 rounded-full bg-yellow-400 inline-block" />
          {{ registryError }}
        </div>

        <div v-else-if="registryStatus === 'error'" class="flex items-center gap-1.5 text-sm text-red-400">
          <span class="w-2 h-2 rounded-full bg-red-400 inline-block" />
          {{ registryError }}
        </div>
      </CardContent>
    </Card>

    <!-- 版本信息 -->
    <Card>
      <CardHeader>
        <CardTitle>关于</CardTitle>
      </CardHeader>
      <CardContent>
        <div class="text-sm text-muted-foreground space-y-1">
          <p>ClawBuddy v0.1.0</p>
          <p>One-click deploy, full control.</p>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
