<script setup lang="ts">
// Blackboard3D rendering is managed within Workspace3D's scene graph.
// This component exists as a logical placeholder.
defineProps<{
  autoSummary: string
  manualNotes: string
}>()
</script>

<template>
  <slot />
</template>
