<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useConfirmState } from '@/composables/useConfirm'
import { TriangleAlert } from 'lucide-vue-next'

const { t } = useI18n()
const { state, handleConfirm, handleCancel } = useConfirmState()

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') handleCancel()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="state.visible"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="handleCancel"
      @keydown="onKeydown"
    >
      <div
        class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-sm p-6 space-y-4"
        tabindex="-1"
        @vue:mounted="($event: any) => $event.el?.focus()"
      >
        <div v-if="state.title" class="flex items-center gap-2">
          <TriangleAlert
            v-if="state.variant === 'danger'"
            class="w-5 h-5 text-red-400 shrink-0"
          />
          <h3 class="font-semibold text-base">{{ state.title }}</h3>
        </div>

        <p class="text-sm text-muted-foreground leading-relaxed">
          {{ state.description }}
        </p>

        <div class="flex justify-end gap-2 pt-1">
          <button
            v-if="!state.isAlert"
            class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-accent transition-colors"
            @click="handleCancel"
          >
            {{ state.cancelText || t('common.cancel') }}
          </button>
          <button
            :class="[
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              state.variant === 'danger'
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-primary text-primary-foreground hover:bg-primary/90',
            ]"
            @click="handleConfirm"
          >
            {{ state.confirmText || t('common.confirm') }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
