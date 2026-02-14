<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { LogOut, User, Package, Save, Plug, Loader2, Lock, Globe, HardDrive } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import api from '@/services/api'

const authStore = useAuthStore()
const router = useRouter()

// ── 镜像仓库配置 ──
const registryUrl = ref('')
const registryUsername = ref('')
const registryPassword = ref('')
const registryHasPassword = ref(false)
const registryDirty = ref(false)
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
    registryUsername.value = data.registry_username || ''
    // 密码后端返回 "******" 表示已配置
    registryHasPassword.value = data.registry_password === '******'
    registryPassword.value = ''
    registryDirty.value = false
    // 网络路由配置
    ingressBaseDomain.value = data.ingress_base_domain || ''
    tlsSecretName.value = data.tls_secret_name || ''
    networkDirty.value = false
  } catch {
    // 首次可能没有配置，不报错
  } finally {
    settingsLoading.value = false
  }
}

/** 保存镜像仓库全部配置到数据库 */
async function handleSaveRegistry() {
  registrySaving.value = true
  try {
    // 并行保存三项配置
    const promises = [
      api.put('/settings/image_registry', { value: registryUrl.value.trim() || null }),
      api.put('/settings/registry_username', { value: registryUsername.value.trim() || null }),
    ]
    // 密码只在用户填了新值时才保存（空值 = 不修改已有密码）
    if (registryPassword.value) {
      promises.push(api.put('/settings/registry_password', { value: registryPassword.value }))
    }
    await Promise.all(promises)
    registryDirty.value = false
    registryPassword.value = ''
    if (registryUsername.value.trim()) {
      registryHasPassword.value = true
    }
    toast.success('镜像仓库配置已保存')
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

function onRegistryFieldChange() {
  registryDirty.value = true
}

// ── 网络路由配置 ──
const ingressBaseDomain = ref('')
const tlsSecretName = ref('')
const networkDirty = ref(false)
const networkSaving = ref(false)

function onNetworkFieldChange() {
  networkDirty.value = true
}

async function handleSaveNetwork() {
  networkSaving.value = true
  try {
    await Promise.all([
      api.put('/settings/ingress_base_domain', { value: ingressBaseDomain.value.trim() || null }),
      api.put('/settings/tls_secret_name', { value: tlsSecretName.value.trim() || null }),
    ])
    networkDirty.value = false
    toast.success('网络路由配置已保存')
  } catch {
    toast.error('保存失败')
  } finally {
    networkSaving.value = false
  }
}

// ── 存储配置 ──
interface StorageClassItem {
  name: string
  provisioner: string
  reclaim_policy: string | null
  allow_volume_expansion: boolean
  is_default: boolean
  enabled: boolean
}
const storageClasses = ref<StorageClassItem[]>([])
const storageLoading = ref(false)
const storageSaving = ref(false)

async function loadStorageClasses() {
  storageLoading.value = true
  try {
    // scope=all 获取集群全部 SC（含 enabled 状态）
    const res = await api.get('/storage-classes', { params: { scope: 'all' } })
    storageClasses.value = res.data.data as StorageClassItem[]
  } catch {
    storageClasses.value = []
  } finally {
    storageLoading.value = false
  }
}

async function toggleStorageClass(scName: string) {
  const sc = storageClasses.value.find((s) => s.name === scName)
  if (!sc) return
  sc.enabled = !sc.enabled
  await saveAllowedStorageClasses()
}

async function saveAllowedStorageClasses() {
  storageSaving.value = true
  try {
    const enabledNames = storageClasses.value.filter((s) => s.enabled).map((s) => s.name)
    await api.put('/settings/allowed_storage_classes', { value: JSON.stringify(enabledNames) })
    toast.success('存储配置已保存')
  } catch {
    toast.error('保存失败')
  } finally {
    storageSaving.value = false
  }
}

onMounted(async () => {
  await loadSettings()
  // 加载完配置后，如果已有地址则自动测试一次
  if (registryUrl.value.trim()) {
    await handleTestRegistry()
  }
  // 加载可用 StorageClass
  await loadStorageClasses()
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
          <Input
            v-model="registryUrl"
            placeholder="如：registry.example.com/namespace/repo"
            class="font-mono text-sm"
            :disabled="settingsLoading"
            @update:model-value="onRegistryFieldChange"
          />
          <p class="text-xs text-muted-foreground mt-1">
            Docker Registry v2 地址，如 nodesk-center-cn-beijing.cr.volces.com/base-image/clawbuddy-base
          </p>
        </div>

        <!-- 认证凭证 -->
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="text-sm font-medium mb-1.5 block">用户名</label>
            <Input
              v-model="registryUsername"
              placeholder="Registry 用户名"
              class="font-mono text-sm"
              :disabled="settingsLoading"
              @update:model-value="onRegistryFieldChange"
            />
          </div>
          <div>
            <label class="text-sm font-medium mb-1.5 block">
              密码
              <span v-if="registryHasPassword" class="text-xs text-muted-foreground font-normal ml-1">
                (已配置，留空不修改)
              </span>
            </label>
            <Input
              v-model="registryPassword"
              type="password"
              :placeholder="registryHasPassword ? '留空不修改' : 'Registry 密码'"
              class="font-mono text-sm"
              :disabled="settingsLoading"
              @update:model-value="onRegistryFieldChange"
            />
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            :disabled="registryTesting || !registryUrl.trim()"
            @click="handleTestRegistry"
          >
            <Loader2 v-if="registryTesting" class="w-3.5 h-3.5 mr-1 animate-spin" />
            <Plug v-else class="w-3.5 h-3.5 mr-1" />
            测试连接
          </Button>
          <Button
            size="sm"
            :disabled="registrySaving || !registryDirty"
            @click="handleSaveRegistry"
          >
            <Loader2 v-if="registrySaving" class="w-3.5 h-3.5 mr-1 animate-spin" />
            <Save v-else class="w-3.5 h-3.5 mr-1" />
            保存
          </Button>
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

    <!-- 网络路由 -->
    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <Globe class="w-5 h-5" />
          网络路由
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-4">
        <p class="text-xs text-muted-foreground">
          配置子域名自动路由，部署实例时自动生成 Ingress 规则（如 instance.nodesk.tech）
        </p>
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="text-sm font-medium mb-1.5 block">基础域名</label>
            <Input
              v-model="ingressBaseDomain"
              placeholder="如：nodesk.tech"
              class="font-mono text-sm"
              :disabled="settingsLoading"
              @update:model-value="onNetworkFieldChange"
            />
            <p class="text-xs text-muted-foreground mt-1">
              需提前配置 DNS 泛解析 *.域名 指向火山云 SLB
            </p>
          </div>
          <div>
            <label class="text-sm font-medium mb-1.5 block">TLS Secret 名称</label>
            <Input
              v-model="tlsSecretName"
              placeholder="如：wildcard-nodesk-tls"
              class="font-mono text-sm"
              :disabled="settingsLoading"
              @update:model-value="onNetworkFieldChange"
            />
            <p class="text-xs text-muted-foreground mt-1">
              K8s 中通配符证书 Secret 的名称
            </p>
          </div>
        </div>
        <div class="flex gap-2">
          <Button
            size="sm"
            :disabled="networkSaving || !networkDirty"
            @click="handleSaveNetwork"
          >
            <Loader2 v-if="networkSaving" class="w-3.5 h-3.5 mr-1 animate-spin" />
            <Save v-else class="w-3.5 h-3.5 mr-1" />
            保存
          </Button>
        </div>
        <div v-if="ingressBaseDomain" class="text-xs text-muted-foreground bg-muted/30 rounded-lg p-3">
          实例部署后访问地址示例：<span class="font-mono text-foreground">https://&lt;instance-name&gt;.{{ ingressBaseDomain }}</span>
        </div>
      </CardContent>
    </Card>

    <!-- 存储配置 -->
    <Card>
      <CardHeader>
        <CardTitle class="flex items-center gap-2">
          <HardDrive class="w-5 h-5" />
          存储配置
        </CardTitle>
      </CardHeader>
      <CardContent class="space-y-4">
        <p class="text-xs text-muted-foreground">
          集群中的 StorageClass 列表。只有启用的才会出现在部署页的存储选择中。
        </p>
        <div v-if="storageLoading" class="text-sm text-muted-foreground">加载中...</div>
        <div v-else-if="storageClasses.length === 0" class="text-sm text-muted-foreground">
          未获取到 StorageClass（需先连接集群并创建 StorageClass）
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="sc in storageClasses"
            :key="sc.name"
            class="flex items-center justify-between rounded-md px-4 py-3 transition-colors"
            :class="sc.enabled ? 'bg-primary/5 border border-primary/20' : 'bg-muted/30'"
          >
            <div>
              <div class="text-sm font-mono font-medium">
                {{ sc.name }}
                <Badge v-if="sc.is_default" variant="outline" class="ml-2 text-xs">集群默认</Badge>
              </div>
              <div class="text-xs text-muted-foreground mt-0.5">
                {{ sc.provisioner }} · 回收策略: {{ sc.reclaim_policy || '-' }} · 扩容: {{ sc.allow_volume_expansion ? '支持' : '不支持' }}
              </div>
            </div>
            <Button
              :variant="sc.enabled ? 'default' : 'outline'"
              size="sm"
              :disabled="storageSaving"
              @click="toggleStorageClass(sc.name)"
            >
              {{ sc.enabled ? '已启用' : '启用' }}
            </Button>
          </div>
        </div>
        <p class="text-xs text-muted-foreground bg-muted/30 rounded-lg p-3">
          添加新存储类型：在 K8s 集群中 <span class="font-mono text-foreground">kubectl apply -f</span> 新的 StorageClass YAML，
          刷新页面即可看到。模板文件见 <span class="font-mono text-foreground">claw-buddy-artifacts/k8s/</span>
        </p>
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
