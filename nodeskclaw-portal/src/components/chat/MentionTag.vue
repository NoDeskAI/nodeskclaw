<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'
import { Bot, X } from 'lucide-vue-next'

const props = defineProps<{
  node: any
  deleteNode: () => void
}>()

const hovered = ref(false)
const popoverVisible = ref(false)
const popoverPos = ref({ x: 0, y: 0 })
let hoverTimer: ReturnType<typeof setTimeout> | null = null

function onEnter(e: MouseEvent) {
  hovered.value = true
  hoverTimer = setTimeout(() => {
    const el = e.currentTarget as HTMLElement
    if (!el) return
    const rect = el.getBoundingClientRect()
    popoverPos.value = { x: rect.left, y: rect.top - 4 }
    popoverVisible.value = true
  }, 400)
}

function onLeave() {
  hovered.value = false
  popoverVisible.value = false
  if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null }
}

onUnmounted(() => {
  if (hoverTimer) clearTimeout(hoverTimer)
})
</script>

<template>
  <NodeViewWrapper
    as="span"
    class="mention-tag"
    @mouseenter="onEnter"
    @mouseleave="onLeave"
  >
    <button
      class="tag-icon-btn"
      contenteditable="false"
      @click.stop.prevent="deleteNode"
    >
      <X class="tag-icon-x" :class="{ visible: hovered }" />
      <Bot class="tag-icon-bot" :class="{ visible: !hovered }" />
    </button>
    <span class="tag-label">{{ node.attrs.label }}</span>

    <Teleport to="body">
      <div
        v-if="popoverVisible && node.attrs.status"
        class="mention-popover"
        :style="{ left: popoverPos.x + 'px', top: popoverPos.y + 'px' }"
      >
        <div class="font-medium text-foreground text-xs">{{ node.attrs.label }}</div>
        <div v-if="node.attrs.slug" class="text-muted-foreground font-mono mt-0.5" style="font-size:10px">{{ node.attrs.slug }}</div>
        <div class="mt-0.5 flex items-center gap-1" style="font-size:10px">
          <span
            class="inline-block w-1.5 h-1.5 rounded-full"
            :class="node.attrs.status === 'running' ? 'bg-green-500' : 'bg-orange-400'"
          />
          <span class="text-muted-foreground">{{ node.attrs.status }}</span>
        </div>
      </div>
    </Teleport>
  </NodeViewWrapper>
</template>

<style scoped>
.mention-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: color-mix(in srgb, var(--primary) 20%, var(--muted));
  color: var(--primary);
  border-radius: 4px;
  padding: 0 4px;
  font-size: 0.7rem;
  font-weight: 500;
  line-height: 1.3;
  cursor: default;
  user-select: none;
  vertical-align: middle;
}
.tag-icon-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  cursor: pointer;
  flex-shrink: 0;
}
.tag-icon-btn:hover {
  background: color-mix(in srgb, var(--primary) 20%, transparent);
}
.tag-icon-x,
.tag-icon-bot {
  position: absolute;
  transition: opacity 0.12s;
  opacity: 0;
  pointer-events: none;
}
.tag-icon-x {
  width: 10px;
  height: 10px;
}
.tag-icon-bot {
  width: 12px;
  height: 12px;
}
.tag-icon-x.visible {
  opacity: 1;
}
.tag-icon-bot.visible {
  opacity: 0.7;
}
.tag-label {
  pointer-events: none;
}
.mention-popover {
  position: fixed;
  z-index: 9999;
  transform: translateY(-100%);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgb(0 0 0 / 0.12);
  padding: 6px 10px;
  white-space: nowrap;
  pointer-events: none;
}
</style>
