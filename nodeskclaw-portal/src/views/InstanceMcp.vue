<script setup lang="ts">
import { ref, inject, onMounted, type ComputedRef } from 'vue'
import { Loader2, Plus, Trash2, Wrench, Power, PowerOff } from 'lucide-vue-next'
import api from '@/services/api'
import { useI18n } from 'vue-i18n'
import CustomSelect from '@/components/shared/CustomSelect.vue'

const { t } = useI18n()
const instanceId = inject<ComputedRef<string>>('instanceId')!

interface McpServer {
  id: string
  name: string
  transport: string
  command: string | null
  url: string | null
  args: Record<string, unknown> | null
  env: Record<string, unknown> | null
  is_active: boolean
  source: string
  source_gene_id: string | null
  created_at: string
}

const servers = ref<McpServer[]>([])
const loading = ref(true)
const showAdd = ref(false)

const newName = ref('')
const newTransport = ref<'stdio' | 'sse'>('stdio')
const newCommand = ref('')
const newUrl = ref('')
const adding = ref(false)

async function fetchServers() {
  loading.value = true
  try {
    const res = await api.get(`/instances/${instanceId.value}/mcp-servers`)
    servers.value = res.data.data || []
  } catch (e) {
    console.error('fetchMcpServers error:', e)
  } finally {
    loading.value = false
  }
}

async function addServer() {
  adding.value = true
  try {
    await api.post(`/instances/${instanceId.value}/mcp-servers`, {
      name: newName.value,
      transport: newTransport.value,
      command: newTransport.value === 'stdio' ? newCommand.value : null,
      url: newTransport.value === 'sse' ? newUrl.value : null,
    })
    newName.value = ''
    newCommand.value = ''
    newUrl.value = ''
    showAdd.value = false
    await fetchServers()
  } catch (e) {
    console.error('addMcpServer error:', e)
  } finally {
    adding.value = false
  }
}

async function toggleActive(server: McpServer) {
  try {
    await api.put(`/instances/${instanceId.value}/mcp-servers/${server.id}`, {
      is_active: !server.is_active,
    })
    server.is_active = !server.is_active
  } catch (e) {
    console.error('toggleMcpServer error:', e)
  }
}

async function deleteServer(id: string) {
  try {
    await api.delete(`/instances/${instanceId.value}/mcp-servers/${id}`)
    servers.value = servers.value.filter(s => s.id !== id)
  } catch (e) {
    console.error('deleteMcpServer error:', e)
  }
}

onMounted(fetchServers)
</script>

<template>
  <div>
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <Wrench class="w-4 h-4 text-violet-400" />
          <h2 class="text-sm font-medium">{{ t('common.tools') }}</h2>
          <span class="text-xs text-muted-foreground">({{ servers.length }})</span>
        </div>
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          @click="showAdd = !showAdd"
        >
          <Plus class="w-3.5 h-3.5" />
          {{ t('common.add') }}
        </button>
      </div>

      <!-- Add form -->
      <div v-if="showAdd" class="bg-muted rounded-lg p-4 space-y-3 border border-border">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="text-xs text-muted-foreground mb-1 block">{{ t('common.name') }}</label>
            <input v-model="newName" class="w-full bg-background rounded px-2.5 py-1.5 text-sm outline-none border border-border focus:border-primary" />
          </div>
          <div>
            <label class="text-xs text-muted-foreground mb-1 block">Transport</label>
            <CustomSelect
              v-model="newTransport"
              :options="[{ value: 'stdio', label: 'stdio' }, { value: 'sse', label: 'sse' }]"
              trigger-class="w-full"
            />
          </div>
        </div>
        <div v-if="newTransport === 'stdio'">
          <label class="text-xs text-muted-foreground mb-1 block">Command</label>
          <input v-model="newCommand" class="w-full bg-background rounded px-2.5 py-1.5 text-sm outline-none border border-border" placeholder="npx -y @modelcontextprotocol/server-..." />
        </div>
        <div v-else>
          <label class="text-xs text-muted-foreground mb-1 block">URL</label>
          <input v-model="newUrl" class="w-full bg-background rounded px-2.5 py-1.5 text-sm outline-none border border-border" placeholder="http://localhost:3001/sse" />
        </div>
        <div class="flex justify-end gap-2">
          <button class="px-3 py-1.5 text-xs rounded bg-muted hover:bg-background transition-colors" @click="showAdd = false">
            {{ t('common.cancel') }}
          </button>
          <button
            class="px-3 py-1.5 text-xs rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            :disabled="!newName || adding"
            @click="addServer"
          >
            <Loader2 v-if="adding" class="w-3 h-3 animate-spin inline mr-1" />
            {{ t('common.save') }}
          </button>
        </div>
      </div>

      <!-- Server list -->
      <div v-if="!servers.length && !showAdd" class="text-sm text-muted-foreground text-center py-8">
        {{ t('common.noData') }}
      </div>

      <div v-for="server in servers" :key="server.id" class="bg-muted rounded-lg p-3 flex items-center gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium truncate">{{ server.name }}</span>
            <span class="text-[10px] px-1.5 py-0.5 rounded bg-background text-muted-foreground">{{ server.transport }}</span>
            <span v-if="server.source === 'gene'" class="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-400">gene</span>
          </div>
          <div class="text-xs text-muted-foreground truncate mt-0.5">
            {{ server.transport === 'stdio' ? server.command : server.url }}
          </div>
        </div>
        <button
          class="p-1.5 rounded hover:bg-background transition-colors"
          :class="server.is_active ? 'text-green-400' : 'text-muted-foreground'"
          @click="toggleActive(server)"
        >
          <Power v-if="server.is_active" class="w-4 h-4" />
          <PowerOff v-else class="w-4 h-4" />
        </button>
        <button
          v-if="server.source !== 'gene'"
          class="p-1.5 rounded hover:bg-background text-muted-foreground hover:text-red-400 transition-colors"
          @click="deleteServer(server.id)"
        >
          <Trash2 class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
