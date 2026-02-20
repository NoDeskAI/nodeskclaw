<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Search, X, ChevronDown, Loader2, RefreshCw, Check } from 'lucide-vue-next'

export interface ModelItem {
  id: string
  name: string
  context_window?: number | null
  max_tokens?: number | null
}

const props = defineProps<{
  provider: string
  modelValue: ModelItem[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: ModelItem[]]
  'fetch-models': [provider: string, callback: (models: ModelItem[]) => void]
}>()

const open = ref(false)
const search = ref('')
const loading = ref(false)
const availableModels = ref<ModelItem[]>([])
const containerRef = ref<HTMLDivElement>()

const selectedIds = computed(() => new Set(props.modelValue.map(m => m.id)))

const filtered = computed(() => {
  if (!search.value) return availableModels.value
  const q = search.value.toLowerCase()
  return availableModels.value.filter(m =>
    m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)
  )
})

function toggle(model: ModelItem) {
  if (selectedIds.value.has(model.id)) {
    emit('update:modelValue', props.modelValue.filter(m => m.id !== model.id))
  } else {
    emit('update:modelValue', [...props.modelValue, model])
  }
}

function remove(id: string) {
  emit('update:modelValue', props.modelValue.filter(m => m.id !== id))
}

function loadModels() {
  loading.value = true
  emit('fetch-models', props.provider, (models: ModelItem[]) => {
    availableModels.value = models
    loading.value = false
  })
}

function handleOpen() {
  if (props.disabled) return
  open.value = !open.value
  if (open.value && availableModels.value.length === 0) {
    loadModels()
  }
}

function onClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside, true))
onUnmounted(() => document.removeEventListener('click', onClickOutside, true))

watch(() => props.provider, () => {
  availableModels.value = []
  search.value = ''
})
</script>

<template>
  <div ref="containerRef" class="relative">
    <label class="text-xs text-muted-foreground mb-1 block">
      可用模型
      <span v-if="modelValue.length > 0" class="text-foreground font-medium ml-1">{{ modelValue.length }} 个已选</span>
    </label>

    <!-- Selected tags + trigger -->
    <div
      class="min-h-[38px] flex flex-wrap items-center gap-1.5 px-3 py-1.5 rounded-lg border bg-card text-sm cursor-pointer transition-colors"
      :class="[
        disabled ? 'opacity-50 cursor-not-allowed border-border' : 'hover:border-primary/50 border-border',
        open ? 'ring-2 ring-primary/50 border-primary' : ''
      ]"
      @click="handleOpen"
    >
      <span
        v-for="m in modelValue"
        :key="m.id"
        class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-mono"
      >
        {{ m.id }}
        <button
          class="hover:text-destructive transition-colors"
          @click.stop="remove(m.id)"
        >
          <X class="w-3 h-3" />
        </button>
      </span>
      <span v-if="modelValue.length === 0" class="text-muted-foreground text-sm">
        点击选择模型...
      </span>
      <ChevronDown class="w-4 h-4 text-muted-foreground ml-auto shrink-0 transition-transform" :class="open ? 'rotate-180' : ''" />
    </div>

    <!-- Dropdown -->
    <div
      v-if="open"
      class="absolute z-20 mt-1 w-full rounded-lg border border-border bg-card shadow-lg overflow-hidden"
    >
      <!-- Search input -->
      <div class="flex items-center gap-2 px-3 py-2 border-b border-border">
        <Search class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
        <input
          v-model="search"
          type="text"
          placeholder="搜索模型..."
          class="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          @click.stop
        />
        <button
          class="text-muted-foreground hover:text-foreground transition-colors"
          title="重新拉取"
          @click.stop="loadModels"
        >
          <RefreshCw class="w-3.5 h-3.5" :class="loading ? 'animate-spin' : ''" />
        </button>
      </div>

      <!-- Model list -->
      <div class="max-h-60 overflow-y-auto">
        <div v-if="loading" class="flex items-center justify-center py-6">
          <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
        </div>
        <div v-else-if="filtered.length === 0" class="py-4 text-center text-xs text-muted-foreground">
          {{ search ? '无匹配模型' : '暂无可用模型' }}
        </div>
        <button
          v-else
          v-for="m in filtered"
          :key="m.id"
          class="w-full flex items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent transition-colors"
          @click.stop="toggle(m)"
        >
          <div
            class="w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors"
            :class="selectedIds.has(m.id) ? 'bg-primary border-primary' : 'border-muted-foreground/40'"
          >
            <Check v-if="selectedIds.has(m.id)" class="w-3 h-3 text-primary-foreground" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="font-mono text-xs truncate">{{ m.id }}</div>
            <div v-if="m.name !== m.id" class="text-[10px] text-muted-foreground truncate">{{ m.name }}</div>
          </div>
          <span v-if="m.context_window" class="text-[10px] text-muted-foreground shrink-0">
            {{ (m.context_window / 1000).toFixed(0) }}k ctx
          </span>
        </button>
      </div>
    </div>
  </div>
</template>
