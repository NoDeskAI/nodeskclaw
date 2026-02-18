<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Plus, Loader2, Palette, Bot } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'

const router = useRouter()
const store = useWorkspaceStore()

const name = ref('')
const description = ref('')
const selectedColor = ref('#a78bfa')
const creating = ref(false)
const error = ref('')

const colors = [
  '#a78bfa', '#60a5fa', '#34d399', '#fbbf24',
  '#f87171', '#f472b6', '#38bdf8', '#a3e635',
]

async function handleCreate() {
  if (!name.value.trim()) {
    error.value = '请输入工作区名称'
    return
  }

  creating.value = true
  error.value = ''

  try {
    const ws = await store.createWorkspace({
      name: name.value.trim(),
      description: description.value.trim(),
      color: selectedColor.value,
    })
    router.push(`/workspace/${ws.id}`)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '创建失败'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="max-w-lg mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-8">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="router.push('/')">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h1 class="text-xl font-bold">新建工作区</h1>
    </div>

    <div class="space-y-6">
      <!-- Name -->
      <div class="space-y-2">
        <label class="text-sm font-medium">工作区名称</label>
        <input
          v-model="name"
          class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50"
          placeholder="如: 客服中心、研发助手"
          maxlength="128"
        />
      </div>

      <!-- Description -->
      <div class="space-y-2">
        <label class="text-sm font-medium">描述</label>
        <textarea
          v-model="description"
          rows="3"
          class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50 resize-none"
          placeholder="简要描述这个工作区的用途..."
        />
      </div>

      <!-- Color -->
      <div class="space-y-2">
        <label class="text-sm font-medium flex items-center gap-1.5">
          <Palette class="w-4 h-4 text-muted-foreground" />
          主题色
        </label>
        <div class="flex gap-2">
          <button
            v-for="c in colors"
            :key="c"
            class="w-8 h-8 rounded-full border-2 transition-all"
            :class="selectedColor === c ? 'border-white scale-110' : 'border-transparent hover:scale-105'"
            :style="{ backgroundColor: c }"
            @click="selectedColor = c"
          />
        </div>
      </div>

      <!-- Preview -->
      <div
        class="rounded-xl border border-border p-4 bg-card"
      >
        <div class="flex items-center gap-3">
          <div
            class="w-10 h-10 rounded-lg flex items-center justify-center text-lg"
            :style="{ backgroundColor: selectedColor + '22', color: selectedColor }"
          >
            🤖
          </div>
          <div>
            <h3 class="font-semibold text-sm">{{ name || '工作区名称' }}</h3>
            <p class="text-xs text-muted-foreground">{{ description || '暂无描述' }}</p>
          </div>
        </div>
      </div>

      <!-- Error -->
      <p v-if="error" class="text-sm text-red-400">{{ error }}</p>

      <!-- Submit -->
      <button
        class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
        :disabled="creating || !name.trim()"
        @click="handleCreate"
      >
        <Loader2 v-if="creating" class="w-4 h-4 animate-spin" />
        <Plus v-else class="w-4 h-4" />
        创建工作区
      </button>
    </div>
  </div>
</template>
