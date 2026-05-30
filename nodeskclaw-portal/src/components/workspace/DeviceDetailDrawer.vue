<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, MonitorCog, RefreshCw, ShieldCheck, Bot, User, Clock, MapPin, AlertCircle } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'
import type { AgentBrief, AgentDeviceGrantInfo, AgentDeviceLeaseInfo, AgentDeviceVisibilityInfo } from '@/stores/workspace'
import { useToast } from '@/composables/useToast'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  open: boolean
  workspaceId: string
  deviceId: string | null
  agents: AgentBrief[]
}>()

const emit = defineEmits<{
  'update:open': [val: boolean]
}>()

const { t, te } = useI18n()
const store = useWorkspaceStore()
const toast = useToast()

const loading = ref(false)
const grants = ref<AgentDeviceGrantInfo[]>([])
const visibility = ref<AgentDeviceVisibilityInfo | null>(null)
const selectedAgentId = ref('')

const device = computed(() =>
  props.deviceId ? store.devices.find(d => d.id === props.deviceId) || null : null,
)

const preset = computed(() =>
  device.value ? store.devicePresets.find(p => p.preset_id === device.value!.preset_id) || null : null,
)

const activeLease = computed(() => visibility.value?.active_lease || null)

function close() {
  emit('update:open', false)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

function formatDate(value?: string | null): string {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function activeLeaseField(key: string): string {
  const value = activeLease.value?.[key as keyof AgentDeviceLeaseInfo]
  return typeof value === 'string' ? value : ''
}

function statusLabel(status?: string | null): string {
  if (!status) return '-'
  const key = `deviceDetail.status_${status}`
  return te(key) ? t(key) : status
}

function reasonLabel(reason: string): string {
  const key = `deviceDetail.reason_${reason}`
  return te(key) ? t(key) : reason
}

function scopeLabel(scope: string): string {
  const key = `deviceDetail.scope_${scope}`
  return te(key) ? t(key) : scope
}

function subjectName(grant: AgentDeviceGrantInfo): string {
  if (grant.subject_type === 'agent') {
    const agent = props.agents.find(a => a.instance_id === grant.subject_id)
    return agent?.display_name || agent?.name || grant.subject_id
  }
  const member = store.members.find(m => m.user_id === grant.subject_id)
  return member?.user_name || grant.subject_id
}

async function loadDeviceContext() {
  if (!props.open || !props.deviceId) return
  loading.value = true
  try {
    await Promise.all([
      store.fetchDevicePresets(props.workspaceId),
      store.fetchDevices(props.workspaceId),
      store.fetchMembers(props.workspaceId),
    ])
    grants.value = await store.fetchDeviceGrants(props.workspaceId, props.deviceId)
    if (!selectedAgentId.value && props.agents.length > 0) {
      selectedAgentId.value = props.agents[0].instance_id
    }
    visibility.value = await store.fetchDeviceVisibility(
      props.workspaceId,
      props.deviceId,
      selectedAgentId.value || undefined,
    )
  } finally {
    loading.value = false
  }
}

async function grantSelectedAgent() {
  if (!props.deviceId || !selectedAgentId.value) return
  try {
    await store.createDeviceGrant(props.workspaceId, props.deviceId, {
      subject_type: 'agent',
      subject_id: selectedAgentId.value,
      scopes: ['discover', 'lease', 'invoke', 'delegate'],
      can_delegate: true,
    })
    toast.success(t('deviceDetail.grantCreated'))
    await loadDeviceContext()
  } catch (err: any) {
    toast.error(err?.response?.data?.detail?.message || t('deviceDetail.grantFailed'))
  }
}

async function revokeGrant(grantId: string) {
  if (!props.deviceId) return
  try {
    await store.revokeDeviceGrant(props.workspaceId, props.deviceId, grantId)
    toast.success(t('deviceDetail.grantRevoked'))
    await loadDeviceContext()
  } catch (err: any) {
    toast.error(err?.response?.data?.detail?.message || t('deviceDetail.revokeFailed'))
  }
}

async function reclaimActiveLease() {
  const leaseId = activeLeaseField('id')
  if (!props.deviceId || !leaseId) return
  try {
    await store.reclaimDeviceLease(props.workspaceId, props.deviceId, leaseId)
    toast.success(t('deviceDetail.leaseReclaimed'))
    await loadDeviceContext()
  } catch (err: any) {
    toast.error(err?.response?.data?.detail?.message || t('deviceDetail.reclaimFailed'))
  }
}

watch(() => props.open, (val) => {
  if (val) {
    document.addEventListener('keydown', onKeydown)
    void loadDeviceContext()
  } else {
    document.removeEventListener('keydown', onKeydown)
  }
})

watch(() => props.deviceId, () => {
  if (props.open) void loadDeviceContext()
})

watch(selectedAgentId, () => {
  if (props.open && props.deviceId) void loadDeviceContext()
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer-overlay">
      <div
        v-if="open"
        class="fixed inset-0 z-50 bg-black/40"
        @click="close"
      />
    </Transition>
    <Transition name="drawer-panel">
      <div
        v-if="open && device"
        class="fixed top-0 right-0 z-50 h-full w-[420px] max-w-[100vw] bg-card border-l border-border shadow-2xl flex flex-col overflow-hidden"
      >
        <div class="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div class="min-w-0">
            <div class="flex items-center gap-2 min-w-0">
              <MonitorCog class="w-4 h-4 text-teal-400 shrink-0" />
              <h3 class="text-sm font-semibold truncate">{{ device.display_name }}</h3>
            </div>
            <p class="text-xs text-muted-foreground mt-0.5">{{ t('deviceDetail.protocolName') }}</p>
          </div>
          <div class="flex items-center gap-2">
            <Button variant="unstyled" size="unstyled" class="p-1 rounded-md hover:bg-muted/50 transition-colors" :title="t('common.refresh')" @click="loadDeviceContext">
              <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
            </Button>
            <Button variant="unstyled" size="unstyled" class="p-1 rounded-md hover:bg-muted/50 transition-colors" @click="close">
              <X class="w-4 h-4" />
            </Button>
          </div>
        </div>

        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-6">
          <section class="space-y-3">
            <div class="flex items-center justify-between text-xs gap-3">
              <span class="text-muted-foreground">{{ t('deviceDetail.preset') }}</span>
              <span class="truncate">{{ preset?.display_name || device.preset_id }}</span>
            </div>
            <div class="flex items-center justify-between text-xs gap-3">
              <span class="text-muted-foreground">{{ t('deviceDetail.provider') }}</span>
              <span class="font-mono text-[11px] truncate">{{ device.provider_id }}</span>
            </div>
            <div class="flex items-center justify-between text-xs gap-3">
              <span class="text-muted-foreground">{{ t('deviceDetail.status') }}</span>
              <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-teal-500/10 text-teal-300">
                {{ statusLabel(device.status) }}
              </span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground inline-flex items-center gap-1">
                <MapPin class="w-3 h-3" />
                {{ t('deviceDetail.position') }}
              </span>
              <span>({{ device.hex_q }}, {{ device.hex_r }})</span>
            </div>
            <p v-if="device.status_reason" class="text-xs text-amber-300 bg-amber-500/10 border border-amber-500/20 rounded-md px-3 py-2">
              {{ device.status_reason }}
            </p>
          </section>

          <section class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <h4 class="text-xs font-semibold">{{ t('deviceDetail.visibility') }}</h4>
              <select
                v-model="selectedAgentId"
                class="max-w-[220px] rounded-md border border-border bg-background px-2 py-1 text-xs"
              >
                <option value="">{{ t('deviceDetail.noAgentSelected') }}</option>
                <option v-for="agent in agents" :key="agent.instance_id" :value="agent.instance_id">
                  {{ agent.display_name || agent.name }}
                </option>
              </select>
            </div>
            <div class="space-y-2 text-xs">
              <div class="flex items-center justify-between">
                <span class="text-muted-foreground">{{ t('deviceDetail.topologyReachable') }}</span>
                <span :class="visibility?.topology_reachable ? 'text-emerald-400' : 'text-amber-400'">
                  {{ visibility?.topology_reachable ? t('common.yes') : t('common.no') }}
                </span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-muted-foreground">{{ t('deviceDetail.visibleToAgent') }}</span>
                <span :class="visibility?.visible ? 'text-emerald-400' : 'text-amber-400'">
                  {{ visibility?.visible ? t('common.yes') : t('common.no') }}
                </span>
              </div>
              <div v-if="visibility?.reasons?.length" class="space-y-1">
                <div
                  v-for="reason in visibility.reasons"
                  :key="reason"
                  class="flex items-start gap-2 rounded-md bg-muted/35 px-3 py-2"
                >
                  <AlertCircle class="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0" />
                  <span>{{ reasonLabel(reason) }}</span>
                </div>
              </div>
            </div>
          </section>

          <section class="space-y-3">
            <div class="flex items-center justify-between">
              <h4 class="text-xs font-semibold">{{ t('deviceDetail.lease') }}</h4>
              <Button
                v-if="activeLease && store.hasPermission('manage_devices')"
                variant="unstyled"
                size="unstyled"
                class="px-2 py-1 rounded-md bg-muted hover:bg-accent text-xs transition-colors"
                @click="reclaimActiveLease"
              >
                {{ t('deviceDetail.reclaimLease') }}
              </Button>
            </div>
            <div v-if="activeLease" class="space-y-2 text-xs">
              <div class="flex items-center justify-between gap-3">
                <span class="text-muted-foreground inline-flex items-center gap-1">
                  <Bot class="w-3 h-3" />
                  {{ t('deviceDetail.holder') }}
                </span>
                <span class="font-mono text-[11px] truncate">{{ activeLeaseField('holder_agent_id') }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span class="text-muted-foreground inline-flex items-center gap-1">
                  <Clock class="w-3 h-3" />
                  {{ t('deviceDetail.expiresAt') }}
                </span>
                <span>{{ formatDate(activeLeaseField('expires_at')) }}</span>
              </div>
            </div>
            <p v-else class="text-xs text-muted-foreground">{{ t('deviceDetail.noActiveLease') }}</p>
          </section>

          <section class="space-y-3">
            <div class="flex items-center justify-between">
              <h4 class="text-xs font-semibold inline-flex items-center gap-1">
                <ShieldCheck class="w-3.5 h-3.5 text-emerald-400" />
                {{ t('deviceDetail.grants') }}
              </h4>
              <Button
                v-if="selectedAgentId && store.hasPermission('manage_devices')"
                variant="unstyled"
                size="unstyled"
                class="px-2 py-1 rounded-md bg-primary text-primary-foreground text-xs hover:bg-primary/90 transition-colors"
                @click="grantSelectedAgent"
              >
                {{ t('deviceDetail.grantSelectedAgent') }}
              </Button>
            </div>
            <div v-if="grants.length" class="space-y-2">
              <div
                v-for="grant in grants"
                :key="grant.id"
                class="rounded-lg border border-border px-3 py-2 space-y-2"
              >
                <div class="flex items-center justify-between gap-3 text-xs">
                  <span class="inline-flex items-center gap-1 min-w-0">
                    <component :is="grant.subject_type === 'agent' ? Bot : User" class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    <span class="truncate">{{ subjectName(grant) }}</span>
                  </span>
                  <Button
                    v-if="store.hasPermission('manage_devices')"
                    variant="unstyled"
                    size="unstyled"
                    class="text-[11px] text-destructive hover:underline"
                    @click="revokeGrant(grant.id)"
                  >
                    {{ t('deviceDetail.revoke') }}
                  </Button>
                </div>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="scope in grant.scopes"
                    :key="scope"
                    class="px-1.5 py-0.5 rounded bg-muted text-[10px] text-muted-foreground"
                  >
                    {{ scopeLabel(scope) }}
                  </span>
                  <span v-if="grant.can_delegate" class="px-1.5 py-0.5 rounded bg-emerald-500/10 text-[10px] text-emerald-300">
                    {{ t('deviceDetail.canDelegate') }}
                  </span>
                </div>
                <p v-if="grant.expires_at" class="text-[11px] text-muted-foreground">
                  {{ t('deviceDetail.grantExpiresAt', { time: formatDate(grant.expires_at) }) }}
                </p>
              </div>
            </div>
            <p v-else class="text-xs text-muted-foreground">{{ t('deviceDetail.noGrants') }}</p>
          </section>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer-overlay-enter-active,
.drawer-overlay-leave-active {
  transition: opacity 0.2s ease;
}
.drawer-overlay-enter-from,
.drawer-overlay-leave-to {
  opacity: 0;
}

.drawer-panel-enter-active,
.drawer-panel-leave-active {
  transition: transform 0.25s ease;
}
.drawer-panel-enter-from,
.drawer-panel-leave-to {
  transform: translateX(100%);
}
</style>
