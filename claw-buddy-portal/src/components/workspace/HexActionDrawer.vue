<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { X, Plus, MessageSquare, ExternalLink, Trash2, PenSquare, Route, User, Palette, Settings, Link, Move } from 'lucide-vue-next'

const { t } = useI18n()

defineProps<{
  open: boolean
  hexType: 'empty' | 'agent' | 'blackboard' | 'corridor' | 'human'
  hexPosition: { q: number, r: number }
  agentInfo?: { id: string, name: string }
  entityInfo?: { id: string, name?: string }
  chatSidebarOpen?: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'action', name: string): void
}>()
</script>

<template>
  <Transition name="slide-up">
    <div
      v-if="open"
      class="fixed bottom-0 -translate-x-1/2 z-40 w-60 bg-card border border-border shadow-2xl rounded-t-xl transition-[left] duration-300"
      :style="{ left: chatSidebarOpen ? 'calc(50% - 200px)' : '50%' }"
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
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'place-corridor')"
          >
            <Route class="w-4 h-4 text-cyan-400" />
            <span>{{ t('hexAction.placeCorridor') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'place-human')"
          >
            <User class="w-4 h-4 text-amber-400" />
            <span>{{ t('hexAction.placeHuman') }}</span>
          </button>
        </template>

        <!-- Agent hex actions -->
        <template v-else-if="hexType === 'agent'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'open-chat')"
          >
            <MessageSquare class="w-4 h-4 text-primary" />
            <span>{{ t('hexAction.openChat') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'view-detail')"
          >
            <ExternalLink class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.viewDetail') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'move-hex')"
          >
            <Move class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.move') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors text-sm"
            @click="emit('action', 'remove-agent')"
          >
            <Trash2 class="w-4 h-4" />
            <span>{{ t('hexAction.remove') }}</span>
          </button>
        </template>

        <!-- Corridor hex actions -->
        <template v-else-if="hexType === 'corridor'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'rename-corridor')"
          >
            <PenSquare class="w-4 h-4 text-cyan-400" />
            <span>{{ t('hexAction.renameCorridor') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'manage-connections')"
          >
            <Link class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.manageConnections') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'move-hex')"
          >
            <Move class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.move') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors text-sm"
            @click="emit('action', 'remove-corridor')"
          >
            <Trash2 class="w-4 h-4" />
            <span>{{ t('hexAction.remove') }}</span>
          </button>
        </template>

        <!-- Human hex actions -->
        <template v-else-if="hexType === 'human'">
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'view-channel')"
          >
            <Settings class="w-4 h-4 text-amber-400" />
            <span>{{ t('hexAction.viewChannel') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'change-color')"
          >
            <Palette class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.changeColor') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'move-hex')"
          >
            <Move class="w-4 h-4 text-muted-foreground" />
            <span>{{ t('hexAction.move') }}</span>
          </button>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-destructive/10 text-destructive transition-colors text-sm"
            @click="emit('action', 'remove-human')"
          >
            <Trash2 class="w-4 h-4" />
            <span>{{ t('hexAction.remove') }}</span>
          </button>
        </template>

        <!-- Blackboard actions -->
        <template v-else>
          <button
            class="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-muted transition-colors text-sm"
            @click="emit('action', 'edit-blackboard')"
          >
            <PenSquare class="w-4 h-4 text-primary" />
            <span>{{ t('hexAction.editBlackboard') }}</span>
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
</style>
