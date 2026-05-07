<script lang="ts">
export type Protocol = 'https://' | 'http://'

export function stripProtocol(url: string): string {
  return url.replace(/^https?:\/\//, '')
}
</script>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { ChevronDown, X } from 'lucide-vue-next'

const props = withDefaults(
  defineProps<{
    modelValue: string
    placeholder?: string
    showClear?: boolean
    inputClass?: string
  }>(),
  {
    placeholder: '',
    showClear: false,
    inputClass: '',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'clear': []
  'input': []
}>()

const protocol = ref<Protocol>('https://')
const host = ref('')
const dropdownOpen = ref(false)
const containerRef = ref<HTMLElement | null>(null)

function splitUrl(url: string): { protocol: Protocol; host: string } {
  if (url.startsWith('http://')) return { protocol: 'http://', host: url.slice(7) }
  if (url.startsWith('https://')) return { protocol: 'https://', host: url.slice(8) }
  return { protocol: 'https://', host: url }
}

function emitJoined() {
  const value = host.value ? `${protocol.value}${host.value}` : ''
  emit('update:modelValue', value)
  emit('input')
}

watch(
  () => props.modelValue,
  (newVal) => {
    const parts = splitUrl(newVal || '')
    const joined = parts.host ? `${parts.protocol}${parts.host}` : ''
    const current = host.value ? `${protocol.value}${host.value}` : ''
    if (joined !== current) {
      protocol.value = parts.protocol
      host.value = parts.host
    }
  },
  { immediate: true },
)

function onHostInput() {
  emitJoined()
}

function selectProtocol(p: Protocol) {
  protocol.value = p
  dropdownOpen.value = false
  if (host.value) emitJoined()
}

function onPaste(e: ClipboardEvent) {
  const text = e.clipboardData?.getData('text') ?? ''
  if (text.startsWith('http://') || text.startsWith('https://')) {
    e.preventDefault()
    const parts = splitUrl(text)
    protocol.value = parts.protocol
    host.value = parts.host
    emitJoined()
  }
}

function onClear() {
  host.value = ''
  protocol.value = 'https://'
  emit('update:modelValue', '')
  emit('clear')
}

function onDocumentMousedown(event: MouseEvent) {
  if (!dropdownOpen.value) return
  if (containerRef.value && !containerRef.value.contains(event.target as Node)) {
    dropdownOpen.value = false
  }
}

onMounted(() => document.addEventListener('mousedown', onDocumentMousedown, true))
onUnmounted(() => document.removeEventListener('mousedown', onDocumentMousedown, true))
</script>

<template>
  <div class="flex relative" ref="containerRef">
    <button
      type="button"
      class="flex items-center gap-0.5 px-2 py-1.5 border border-r-0 border-border bg-muted/50 rounded-l-md text-xs font-mono text-muted-foreground hover:text-foreground transition-colors shrink-0"
      @click="dropdownOpen = !dropdownOpen"
    >
      {{ protocol }}
      <ChevronDown
        class="w-3 h-3 transition-transform"
        :class="dropdownOpen ? 'rotate-180' : ''"
      />
    </button>

    <div
      v-if="dropdownOpen"
      class="absolute left-0 top-full z-50 mt-1 rounded-md border border-border bg-card shadow-lg overflow-hidden"
    >
      <button
        v-for="p in (['https://', 'http://'] as Protocol[])"
        :key="p"
        type="button"
        class="flex w-full items-center px-3 py-1.5 text-xs font-mono transition-colors hover:bg-accent"
        :class="protocol === p ? 'text-primary' : 'text-foreground'"
        @click="selectProtocol(p)"
      >
        {{ p }}
      </button>
    </div>

    <input
      :value="host"
      type="text"
      :placeholder="placeholder"
      :class="[showClear ? 'pr-8' : 'pr-3', inputClass]"
      class="flex-1 min-w-0 pl-3 py-1.5 border border-border bg-background rounded-r-md text-sm font-mono focus:outline-none focus:ring-1 focus:ring-primary/50"
      @input="host = ($event.target as HTMLInputElement).value; onHostInput()"
      @paste="onPaste"
    />

    <button
      v-if="showClear"
      type="button"
      class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
      @click="onClear"
    >
      <X class="w-3.5 h-3.5" />
    </button>
  </div>
</template>
