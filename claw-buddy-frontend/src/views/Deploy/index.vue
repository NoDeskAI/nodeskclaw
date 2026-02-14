<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useInstanceStore } from '@/stores/instance'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import AdvancedConfigPanel from '@/components/AdvancedConfigPanel.vue'
import {
  Rocket, CheckCircle, XCircle, AlertTriangle, Loader2,
  ChevronLeft, ChevronRight, ChevronDown, ChevronUp,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import api from '@/services/api'

const router = useRouter()
const authStore = useAuthStore()
const clusterStore = useClusterStore()
const instanceStore = useInstanceStore()

// ── Stepper ──
const currentStep = ref(0)
const steps = [
  { title: '基本信息', description: '名称、镜像版本、集群' },
  { title: '资源配额', description: 'CPU、内存、存储' },
  { title: '环境变量', description: '运行时环境变量' },
  { title: '确认部署', description: '预检与高级配置' },
]

// ── Form state ──
const form = ref({
  name: '',
  image_version: '',
  replicas: 1,
  cpu_request: '500m',
  cpu_limit: '2000m',
  mem_request: '512Mi',
  mem_limit: '4Gi',
  storage_class: 'nas-subpath',
  storage_size: '80Gi',
  quota_cpu: '4',
  quota_mem: '8Gi',
})

/** 根据用户邮箱前缀 + 已有实例数量生成默认实例名称（RFC 1123 格式） */
function generateDefaultName() {
  const user = authStore.user
  if (!user) return
  let prefix = 'instance'
  if (user.email) {
    prefix = user.email.split('@')[0].replace(/[^a-z0-9-]/gi, '-').toLowerCase()
  } else if (user.name) {
    prefix = user.name.replace(/[^a-z0-9-]/gi, '-').toLowerCase()
  }
  // 去除首尾 - 和连续 -
  prefix = prefix.replace(/^-+|-+$/g, '').replace(/-{2,}/g, '-') || 'instance'
  const count = instanceStore.instances.length + 1
  form.value.name = `${prefix}-${count}`
}

// ── Quota presets ──
const quotaPreset = ref<string>('medium')
const quotaPresets = [
  { key: 'small', label: '小型', cpu: '2', mem: '4Gi' },
  { key: 'medium', label: '中型', cpu: '4', mem: '8Gi' },
  { key: 'large', label: '大型', cpu: '8', mem: '16Gi' },
]

// 预设档位对应的容器资源配置
const presetResources: Record<string, { cpu_request: string; cpu_limit: string; mem_request: string; mem_limit: string; storage_size: string }> = {
  small:  { cpu_request: '250m',  cpu_limit: '1000m', mem_request: '256Mi', mem_limit: '1Gi',  storage_size: '40Gi' },
  medium: { cpu_request: '500m',  cpu_limit: '2000m', mem_request: '512Mi', mem_limit: '4Gi',  storage_size: '80Gi' },
  large:  { cpu_request: '1000m', cpu_limit: '4000m', mem_request: '1Gi',   mem_limit: '8Gi',  storage_size: '160Gi' },
}

function selectQuotaPreset(key: string) {
  quotaPreset.value = key
  const preset = quotaPresets.find((p) => p.key === key)
  if (preset) {
    form.value.quota_cpu = preset.cpu
    form.value.quota_mem = preset.mem
    // 联动更新容器资源
    const res = presetResources[key]
    if (res) {
      form.value.cpu_request = res.cpu_request
      form.value.cpu_limit = res.cpu_limit
      form.value.mem_request = res.mem_request
      form.value.mem_limit = res.mem_limit
      form.value.storage_size = res.storage_size
    }
  }
}

// ── Image tags from registry ──
const imageTags = ref<string[]>([])
const loadingTags = ref(false)

async function fetchImageTags() {
  loadingTags.value = true
  try {
    const res = await api.get('/registry/tags')
    const tags = res.data.data as { tag: string }[]
    imageTags.value = tags.map((t) => t.tag)
  } catch {
    // Registry not configured or unreachable -- allow manual input
    imageTags.value = []
  } finally {
    loadingTags.value = false
  }
}

// ── 基础域名（从 Settings 加载，用于展示访问地址）──
const baseDomain = ref('')

async function fetchBaseDomain() {
  try {
    const res = await api.get('/settings')
    const data = res.data.data as Record<string, string | null>
    baseDomain.value = data.ingress_base_domain || ''
  } catch {
    baseDomain.value = ''
  }
}

// ── StorageClass 列表（仅管理员启用的）──
interface StorageClassItem {
  name: string
  provisioner: string
  reclaim_policy: string | null
  allow_volume_expansion: boolean
  is_default: boolean
  enabled: boolean
}
const storageClasses = ref<StorageClassItem[]>([])
const loadingStorageClasses = ref(false)

async function fetchStorageClasses() {
  loadingStorageClasses.value = true
  try {
    const res = await api.get('/storage-classes')
    storageClasses.value = res.data.data as StorageClassItem[]
    // 如果当前选中的 storage_class 不在列表中，选默认或第一个
    if (storageClasses.value.length > 0) {
      const names = storageClasses.value.map((sc) => sc.name)
      if (!names.includes(form.value.storage_class)) {
        const defaultSc = storageClasses.value.find((sc) => sc.is_default)
        form.value.storage_class = defaultSc ? defaultSc.name : storageClasses.value[0].name
      }
    }
  } catch {
    storageClasses.value = []
  } finally {
    loadingStorageClasses.value = false
  }
}

const accessUrl = computed(() => {
  if (!form.value.name || !baseDomain.value) return ''
  const proto = baseDomain.value ? 'https' : 'http'
  return `${proto}://${form.value.name}.${baseDomain.value}`
})

// ── Env vars ──
const envPairs = ref<{ key: string; value: string }[]>([])
function addEnv() {
  envPairs.value.push({ key: '', value: '' })
}
function removeEnv(idx: number) {
  envPairs.value.splice(idx, 1)
}

// ── Advanced config ──
const showAdvanced = ref(false)
const advancedConfig = ref({
  volumes: [] as { name: string; volume_type: string; mount_path: string; pvc: string; config_map_name: string; secret_name: string }[],
  sidecars: [] as { name: string; image: string; cpu_request: string; cpu_limit: string; mem_request: string; mem_limit: string }[],
  init_containers: [] as { name: string; image: string; command: string }[],
  network: { peers: [] as string[] },
  custom_labels: {} as Record<string, string>,
  custom_annotations: {} as Record<string, string>,
})

// ── Precheck / Deploy state ──
const precheckResult = ref<{passed: boolean; items: {name: string; status: string; message: string}[]} | null>(null)
const checking = ref(false)
const deploying = ref(false)

const selectedCluster = computed(() => clusterStore.currentCluster)
const availableInstances = computed(() =>
  instanceStore.instances.map((i) => ({ id: i.id, name: i.name }))
)

onMounted(async () => {
  await Promise.all([
    clusterStore.fetchClusters(),
    instanceStore.fetchInstances(),
    fetchImageTags(),
    fetchBaseDomain(),
    fetchStorageClasses(),
  ])
  // 自动生成实例名称
  generateDefaultName()
  // 默认选中最新的镜像 tag
  if (imageTags.value.length > 0) {
    form.value.image_version = imageTags.value[0]
  }
})

function buildPayload() {
  const hasAdvanced =
    advancedConfig.value.volumes.length > 0 ||
    advancedConfig.value.sidecars.length > 0 ||
    advancedConfig.value.init_containers.length > 0 ||
    advancedConfig.value.network.peers.length > 0 ||
    Object.keys(advancedConfig.value.custom_labels).length > 0 ||
    Object.keys(advancedConfig.value.custom_annotations).length > 0

  const initContainers = advancedConfig.value.init_containers.map((ic) => ({
    ...ic,
    command: ic.command ? ic.command.split(' ') : [],
  }))

  // Build env_vars from key-value pairs
  const envVars: Record<string, string> = {}
  for (const pair of envPairs.value) {
    if (pair.key.trim()) envVars[pair.key.trim()] = pair.value
  }

  return {
    ...form.value,
    cluster_id: selectedCluster.value?.id,
    env_vars: Object.keys(envVars).length > 0 ? envVars : {},
    advanced_config: hasAdvanced
      ? { ...advancedConfig.value, init_containers: initContainers }
      : undefined,
  }
}

async function runPrecheck() {
  if (!selectedCluster.value) {
    toast.error('请先选择集群')
    return
  }
  checking.value = true
  precheckResult.value = null
  try {
    const res = await api.post('/deploy/precheck', buildPayload())
    precheckResult.value = res.data.data
  } catch {
    toast.error('预检失败')
  } finally {
    checking.value = false
  }
}

async function handleDeploy() {
  if (!selectedCluster.value) return
  deploying.value = true

  try {
    const res = await api.post('/deploy', buildPayload())
    const deployId = res.data.data.deploy_id
    toast.info('部署任务已提交，正在执行...')

    // 跳转到独立的部署进度页
    router.push({
      name: 'DeployProgress',
      params: { deployId },
      query: { name: form.value.name },
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '部署请求失败'
    toast.error(msg)
    deploying.value = false
  }
}

function statusIcon(status: string) {
  if (status === 'pass') return CheckCircle
  if (status === 'fail') return XCircle
  return AlertTriangle
}

// ── Step navigation ──
function nextStep() {
  if (currentStep.value < steps.length - 1) currentStep.value++
}
function prevStep() {
  if (currentStep.value > 0) currentStep.value--
}

// ── Step validation ──
const canProceedStep0 = computed(() =>
  !!form.value.name && !!form.value.image_version && !!selectedCluster.value
)
const canProceedStep1 = computed(() =>
  !!form.value.quota_cpu && !!form.value.quota_mem
)

// ── YAML 预览 ──
const showYaml = ref(false)
const yamlPreview = computed(() => {
  const p = buildPayload()
  const lines: string[] = []
  lines.push('apiVersion: apps/v1')
  lines.push('kind: Deployment')
  lines.push('metadata:')
  lines.push(`  name: ${p.name || '<name>'}`)
  lines.push(`  namespace: clawbuddy-${p.name || '<name>'}`)
  lines.push('spec:')
  lines.push(`  replicas: ${p.replicas}`)
  lines.push('  template:')
  lines.push('    spec:')
  lines.push('      containers:')
  lines.push(`        - name: ${p.name || '<name>'}`)
  lines.push(`          image: <registry>:${p.image_version || '<tag>'}`)
  lines.push('          resources:')
  lines.push('            requests:')
  lines.push(`              cpu: "${p.cpu_request}"`)
  lines.push(`              memory: "${p.mem_request}"`)
  lines.push('            limits:')
  lines.push(`              cpu: "${p.cpu_limit}"`)
  lines.push(`              memory: "${p.mem_limit}"`)
  if (p.env_vars && Object.keys(p.env_vars).length > 0) {
    lines.push('          env:')
    for (const [k, v] of Object.entries(p.env_vars)) {
      lines.push(`            - name: ${k}`)
      lines.push(`              value: "${v}"`)
    }
  }
  if (p.advanced_config) {
    const ac = p.advanced_config as Record<string, unknown>
    const vols = ac.volumes as { name: string; mount_path: string; volume_type: string }[] | undefined
    if (vols && vols.length > 0) {
      lines.push('          volumeMounts:')
      for (const v of vols) {
        lines.push(`            - name: ${v.name}`)
        lines.push(`              mountPath: ${v.mount_path}`)
      }
      lines.push('      volumes:')
      for (const v of vols) {
        lines.push(`        - name: ${v.name}`)
        lines.push(`          ${v.volume_type}: {}`)
      }
    }
    const sidecars = ac.sidecars as { name: string; image: string }[] | undefined
    if (sidecars && sidecars.length > 0) {
      for (const s of sidecars) {
        lines.push(`        - name: ${s.name}`)
        lines.push(`          image: ${s.image}`)
      }
    }
    const labels = ac.custom_labels as Record<string, string> | undefined
    if (labels && Object.keys(labels).length > 0) {
      lines.push('    metadata:')
      lines.push('      labels:')
      for (const [k, v] of Object.entries(labels)) {
        lines.push(`        ${k}: "${v}"`)
      }
    }
  }
  lines.push('---')
  lines.push('apiVersion: v1')
  lines.push('kind: Service')
  lines.push('metadata:')
  lines.push(`  name: ${p.name || '<name>'}`)
  lines.push('spec:')
  lines.push('  type: ClusterIP')
  lines.push('  ports:')
  lines.push('    - port: 18789')
  lines.push('      targetPort: 18789')
  if (baseDomain.value && p.name) {
    const host = `${p.name}.${baseDomain.value}`
    lines.push('---')
    lines.push('apiVersion: networking.k8s.io/v1')
    lines.push('kind: Ingress')
    lines.push('metadata:')
    lines.push(`  name: ${p.name}`)
    lines.push('  annotations:')
    lines.push('    nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"')
    lines.push('    nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"')
    lines.push('spec:')
    lines.push('  ingressClassName: nginx')
    lines.push('  tls:')
    lines.push(`    - hosts: ["${host}"]`)
    lines.push('  rules:')
    lines.push(`    - host: ${host}`)
    lines.push('      http:')
    lines.push('        paths:')
    lines.push('          - path: /')
    lines.push('            pathType: Prefix')
    lines.push('            backend:')
    lines.push('              service:')
    lines.push(`                name: ${p.name}`)
    lines.push('                port:')
    lines.push('                  number: 18789')
  }

  return lines.join('\n')
})
</script>

<template>
  <div class="p-6 space-y-6 max-w-3xl mx-auto">
    <div class="flex items-center gap-2">
      <Rocket class="w-6 h-6" />
      <h1 class="text-2xl font-bold">部署 OpenClaw 实例</h1>
    </div>

    <!-- Cluster selector hint -->
    <div v-if="!selectedCluster" class="text-destructive text-sm">
      请先在集群管理中添加并选择一个集群
    </div>
    <div v-else class="text-sm text-muted-foreground">
      目标集群: <Badge variant="secondary">{{ selectedCluster.name }}</Badge>
    </div>

    <!-- Stepper indicator -->
    <div class="flex items-center gap-1">
      <template v-for="(step, idx) in steps" :key="idx">
        <button
          class="flex items-center gap-2 px-3 py-1.5 rounded-full text-xs transition-colors"
          :class="
            idx === currentStep
              ? 'bg-primary text-primary-foreground font-medium'
              : idx < currentStep
                ? 'bg-primary/20 text-primary'
                : 'bg-muted text-muted-foreground'
          "
          @click="idx <= currentStep ? (currentStep = idx) : null"
        >
          <span class="w-5 h-5 rounded-full inline-flex items-center justify-center text-[10px] font-bold"
            :class="idx < currentStep ? 'bg-primary text-primary-foreground' : 'bg-muted-foreground/20'"
          >{{ idx + 1 }}</span>
          {{ step.title }}
        </button>
        <div v-if="idx < steps.length - 1" class="w-8 h-px bg-border" />
      </template>
    </div>

    <!-- Step 0: 基本信息 -->
    <Card v-show="currentStep === 0">
      <CardHeader><CardTitle>基本信息</CardTitle></CardHeader>
      <CardContent class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="text-sm font-medium mb-1.5 block">实例名称 *</label>
            <Input v-model="form.name" placeholder="如: prod-main" />
          </div>
          <div>
            <label class="text-sm font-medium mb-1.5 block">镜像版本 *</label>
            <div class="relative">
              <Input
                v-model="form.image_version"
                :placeholder="loadingTags ? '加载中...' : '选择或输入版本'"
                list="image-tag-list"
              />
              <datalist id="image-tag-list">
                <option v-for="tag in imageTags" :key="tag" :value="tag" />
              </datalist>
            </div>
            <p v-if="imageTags.length === 0 && !loadingTags" class="text-xs text-muted-foreground mt-1">
              未配置镜像仓库，请手动输入版本号
            </p>
          </div>
          <div>
            <label class="text-sm font-medium mb-1.5 block">副本数</label>
            <div class="h-9 flex items-center px-3 rounded-md border border-border bg-muted/30 text-sm font-mono">
              {{ form.replicas }}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Step 1: 资源配额 -->
    <Card v-show="currentStep === 1">
      <CardHeader><CardTitle>资源配额</CardTitle></CardHeader>
      <CardContent class="space-y-4">
        <!-- Quota presets -->
        <div>
          <label class="text-sm font-medium mb-2 block">Namespace 配额档位</label>
          <div class="grid grid-cols-3 gap-3">
            <button
              v-for="preset in quotaPresets"
              :key="preset.key"
              class="rounded-lg border-2 p-3 text-center transition-all text-sm"
              :class="
                quotaPreset === preset.key
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/50'
              "
              @click="selectQuotaPreset(preset.key)"
            >
              <div class="font-medium">{{ preset.label }}</div>
              <div v-if="preset.key !== 'custom'" class="text-xs text-muted-foreground mt-1">
                {{ preset.cpu }}c / {{ preset.mem }}
              </div>
            </button>
          </div>
        </div>

        <!-- 只读展示当前配额 -->
        <div class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm bg-muted/30 rounded-lg p-4">
          <div class="text-muted-foreground">Namespace 配额</div>
          <div class="font-medium font-mono">{{ form.quota_cpu }}c / {{ form.quota_mem }}</div>
          <div class="text-muted-foreground">CPU (Request / Limit)</div>
          <div class="font-medium font-mono">{{ form.cpu_request }} / {{ form.cpu_limit }}</div>
          <div class="text-muted-foreground">内存 (Request / Limit)</div>
          <div class="font-medium font-mono">{{ form.mem_request }} / {{ form.mem_limit }}</div>
        </div>

        <!-- 存储配置 -->
        <div class="border-t pt-4">
          <label class="text-sm font-medium mb-2 block">存储配置</label>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="text-xs text-muted-foreground mb-1.5 block">存储类型 (StorageClass)</label>
              <Select v-model="form.storage_class" :key="storageClasses.length">
                <SelectTrigger class="w-full font-mono text-sm">
                  <SelectValue placeholder="选择 StorageClass" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem
                    v-if="storageClasses.length === 0"
                    value="nas-subpath"
                  >
                    nas-subpath
                  </SelectItem>
                  <SelectItem
                    v-for="sc in storageClasses"
                    :key="sc.name"
                    :value="sc.name"
                  >
                    <div class="flex items-center justify-between w-full gap-4">
                      <span class="font-mono">{{ sc.name }}</span>
                      <Badge v-if="sc.is_default" variant="secondary" class="text-[10px] px-1.5 py-0">默认</Badge>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <p v-if="loadingStorageClasses" class="text-xs text-muted-foreground mt-1">加载中...</p>
              <p v-else-if="storageClasses.length === 0" class="text-xs text-muted-foreground mt-1">
                未获取到集群 StorageClass，使用默认值
              </p>
              <p v-else class="text-xs text-muted-foreground mt-1">
                {{ storageClasses.find(sc => sc.name === form.storage_class)?.provisioner || '' }}
              </p>
            </div>
            <div>
              <label class="text-xs text-muted-foreground mb-1.5 block">存储大小</label>
              <div class="h-9 flex items-center px-3 rounded-md border border-border bg-muted/30 text-sm font-mono">
                {{ form.storage_size }}
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Step 2: 环境变量 -->
    <Card v-show="currentStep === 2">
      <CardHeader><CardTitle>环境变量</CardTitle></CardHeader>
      <CardContent class="space-y-4">
        <div>
          <div class="flex items-center justify-between mb-2">
            <label class="text-sm font-medium">运行时环境变量</label>
            <Button variant="outline" size="sm" @click="addEnv">+ 添加</Button>
          </div>
          <div v-if="envPairs.length === 0" class="text-xs text-muted-foreground">
            暂无环境变量，可直接跳过此步
          </div>
          <div v-for="(pair, idx) in envPairs" :key="idx" class="grid grid-cols-[1fr_1fr_auto] gap-2 mb-2">
            <Input v-model="pair.key" placeholder="KEY" class="text-xs" />
            <Input v-model="pair.value" placeholder="VALUE" class="text-xs" />
            <Button variant="ghost" size="sm" class="text-destructive h-9" @click="removeEnv(idx)">
              X
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Step 3: 确认部署 -->
    <template v-if="currentStep === 3">
      <!-- Summary -->
      <Card>
        <CardHeader><CardTitle>部署概览</CardTitle></CardHeader>
        <CardContent>
          <div class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div class="text-muted-foreground">实例名称</div>
            <div class="font-medium">{{ form.name }}</div>
            <div class="text-muted-foreground">镜像版本</div>
            <div class="font-medium">{{ form.image_version }}</div>
            <div class="text-muted-foreground">集群</div>
            <div class="font-medium">{{ selectedCluster?.name }}</div>
            <div class="text-muted-foreground">副本数</div>
            <div class="font-medium">{{ form.replicas }}</div>
            <div class="text-muted-foreground">资源配额</div>
            <div class="font-medium">{{ form.quota_cpu }}c / {{ form.quota_mem }}</div>
            <div class="text-muted-foreground">CPU</div>
            <div class="font-medium">{{ form.cpu_request }} / {{ form.cpu_limit }}</div>
            <div class="text-muted-foreground">内存</div>
            <div class="font-medium">{{ form.mem_request }} / {{ form.mem_limit }}</div>
            <div class="text-muted-foreground">存储类型</div>
            <div class="font-medium font-mono">{{ form.storage_class }}</div>
            <div class="text-muted-foreground">存储大小</div>
            <div class="font-medium font-mono">{{ form.storage_size }}</div>
            <div class="text-muted-foreground">访问地址</div>
            <div v-if="accessUrl" class="font-medium font-mono text-primary">{{ accessUrl }}</div>
            <div v-else class="text-muted-foreground text-xs">请在 Settings 页面配置基础域名</div>
          </div>
        </CardContent>
      </Card>

      <!-- YAML 预览 -->
      <Card>
        <CardHeader>
          <button
            class="flex items-center justify-between w-full text-left"
            @click="showYaml = !showYaml"
          >
            <CardTitle class="text-base">YAML 预览</CardTitle>
            <ChevronDown v-if="!showYaml" class="w-4 h-4 text-muted-foreground" />
            <ChevronUp v-else class="w-4 h-4 text-muted-foreground" />
          </button>
        </CardHeader>
        <CardContent v-if="showYaml">
          <pre class="text-xs font-mono bg-muted/30 rounded-lg p-4 overflow-x-auto max-h-96 overflow-y-auto whitespace-pre text-muted-foreground">{{ yamlPreview }}</pre>
          <p class="text-xs text-muted-foreground mt-2">
            此为预览，实际部署时由后端根据表单数据生成完整 K8s 资源清单
          </p>
        </CardContent>
      </Card>

      <!-- Advanced config toggle -->
      <Card>
        <CardHeader>
          <button
            class="flex items-center justify-between w-full text-left"
            @click="showAdvanced = !showAdvanced"
          >
            <CardTitle class="text-base">高级配置</CardTitle>
            <ChevronDown v-if="!showAdvanced" class="w-4 h-4 text-muted-foreground" />
            <ChevronUp v-else class="w-4 h-4 text-muted-foreground" />
          </button>
        </CardHeader>
        <CardContent v-if="showAdvanced">
          <AdvancedConfigPanel
            v-model="advancedConfig"
            :available-instances="availableInstances"
          />
        </CardContent>
      </Card>

      <!-- Precheck results -->
      <Card v-if="precheckResult">
        <CardHeader><CardTitle>预检结果</CardTitle></CardHeader>
        <CardContent>
          <div class="space-y-2">
            <div
              v-for="item in precheckResult.items"
              :key="item.name"
              class="flex items-center gap-2 text-sm"
            >
              <component
                :is="statusIcon(item.status)"
                class="w-4 h-4"
                :class="{
                  'text-green-400': item.status === 'pass',
                  'text-red-400': item.status === 'fail',
                  'text-yellow-400': item.status === 'warning',
                }"
              />
              <span class="font-medium w-16">{{ item.name }}</span>
              <span class="text-muted-foreground">{{ item.message }}</span>
            </div>
          </div>
        </CardContent>
      </Card>

    </template>

    <!-- Navigation + Actions -->
    <div class="flex justify-between">
      <Button
        v-if="currentStep > 0"
        variant="outline"
        @click="prevStep"
      >
        <ChevronLeft class="w-4 h-4 mr-1" /> 上一步
      </Button>
      <div v-else />

      <div class="flex gap-3">
        <template v-if="currentStep < 3">
          <Button
            :disabled="
              (currentStep === 0 && !canProceedStep0) ||
              (currentStep === 1 && !canProceedStep1)
            "
            @click="nextStep"
          >
            下一步 <ChevronRight class="w-4 h-4 ml-1" />
          </Button>
        </template>
        <template v-else>
          <Button variant="outline" :disabled="checking || !selectedCluster" @click="runPrecheck">
            {{ checking ? '检查中...' : '预检' }}
          </Button>
          <Button
            :disabled="deploying || !selectedCluster || !form.name || !form.image_version"
            @click="handleDeploy"
          >
            <Loader2 v-if="deploying" class="w-4 h-4 mr-2 animate-spin" />
            {{ deploying ? '部署中...' : '开始部署' }}
          </Button>
        </template>
      </div>
    </div>
  </div>
</template>
