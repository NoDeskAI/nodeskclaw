<script setup lang="ts">
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '@/composables/useToast'
import { X, Copy, User as UserIcon, Bot } from 'lucide-vue-next'
import type { AuditLog } from '@/components/audit/AuditLogTable.vue'

const props = defineProps<{
  log: AuditLog | null
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [val: boolean]
}>()

const { t, te } = useI18n()
const toast = useToast()

function close() {
  emit('update:open', false)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

watch(() => props.open, (val) => {
  if (val) {
    document.addEventListener('keydown', onKeydown)
  } else {
    document.removeEventListener('keydown', onKeydown)
  }
})

function localizeAction(action: string): string {
  const key = 'auditActions.' + action.replace(/\./g, '_')
  return te(key) ? t(key) : action
}

function localizeTargetType(tt: string): string {
  const key = 'auditTargetTypes.' + tt
  return te(key) ? t(key) : tt
}

const actionColorMap: Record<string, string> = {
  auth: 'bg-blue-500/15 text-blue-400',
  instance: 'bg-emerald-500/15 text-emerald-400',
  deploy: 'bg-emerald-500/15 text-emerald-400',
  cluster: 'bg-amber-500/15 text-amber-400',
  workspace: 'bg-violet-500/15 text-violet-400',
  org: 'bg-amber-500/15 text-amber-400',
  llm_key: 'bg-amber-500/15 text-amber-400',
  system: 'bg-amber-500/15 text-amber-400',
}

function actionBadgeClass(action: string): string {
  const prefix = action.split('.')[0]
  return actionColorMap[prefix] ?? 'bg-muted text-muted-foreground'
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

const detailsJson = computed(() => {
  if (!props.log?.details) return null
  return JSON.stringify(props.log.details, null, 2)
})

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(t('auditLogs.drawerCopied'))
  } catch {
    /* clipboard not available */
  }
}
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
        v-if="open && log"
        class="fixed top-0 right-0 z-50 h-full w-[400px] bg-card border-l border-border shadow-2xl flex flex-col overflow-hidden"
      >
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <div>
            <h3 class="text-sm font-semibold">{{ t('auditLogs.drawerTitle') }}</h3>
            <p class="text-xs text-muted-foreground mt-0.5">{{ formatDate(log.created_at) }}</p>
          </div>
          <button class="p-1 rounded-md hover:bg-muted/50 transition-colors" @click="close">
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 overflow-y-auto px-5 py-4 space-y-5">
          <div class="space-y-3">
            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">{{ t('auditLogs.drawerAction') }}</span>
              <span class="inline-block px-2 py-0.5 rounded text-[11px]" :class="actionBadgeClass(log.action)">
                {{ localizeAction(log.action) }}
              </span>
            </div>

            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">{{ t('auditLogs.drawerTargetType') }}</span>
              <span>{{ log.target_type ? localizeTargetType(log.target_type) : '-' }}</span>
            </div>

            <div class="flex items-center justify-between text-xs gap-2">
              <span class="text-muted-foreground shrink-0">{{ t('auditLogs.drawerTargetId') }}</span>
              <div v-if="log.target_id" class="flex items-center gap-1 min-w-0">
                <span class="font-mono text-[11px] truncate">{{ log.target_id }}</span>
                <button class="shrink-0 p-0.5 rounded hover:bg-muted/50 transition-colors" @click.stop="copyText(log.target_id!)">
                  <Copy class="w-3 h-3 text-muted-foreground" />
                </button>
              </div>
              <span v-else>-</span>
            </div>

            <div class="flex items-center justify-between text-xs">
              <span class="text-muted-foreground">{{ t('auditLogs.drawerActor') }}</span>
              <span class="inline-flex items-center gap-1">
                <component :is="log.actor_type === 'agent' ? Bot : UserIcon" class="w-3 h-3 text-muted-foreground" />
                {{ log.actor_name || '-' }}
                <span class="text-[10px] text-muted-foreground px-1 py-0.5 rounded bg-muted/50">
                  {{ log.actor_type === 'agent' ? t('auditLogs.actorTypeAgent') : t('auditLogs.actorTypeUser') }}
                </span>
              </span>
            </div>

            <div v-if="log.actor_id" class="flex items-center justify-between text-xs gap-2">
              <span class="text-muted-foreground shrink-0">{{ t('auditLogs.drawerActorId') }}</span>
              <div class="flex items-center gap-1 min-w-0">
                <span class="font-mono text-[11px] truncate">{{ log.actor_id }}</span>
                <button class="shrink-0 p-0.5 rounded hover:bg-muted/50 transition-colors" @click.stop="copyText(log.actor_id!)">
                  <Copy class="w-3 h-3 text-muted-foreground" />
                </button>
              </div>
            </div>

            <div v-if="log.workspace_id" class="flex items-center justify-between text-xs gap-2">
              <span class="text-muted-foreground shrink-0">{{ t('auditLogs.drawerWorkspaceId') }}</span>
              <div class="flex items-center gap-1 min-w-0">
                <span class="font-mono text-[11px] truncate">{{ log.workspace_id }}</span>
                <button class="shrink-0 p-0.5 rounded hover:bg-muted/50 transition-colors" @click.stop="copyText(log.workspace_id!)">
                  <Copy class="w-3 h-3 text-muted-foreground" />
                </button>
              </div>
            </div>

            <div v-if="log.org_id" class="flex items-center justify-between text-xs gap-2">
              <span class="text-muted-foreground shrink-0">{{ t('auditLogs.drawerOrgId') }}</span>
              <div class="flex items-center gap-1 min-w-0">
                <span class="font-mono text-[11px] truncate">{{ log.org_id }}</span>
                <button class="shrink-0 p-0.5 rounded hover:bg-muted/50 transition-colors" @click.stop="copyText(log.org_id!)">
                  <Copy class="w-3 h-3 text-muted-foreground" />
                </button>
              </div>
            </div>
          </div>

          <!-- Details JSON -->
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-medium">{{ t('auditLogs.drawerDetails') }}</span>
              <button
                v-if="detailsJson"
                class="p-0.5 rounded hover:bg-muted/50 transition-colors"
                @click="copyText(detailsJson!)"
              >
                <Copy class="w-3 h-3 text-muted-foreground" />
              </button>
            </div>
            <div v-if="detailsJson" class="bg-muted/30 border border-border rounded-md p-3 overflow-x-auto">
              <pre class="text-[11px] font-mono text-foreground whitespace-pre-wrap break-all">{{ detailsJson }}</pre>
            </div>
            <p v-else class="text-xs text-muted-foreground">{{ t('auditLogs.drawerNoDetails') }}</p>
          </div>
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
