<script setup lang="ts">
import { ref } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'
import { Terminal, X } from 'lucide-vue-next'

defineProps<{
  node: any
  deleteNode: () => void
}>()

const hovered = ref(false)
</script>

<template>
  <NodeViewWrapper
    as="span"
    class="command-tag"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
    <button
      class="tag-icon-btn"
      contenteditable="false"
      @click.stop.prevent="deleteNode"
    >
      <X class="tag-icon-x" :class="{ visible: hovered }" />
      <Terminal class="tag-icon-default" :class="{ visible: !hovered }" />
    </button>
    <span class="tag-label">/{{ node.attrs.label }}<span v-if="node.attrs.agentLabel" class="agent-part">{{ node.attrs.agentLabel }}</span></span>
  </NodeViewWrapper>
</template>

<style scoped>
.command-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: color-mix(in srgb, var(--primary) 20%, var(--muted));
  color: color-mix(in srgb, var(--primary) 90%, white);
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
.tag-icon-default {
  position: absolute;
  transition: opacity 0.12s;
  opacity: 0;
  pointer-events: none;
}
.tag-icon-x {
  width: 10px;
  height: 10px;
}
.tag-icon-default {
  width: 12px;
  height: 12px;
}
.tag-icon-x.visible {
  opacity: 1;
}
.tag-icon-default.visible {
  opacity: 0.7;
}
.tag-label {
  pointer-events: none;
}
.agent-part {
  margin-left: 4px;
  color: var(--primary);
  font-weight: 600;
}
</style>
