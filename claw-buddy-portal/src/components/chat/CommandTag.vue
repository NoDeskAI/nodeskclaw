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
      v-if="hovered"
      class="tag-icon-btn"
      contenteditable="false"
      @click.stop.prevent="deleteNode"
    >
      <X class="w-2.5 h-2.5" />
    </button>
    <Terminal v-else class="w-3 h-3 shrink-0 opacity-70" />
    <span class="tag-label">/{{ node.attrs.label }}<span v-if="node.attrs.agentLabel" class="agent-part"> @{{ node.attrs.agentLabel }}</span></span>
  </NodeViewWrapper>
</template>

<style scoped>
.command-tag {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  background: hsl(var(--primary) / 0.08);
  color: hsl(var(--primary) / 0.9);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 0.75rem;
  font-weight: 500;
  line-height: 1.4;
  cursor: default;
  user-select: none;
  vertical-align: baseline;
}
.tag-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  cursor: pointer;
  transition: background 0.15s;
}
.tag-icon-btn:hover {
  background: hsl(var(--primary) / 0.15);
}
.tag-label {
  pointer-events: none;
}
.agent-part {
  color: hsl(var(--primary));
  font-weight: 600;
}
</style>
