<script setup lang="ts">
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Plus, Trash2, HardDrive, Container, Zap, Globe, Tag } from 'lucide-vue-next'

interface VolumeConfig {
  name: string
  volume_type: string
  mount_path: string
  pvc: string
  config_map_name: string
  secret_name: string
}

interface SidecarConfig {
  name: string
  image: string
  cpu_request: string
  cpu_limit: string
  mem_request: string
  mem_limit: string
}

interface InitContainerConfig {
  name: string
  image: string
  command: string
}

const props = defineProps<{
  modelValue: {
    volumes: VolumeConfig[]
    sidecars: SidecarConfig[]
    init_containers: InitContainerConfig[]
    network: { peers: string[] }
    custom_labels: Record<string, string>
    custom_annotations: Record<string, string>
  }
  availableInstances?: { id: string; name: string }[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: typeof props.modelValue): void
}>()

function update<K extends keyof typeof props.modelValue>(
  key: K,
  val: (typeof props.modelValue)[K]
) {
  emit('update:modelValue', { ...props.modelValue, [key]: val })
}

// ── Volume ──
const volumeTypes = [
  { value: 'pvc', label: 'PVC' },
  { value: 'emptyDir', label: 'EmptyDir' },
  { value: 'configMap', label: 'ConfigMap' },
  { value: 'secret', label: 'Secret' },
]

function addVolume() {
  update('volumes', [
    ...props.modelValue.volumes,
    { name: '', volume_type: 'pvc', mount_path: '', pvc: '', config_map_name: '', secret_name: '' },
  ])
}
function removeVolume(idx: number) {
  const arr = [...props.modelValue.volumes]
  arr.splice(idx, 1)
  update('volumes', arr)
}
function updateVolume(idx: number, field: string, val: string) {
  const arr = [...props.modelValue.volumes]
  arr[idx] = { ...arr[idx], [field]: val }
  update('volumes', arr)
}

// ── Sidecar ──
function addSidecar() {
  update('sidecars', [
    ...props.modelValue.sidecars,
    { name: '', image: '', cpu_request: '100m', cpu_limit: '500m', mem_request: '128Mi', mem_limit: '512Mi' },
  ])
}
function removeSidecar(idx: number) {
  const arr = [...props.modelValue.sidecars]
  arr.splice(idx, 1)
  update('sidecars', arr)
}
function updateSidecar(idx: number, field: keyof SidecarConfig, val: string) {
  const arr = [...props.modelValue.sidecars]
  arr[idx] = { ...arr[idx], [field]: val }
  update('sidecars', arr)
}

// ── Init Container ──
function addInit() {
  update('init_containers', [
    ...props.modelValue.init_containers,
    { name: '', image: '', command: '' },
  ])
}
function removeInit(idx: number) {
  const arr = [...props.modelValue.init_containers]
  arr.splice(idx, 1)
  update('init_containers', arr)
}
function updateInit(idx: number, field: keyof InitContainerConfig, val: string) {
  const arr = [...props.modelValue.init_containers]
  arr[idx] = { ...arr[idx], [field]: val }
  update('init_containers', arr)
}

// ── Network peers ──
function togglePeer(peerId: string) {
  const peers = [...props.modelValue.network.peers]
  const idx = peers.indexOf(peerId)
  if (idx >= 0) peers.splice(idx, 1)
  else peers.push(peerId)
  update('network', { peers })
}
const hasPeer = (id: string) => props.modelValue.network.peers.includes(id)

// ── Custom labels / annotations (key-value) ──
function addLabel() {
  const labels = { ...props.modelValue.custom_labels, '': '' }
  update('custom_labels', labels)
}
function removeLabel(key: string) {
  const labels = { ...props.modelValue.custom_labels }
  delete labels[key]
  update('custom_labels', labels)
}
function updateLabelKey(oldKey: string, newKey: string) {
  const labels = { ...props.modelValue.custom_labels }
  const val = labels[oldKey]
  delete labels[oldKey]
  labels[newKey] = val || ''
  update('custom_labels', labels)
}
function updateLabelValue(key: string, val: string) {
  update('custom_labels', { ...props.modelValue.custom_labels, [key]: val })
}

function addAnnotation() {
  const ann = { ...props.modelValue.custom_annotations, '': '' }
  update('custom_annotations', ann)
}
function removeAnnotation(key: string) {
  const ann = { ...props.modelValue.custom_annotations }
  delete ann[key]
  update('custom_annotations', ann)
}
function updateAnnotationKey(oldKey: string, newKey: string) {
  const ann = { ...props.modelValue.custom_annotations }
  const val = ann[oldKey]
  delete ann[oldKey]
  ann[newKey] = val || ''
  update('custom_annotations', ann)
}
function updateAnnotationValue(key: string, val: string) {
  update('custom_annotations', { ...props.modelValue.custom_annotations, [key]: val })
}

const labelEntries = () => Object.entries(props.modelValue.custom_labels || {})
const annotationEntries = () => Object.entries(props.modelValue.custom_annotations || {})
</script>

<template>
  <div class="space-y-4">
    <!-- Volumes (multi-type) -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm flex items-center gap-2">
            <HardDrive class="w-4 h-4" /> Volume 挂载
            <Badge variant="secondary" class="text-xs">{{ modelValue.volumes.length }}</Badge>
          </CardTitle>
          <Button variant="outline" size="sm" @click="addVolume">
            <Plus class="w-3 h-3 mr-1" /> 添加
          </Button>
        </div>
      </CardHeader>
      <CardContent v-if="modelValue.volumes.length > 0">
        <div v-for="(vol, idx) in modelValue.volumes" :key="idx" class="border rounded-md p-3 mb-3 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs text-muted-foreground">Volume #{{ idx + 1 }}</span>
            <Button variant="ghost" size="sm" class="h-6 text-destructive" @click="removeVolume(idx)">
              <Trash2 class="w-3 h-3" />
            </Button>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <Label class="text-xs">类型</Label>
              <select
                :value="vol.volume_type"
                class="w-full mt-1 h-9 rounded-md bg-card border border-border px-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
                @change="updateVolume(idx, 'volume_type', ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="vt in volumeTypes" :key="vt.value" :value="vt.value">{{ vt.label }}</option>
              </select>
            </div>
            <div>
              <Label class="text-xs">名称</Label>
              <Input :model-value="vol.name" class="mt-1" placeholder="data" @update:model-value="updateVolume(idx, 'name', $event as string)" />
            </div>
            <div>
              <Label class="text-xs">挂载路径</Label>
              <Input :model-value="vol.mount_path" class="mt-1" placeholder="/data" @update:model-value="updateVolume(idx, 'mount_path', $event as string)" />
            </div>
            <!-- PVC specific -->
            <div v-if="vol.volume_type === 'pvc'">
              <Label class="text-xs">PVC 名称</Label>
              <Input :model-value="vol.pvc" class="mt-1" placeholder="my-pvc" @update:model-value="updateVolume(idx, 'pvc', $event as string)" />
            </div>
            <!-- ConfigMap specific -->
            <div v-if="vol.volume_type === 'configMap'">
              <Label class="text-xs">ConfigMap 名称</Label>
              <Input :model-value="vol.config_map_name" class="mt-1" placeholder="my-cm" @update:model-value="updateVolume(idx, 'config_map_name', $event as string)" />
            </div>
            <!-- Secret specific -->
            <div v-if="vol.volume_type === 'secret'">
              <Label class="text-xs">Secret 名称</Label>
              <Input :model-value="vol.secret_name" class="mt-1" placeholder="my-secret" @update:model-value="updateVolume(idx, 'secret_name', $event as string)" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Sidecars -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm flex items-center gap-2">
            <Container class="w-4 h-4" /> Sidecar 容器
            <Badge variant="secondary" class="text-xs">{{ modelValue.sidecars.length }}</Badge>
          </CardTitle>
          <Button variant="outline" size="sm" @click="addSidecar">
            <Plus class="w-3 h-3 mr-1" /> 添加
          </Button>
        </div>
      </CardHeader>
      <CardContent v-if="modelValue.sidecars.length > 0">
        <div v-for="(sc, idx) in modelValue.sidecars" :key="idx" class="border rounded-md p-3 mb-3 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-xs text-muted-foreground">Sidecar #{{ idx + 1 }}</span>
            <Button variant="ghost" size="sm" class="h-6 text-destructive" @click="removeSidecar(idx)">
              <Trash2 class="w-3 h-3" />
            </Button>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <Label class="text-xs">名称</Label>
              <Input :model-value="sc.name" class="mt-1" placeholder="fluentd" @update:model-value="updateSidecar(idx, 'name', $event as string)" />
            </div>
            <div>
              <Label class="text-xs">镜像</Label>
              <Input :model-value="sc.image" class="mt-1" placeholder="fluentd:latest" @update:model-value="updateSidecar(idx, 'image', $event as string)" />
            </div>
            <div>
              <Label class="text-xs">CPU Request</Label>
              <Input :model-value="sc.cpu_request" class="mt-1" @update:model-value="updateSidecar(idx, 'cpu_request', $event as string)" />
            </div>
            <div>
              <Label class="text-xs">CPU Limit</Label>
              <Input :model-value="sc.cpu_limit" class="mt-1" @update:model-value="updateSidecar(idx, 'cpu_limit', $event as string)" />
            </div>
            <div>
              <Label class="text-xs">Memory Request</Label>
              <Input :model-value="sc.mem_request" class="mt-1" @update:model-value="updateSidecar(idx, 'mem_request', $event as string)" />
            </div>
            <div>
              <Label class="text-xs">Memory Limit</Label>
              <Input :model-value="sc.mem_limit" class="mt-1" @update:model-value="updateSidecar(idx, 'mem_limit', $event as string)" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Init Containers -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm flex items-center gap-2">
            <Zap class="w-4 h-4" /> Init 容器
            <Badge variant="secondary" class="text-xs">{{ modelValue.init_containers.length }}</Badge>
          </CardTitle>
          <Button variant="outline" size="sm" @click="addInit">
            <Plus class="w-3 h-3 mr-1" /> 添加
          </Button>
        </div>
      </CardHeader>
      <CardContent v-if="modelValue.init_containers.length > 0">
        <div v-for="(ic, idx) in modelValue.init_containers" :key="idx" class="grid grid-cols-4 gap-2 items-end mb-3">
          <div>
            <Label class="text-xs">名称</Label>
            <Input :model-value="ic.name" class="mt-1" placeholder="setup" @update:model-value="updateInit(idx, 'name', $event as string)" />
          </div>
          <div>
            <Label class="text-xs">镜像</Label>
            <Input :model-value="ic.image" class="mt-1" placeholder="busybox" @update:model-value="updateInit(idx, 'image', $event as string)" />
          </div>
          <div>
            <Label class="text-xs">命令</Label>
            <Input :model-value="ic.command" class="mt-1" placeholder="sh -c 'echo init'" @update:model-value="updateInit(idx, 'command', $event as string)" />
          </div>
          <Button variant="ghost" size="sm" class="h-9 text-destructive" @click="removeInit(idx)">
            <Trash2 class="w-3 h-3" />
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- Network -->
    <Card>
      <CardHeader>
        <CardTitle class="text-sm flex items-center gap-2">
          <Globe class="w-4 h-4" /> 跨实例网络
          <Badge variant="secondary" class="text-xs">{{ modelValue.network.peers.length }}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p class="text-xs text-muted-foreground mb-3">
          选择允许与此实例互相访问的其他实例
        </p>
        <div v-if="!availableInstances || availableInstances.length === 0" class="text-xs text-muted-foreground">
          暂无其他实例可选
        </div>
        <div v-else class="flex flex-wrap gap-2">
          <Button
            v-for="inst in availableInstances"
            :key="inst.id"
            :variant="hasPeer(inst.id) ? 'default' : 'outline'"
            size="sm"
            class="text-xs"
            @click="togglePeer(inst.id)"
          >
            {{ inst.name }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- Custom Labels -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm flex items-center gap-2">
            <Tag class="w-4 h-4" /> 自定义标签 (Labels)
            <Badge variant="secondary" class="text-xs">{{ labelEntries().length }}</Badge>
          </CardTitle>
          <Button variant="outline" size="sm" @click="addLabel">
            <Plus class="w-3 h-3 mr-1" /> 添加
          </Button>
        </div>
      </CardHeader>
      <CardContent v-if="labelEntries().length > 0">
        <div v-for="([key, val], idx) in labelEntries()" :key="idx" class="grid grid-cols-[1fr_1fr_auto] gap-2 mb-2">
          <Input :model-value="key" placeholder="key" class="text-xs" @change="updateLabelKey(key, ($event.target as HTMLInputElement).value)" />
          <Input :model-value="val" placeholder="value" class="text-xs" @update:model-value="updateLabelValue(key, $event as string)" />
          <Button variant="ghost" size="sm" class="h-9 text-destructive" @click="removeLabel(key)">
            <Trash2 class="w-3 h-3" />
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- Custom Annotations -->
    <Card>
      <CardHeader>
        <div class="flex items-center justify-between">
          <CardTitle class="text-sm flex items-center gap-2">
            <Tag class="w-4 h-4" /> 自定义注解 (Annotations)
            <Badge variant="secondary" class="text-xs">{{ annotationEntries().length }}</Badge>
          </CardTitle>
          <Button variant="outline" size="sm" @click="addAnnotation">
            <Plus class="w-3 h-3 mr-1" /> 添加
          </Button>
        </div>
      </CardHeader>
      <CardContent v-if="annotationEntries().length > 0">
        <div v-for="([key, val], idx) in annotationEntries()" :key="idx" class="grid grid-cols-[1fr_1fr_auto] gap-2 mb-2">
          <Input :model-value="key" placeholder="key" class="text-xs" @change="updateAnnotationKey(key, ($event.target as HTMLInputElement).value)" />
          <Input :model-value="val" placeholder="value" class="text-xs" @update:model-value="updateAnnotationValue(key, $event as string)" />
          <Button variant="ghost" size="sm" class="h-9 text-destructive" @click="removeAnnotation(key)">
            <Trash2 class="w-3 h-3" />
          </Button>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
