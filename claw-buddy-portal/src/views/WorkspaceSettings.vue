<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Save, Trash2, Loader2, Users, Palette } from 'lucide-vue-next'
import { useWorkspaceStore } from '@/stores/workspace'

const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()

const workspaceId = computed(() => route.params.id as string)

const name = ref('')
const description = ref('')
const color = ref('#a78bfa')
const saving = ref(false)
const deleting = ref(false)

const colors = [
  '#a78bfa', '#60a5fa', '#34d399', '#fbbf24',
  '#f87171', '#f472b6', '#38bdf8', '#a3e635',
]

onMounted(async () => {
  await store.fetchWorkspace(workspaceId.value)
  await store.fetchMembers(workspaceId.value)
  if (store.currentWorkspace) {
    name.value = store.currentWorkspace.name
    description.value = store.currentWorkspace.description
    color.value = store.currentWorkspace.color
  }
})

async function handleSave() {
  saving.value = true
  try {
    await store.updateWorkspace(workspaceId.value, {
      name: name.value.trim(),
      description: description.value.trim(),
      color: color.value,
    })
  } catch (e) {
    console.error('save error:', e)
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!confirm('确认删除该工作区？此操作不可撤销。')) return
  deleting.value = true
  try {
    await store.deleteWorkspace(workspaceId.value)
    router.push('/')
  } catch (e: any) {
    alert(e?.response?.data?.detail || '删除失败')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="max-w-lg mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-8">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="router.push(`/workspace/${workspaceId}`)">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h1 class="text-xl font-bold">工作区设置</h1>
    </div>

    <div class="space-y-6">
      <div class="space-y-2">
        <label class="text-sm font-medium">名称</label>
        <input
          v-model="name"
          class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50"
        />
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">描述</label>
        <textarea
          v-model="description"
          rows="3"
          class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50 resize-none"
        />
      </div>

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
            :class="color === c ? 'border-white scale-110' : 'border-transparent hover:scale-105'"
            :style="{ backgroundColor: c }"
            @click="color = c"
          />
        </div>
      </div>

      <!-- Members -->
      <div class="space-y-3">
        <h3 class="text-sm font-medium flex items-center gap-1.5">
          <Users class="w-4 h-4 text-muted-foreground" />
          成员 ({{ store.members.length }})
        </h3>
        <div class="space-y-2">
          <div
            v-for="m in store.members"
            :key="m.user_id"
            class="flex items-center gap-3 py-2 px-3 rounded-lg bg-muted"
          >
            <div class="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center text-xs font-medium">
              {{ m.user_name?.[0] || '?' }}
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm font-medium truncate">{{ m.user_name }}</p>
              <p class="text-xs text-muted-foreground">{{ m.role }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="flex gap-3">
        <button
          class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          :disabled="saving"
          @click="handleSave"
        >
          <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
          <Save v-else class="w-4 h-4" />
          保存
        </button>
        <button
          class="px-4 py-2.5 rounded-lg border border-destructive text-destructive text-sm font-medium hover:bg-destructive/10 transition-colors disabled:opacity-50"
          :disabled="deleting"
          @click="handleDelete"
        >
          <Loader2 v-if="deleting" class="w-4 h-4 animate-spin" />
          <Trash2 v-else class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
