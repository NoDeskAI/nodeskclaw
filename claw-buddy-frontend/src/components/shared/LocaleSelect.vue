<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { Check, Languages } from 'lucide-vue-next'

type LocaleValue = 'zh-CN' | 'en-US'

const props = withDefaults(
  defineProps<{
    modelValue: string
    disabled?: boolean
  }>(),
  {
    disabled: false,
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: LocaleValue]
}>()

const options: Array<{ value: LocaleValue; label: string }> = [
  { value: 'zh-CN', label: '🇨🇳 简体中文' },
  { value: 'en-US', label: '🇺🇸 English' },
]

const open = ref(false)
const highlightIndex = ref(0)
const containerRef = ref<HTMLElement | null>(null)

const currentValue = computed<LocaleValue>(() => (props.modelValue === 'zh-CN' ? 'zh-CN' : 'en-US'))
function setHighlightFromCurrent() {
  const idx = options.findIndex((item) => item.value === currentValue.value)
  highlightIndex.value = idx >= 0 ? idx : 0
}

watch(
  () => props.modelValue,
  () => {
    setHighlightFromCurrent()
  },
  { immediate: true },
)

function closePanel() {
  open.value = false
}

function togglePanel() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value) setHighlightFromCurrent()
}

function selectLocale(value: LocaleValue) {
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
      highlightIndex.value = (highlightIndex.value + 1) % options.length
    }
    return
  }

  if (event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) {
      open.value = true
      setHighlightFromCurrent()
    } else {
      highlightIndex.value = (highlightIndex.value - 1 + options.length) % options.length
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
    const target = options[highlightIndex.value]
    if (target) selectLocale(target.value)
  }
}

function onDocumentMousedown(event: MouseEvent) {
  if (!open.value) return
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    closePanel()
  }
}

onMounted(() => {
  document.addEventListener('mousedown', onDocumentMousedown, true)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocumentMousedown, true)
})
</script>

<template>
  <div ref="containerRef" class="relative">
    <button
      type="button"
      class="h-8 w-8 rounded-md border border-border bg-card flex items-center justify-center text-foreground transition-all hover:border-primary/40 hover:bg-muted/30 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
      :disabled="disabled"
      aria-haspopup="listbox"
      :aria-expanded="open"
      @click="togglePanel"
      @keydown="onTriggerKeydown"
    >
      <Languages class="h-4 w-4 text-muted-foreground" />
    </button>

    <div
      v-if="open"
      class="absolute right-0 top-full z-50 mt-1.5 w-[132px] overflow-hidden rounded-md border border-border bg-card shadow-lg"
      role="listbox"
    >
      <button
        v-for="(item, idx) in options"
        :key="item.value"
        type="button"
        class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors"
        :class="[
          highlightIndex === idx ? 'bg-muted/60' : 'bg-card',
          currentValue === item.value ? 'text-primary' : 'text-foreground',
        ]"
        @mouseenter="highlightIndex = idx"
        @click="selectLocale(item.value)"
      >
        <Check class="h-3.5 w-3.5 shrink-0" :class="currentValue === item.value ? 'opacity-100' : 'opacity-0'" />
        <span class="truncate">{{ item.label }}</span>
      </button>
    </div>
  </div>
</template>
