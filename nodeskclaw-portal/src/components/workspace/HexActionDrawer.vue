<script setup lang="ts">
import { watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, Plus, MessageSquare, ExternalLink, Trash2, Eye, Route, User, Palette, Move, PenSquare, Crosshair, GitBranch } from 'lucide-vue-next'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  open: boolean
  hexType: 'empty' | 'agent' | 'blackboard' | 'corridor' | 'human'
  hexPosition: { q: number, r: number }
  agentInfo?: { id: string, name: string }
  entityInfo?: { id: string, name?: string }
  chatSidebarOpen?: boolean
  chatSidebarWidth?: number
}>(), { chatSidebarWidth: 400 })

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'action', name: string): void
}>()

const SHORTCUT_MAP: Record<string, Record<string, string>> = {
  empty: { a: 'add-agent', c: 'place-corridor', h: 'place-human' },
  agent: { f: 'focus-hex', c: 'open-chat', d: 'view-detail', l: 'view-collaboration', r: 'rename-agent', p: 'change-agent-color', m: 'move-hex', Delete: 'remove-agent', Backspace: 'remove-agent' },
  corridor: { f: 'focus-hex', r: 'rename-corridor', m: 'move-hex', Delete: 'remove-corridor', Backspace: 'remove-corridor' },
  human: { f: 'focus-hex', r: 'rename-human', p: 'change-color', m: 'move-hex', Delete: 'remove-human', Backspace: 'remove-human' },
  blackboard: { f: 'focus-hex', e: 'view-blackboard' },
}

function onKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || (e.target as HTMLElement)?.isContentEditable) return

  const map = SHORTCUT_MAP[props.hexType]
  if (!map) return

  const action = map[e.key] || map[e.key.toLowerCase()]
  if (action) {
    e.preventDefault()
    e.stopPropagation()
    emit('action', action)
  }
}

watch(() => props.open, (open) => {
  if (open) {
    window.addEventListener('keydown', onKeydown)
  } else {
    window.removeEventListener('keydown', onKeydown)
  }
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <Transition name="slide-up">
    <div
      v-if="open"
      class="fixed bottom-0 -translate-x-1/2 z-40 w-60 bg-card border border-border shadow-2xl rounded-t-xl transition-[left] duration-300"
      :style="{ left: chatSidebarOpen ? `calc(50% - ${chatSidebarWidth / 2}px)` : '50%' }"
    >
      <div class="flex items-center justify-between px-4 py-2.5 border-b border-border/50">
        <span class="text-sm font-medium text-foreground">
          <template v-if="hexType === 'empty'">
            {{ t('hexAction.emptySlot') }}
          </template>
          <template v-else-if="hexType === 'agent'">
            {{ agentInfo?.name || 'Agent' }}
          </template>
          <template v-else-if="hexType === 'corridor'">
            {{ entityInfo?.name || t('hexAction.corridor') }}
          </template>
          <template v-else-if="hexType === 'human'">
            {{ entityInfo?.name || t('hexAction.humanHex') }}
          </template>
          <template v-else>
            {{ t('hexAction.centralBlackboard') }}
          </template>
        </span>
        <button
          class="p-1 rounded hover:bg-muted transition-colors"
          @click="emit('close')"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <div class="flex flex-col gap-0.5 px-2 py-2">
        <!-- Empty hex actions -->
        <template v-if="hexType === 'empty'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'add-agent')"
          >
            <Plus class="w-4 h-4 text-primary" />
            <span>{{ t('hexAction.addAgentHere') }}</span>
            <kbd class="kbd-hint">A</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'place-corridor')"
          >
            <Route class="w-4 h-4 text-cyan-400" />
            <span>{{ t('hexAction.placeCorridor') }}</span>
            <kbd class="kbd-hint">C</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'place-human')"
          >
            <User class="w-4 h-4 text-amber-400" />
            <span>{{ t('hexAction.placeHuman') }}</span>
            <kbd class="kbd-hint">H</kbd>
          </button>
        </template>

        <!-- Agent hex actions -->
        <template v-else-if="hexType === 'agent'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'focus-hex')"
          >
            <Crosshair class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.focusHex') }}</span>
            <kbd class="kbd-hint">F</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'open-chat')"
          >
            <MessageSquare class="w-4 h-4 text-primary" />
            <span>{{ t('hexAction.openChat') }}</span>
            <kbd class="kbd-hint">C</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'view-detail')"
          >
            <ExternalLink class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.viewDetail') }}</span>
            <kbd class="kbd-hint">D</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'view-collaboration')"
          >
            <GitBranch class="w-4 h-4 text-violet-400" />
            <span>{{ t('hexAction.viewCollaboration') }}</span>
            <kbd class="kbd-hint">L</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'rename-agent')"
          >
            <PenSquare class="w-4 h-4 text-cyan-400" />
            <span>{{ t('hexAction.renameAgent') }}</span>
            <kbd class="kbd-hint">R</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'change-agent-color')"
          >
            <Palette class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.changeAgentColor') }}</span>
            <kbd class="kbd-hint">P</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'move-hex')"
          >
            <Move class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.move') }}</span>
            <kbd class="kbd-hint">M</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors text-sm"
            @click="emit('action', 'remove-agent')"
          >
            <Trash2 class="w-4 h-4" />
            <span>{{ t('hexAction.remove') }}</span>
            <kbd class="kbd-hint">Del</kbd>
          </button>
        </template>

        <!-- Corridor hex actions -->
        <template v-else-if="hexType === 'corridor'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'focus-hex')"
          >
            <Crosshair class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.focusHex') }}</span>
            <kbd class="kbd-hint">F</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'rename-corridor')"
          >
            <PenSquare class="w-4 h-4 text-cyan-400" />
            <span>{{ t('hexAction.renameCorridor') }}</span>
            <kbd class="kbd-hint">R</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'move-hex')"
          >
            <Move class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.move') }}</span>
            <kbd class="kbd-hint">M</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors text-sm"
            @click="emit('action', 'remove-corridor')"
          >
            <Trash2 class="w-4 h-4" />
            <span>{{ t('hexAction.remove') }}</span>
            <kbd class="kbd-hint">Del</kbd>
          </button>
        </template>

        <!-- Human hex actions -->
        <template v-else-if="hexType === 'human'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'focus-hex')"
          >
            <Crosshair class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.focusHex') }}</span>
            <kbd class="kbd-hint">F</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'rename-human')"
          >
            <PenSquare class="w-4 h-4 text-amber-400" />
            <span>{{ t('hexAction.renameHuman') }}</span>
            <kbd class="kbd-hint">R</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'change-color')"
          >
            <Palette class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.changeColor') }}</span>
            <kbd class="kbd-hint">P</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'move-hex')"
          >
            <Move class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.move') }}</span>
            <kbd class="kbd-hint">M</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors text-sm"
            @click="emit('action', 'remove-human')"
          >
            <Trash2 class="w-4 h-4" />
            <span>{{ t('hexAction.remove') }}</span>
            <kbd class="kbd-hint">Del</kbd>
          </button>
        </template>

        <!-- Blackboard actions -->
        <template v-else>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'focus-hex')"
          >
            <Crosshair class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.focusHex') }}</span>
            <kbd class="kbd-hint">F</kbd>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'view-blackboard')"
          >
            <Eye class="w-4 h-4 text-primary" />
            <span>{{ t('hexAction.viewBlackboard') }}</span>
            <kbd class="kbd-hint">E</kbd>
          </button>
        </template>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active {
  transition: transform 0.25s ease;
}
.slide-up-enter-from, .slide-up-leave-to {
  transform: translateY(100%);
}
.kbd-hint {
  margin-left: auto;
  font-size: 11px;
  line-height: 1;
  padding: 2px 5px;
  border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border: 1px solid hsl(var(--border));
}
</style>
