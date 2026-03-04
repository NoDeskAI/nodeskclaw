<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'

export interface SelectOption {
  value: string | null
  label: string
  disabled?: boolean
}

const props = withDefaults(
  defineProps<{
    modelValue: string | null
    options: SelectOption[]
    placeholder?: string
    size?: 'xs' | 'sm'
    disabled?: boolean
    triggerClass?: string
  }>(),
  {
    placeholder: '',
    size: 'sm',
    disabled: false,
    triggerClass: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const open = ref(false)
const highlightIndex = ref(0)
const containerRef = ref<HTMLElement | null>(null)

const enabledOptions = computed(() => props.options.filter(o => !o.disabled))

const currentLabel = computed(() => {
  const match = props.options.find(o => o.value === props.modelValue)
  return match?.label ?? props.placeholder
})

const showPlaceholder = computed(() => {
  return !props.options.some(o => o.value === props.modelValue)
})

function setHighlightFromCurrent() {
  const idx = enabledOptions.value.findIndex(o => o.value === props.modelValue)
  highlightIndex.value = idx >= 0 ? idx : 0
}

watch(() => props.modelValue, () => setHighlightFromCurrent(), { immediate: true })

function closePanel() {
  open.value = false
}

function togglePanel() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) setHighlightFromCurrent()
}

function selectOption(value: string | null) {
  emit('update:modelValue', value)
  closePanel()
}

function onTriggerKeydown(event: KeyboardEvent) {
  if (props.disabled) return

  if (event.key === 'Escape') {
    if (open.value) {
      event.preventDefault()
      closePanel()
    }
    return
  }

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    if (!open.value) {
      open.value = true
      setHighlightFromCurrent()
    } else {
      highlightIndex.value = (highlightIndex.value + 1) % enabledOptions.value.length
    }
    return
  }

  if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) {
      open.value = true
      setHighlightFromCurrent()
    } else {
      highlightIndex.value = (highlightIndex.value - 1 + enabledOptions.value.length) % enabledOptions.value.length
    }
    return
  }

  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (!open.value) {
      open.value = true
      setHighlightFromCurrent()
      return
    }
    const target = enabledOptions.value[highlightIndex.value]
    if (target) selectOption(target.value)
  }
}

function onDocumentMousedown(event: MouseEvent) {
  if (!open.value) return
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    closePanel()
  }
}

onMounted(() => document.addEventListener('mousedown', onDocumentMousedown, true))
onUnmounted(() => document.removeEventListener('mousedown', onDocumentMousedown, true))

const sizeClasses = computed(() => {
  if (props.size === 'xs') return { trigger: 'px-2.5 py-1 text-xs', item: 'px-2.5 py-1 text-xs', check: 'w-3 h-3', chevron: 'w-3 h-3', gap: 'gap-1.5', panel: 'min-w-[7rem]' }
  return { trigger: 'px-3 py-1.5 text-sm', item: 'px-3 py-1.5 text-sm', check: 'w-3.5 h-3.5', chevron: 'w-3.5 h-3.5', gap: 'gap-2', panel: 'min-w-[8rem]' }
})
</script>

<template>
  <div ref="containerRef" class="relative">
    <button
      type="button"
      class="flex items-center rounded-md border border-border bg-card text-foreground transition-all hover:border-primary/40 focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:cursor-not-allowed disabled:opacity-50"
      :class="[
        sizeClasses.trigger,
        sizeClasses.gap,
        open ? 'ring-2 ring-primary/30 border-primary/40' : '',
        triggerClass,
      ]"
      :disabled="disabled"
      aria-haspopup="listbox"
      :aria-expanded="open"
      @click="togglePanel"
      @keydown="onTriggerKeydown"
    >
      <span class="truncate" :class="showPlaceholder ? 'text-muted-foreground' : ''">{{ currentLabel }}</span>
      <ChevronDown
        :class="[sizeClasses.chevron, 'text-muted-foreground shrink-0 transition-transform', open ? 'rotate-180' : '']"
      />
    </button>

    <div
      v-if="open"
      class="absolute left-0 top-full z-50 mt-1 overflow-hidden rounded-md border border-border bg-card shadow-lg"
      :class="sizeClasses.panel"
      role="listbox"
    >
      <button
        v-for="(item, idx) in enabledOptions"
        :key="String(item.value)"
        type="button"
        class="flex w-full items-center text-left transition-colors hover:bg-accent"
        :class="[
          sizeClasses.item,
          sizeClasses.gap,
          highlightIndex === idx ? 'bg-muted/60' : '',
          props.modelValue === item.value ? 'text-primary' : 'text-foreground',
        ]"
        @mouseenter="highlightIndex = idx"
        @click="selectOption(item.value)"
      >
        <Check
          :class="[sizeClasses.check, 'shrink-0', props.modelValue === item.value ? 'opacity-100' : 'opacity-0']"
        />
        <span class="truncate">{{ item.label }}</span>
      </button>
    </div>
  </div>
</template>
