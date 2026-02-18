<script setup lang="ts">
// AgentHex3D is used declaratively within Workspace3D's scene graph management.
// The actual mesh creation is handled in Workspace3D.vue for performance
// (single scene graph, shared geometry). This component exists for future
// extraction if needed.
defineProps<{
  instanceId: string
  name: string
  displayName: string | null
  status: string
  hexQ: number
  hexR: number
  isHovered: boolean
}>()
</script>

<template>
  <slot />
</template>
