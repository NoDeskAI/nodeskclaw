<script setup lang="ts">
import { computed } from 'vue'
import { FilePlus2, Code2, PenTool, Microscope, LayoutTemplate, Building2 } from 'lucide-vue-next'
import type { WorkspaceTemplateItem } from '@/stores/workspace'

const props = defineProps<{
  template?: WorkspaceTemplateItem
  blank?: boolean
  selected?: boolean
}>()

defineEmits<{
  select: []
}>()

const iconComponent = computed(() => {
  if (props.blank) return FilePlus2
  if (!props.template) return LayoutTemplate
  if (props.template.visibility === 'org_private') return Building2
  const name = props.template.name
  if (name.includes('研发') || name.includes('Software')) return Code2
  if (name.includes('内容') || name.includes('Content')) return PenTool
  if (name.includes('研究') || name.includes('Research')) return Microscope
  return LayoutTemplate
})

const agentCount = computed(() => {
  if (props.blank || !props.template) return 0
  if (props.template.agent_count != null) return props.template.agent_count
  const topo = (props.template as { topology_snapshot?: { nodes?: { node_type?: string }[] } }).topology_snapshot
  if (!topo?.nodes) return 0
  return topo.nodes.filter((n) => n.node_type === 'agent').length
})

const humanCount = computed(() => {
  if (props.blank || !props.template) return 0
  return props.template.human_count ?? 0
})
</script>

<template>
  <button
    class="group relative flex flex-col items-center gap-2 p-4 rounded-xl border-2 transition-all text-center min-h-[120px] justify-center"
    :class="[
      selected
        ? 'border-primary bg-primary/5'
        : 'border-border hover:border-primary/40 hover:bg-muted/50',
    ]"
    @click="$emit('select')"
  >
    <component :is="iconComponent" class="w-7 h-7 text-muted-foreground group-hover:text-primary transition-colors" :class="{ 'text-primary': selected }" />
    <span class="text-sm font-medium leading-tight">
      {{ blank ? $t('createWorkspace.blankTemplate') : template?.name }}
    </span>
    <span v-if="!blank" class="text-xs text-muted-foreground">
      {{ $t('createWorkspace.agentSlots', { count: agentCount }) }}
    </span>
    <span v-if="!blank && humanCount > 0" class="text-xs text-muted-foreground">
      {{ $t('createWorkspace.humanSlots', { count: humanCount }) }}
    </span>
    <span
      v-if="template?.visibility === 'org_private'"
      class="absolute top-1.5 right-1.5 text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
    >
      {{ $t('createWorkspace.orgPrivate') }}
    </span>
  </button>
</template>
