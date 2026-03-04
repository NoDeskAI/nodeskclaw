<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useOrgStore } from '@/stores/org'
import {
  Plus,
  Trash2,
  Loader2,
  Search,
  X,
  Dna,
  FlaskConical,
} from 'lucide-vue-next'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import { resolveApiErrorMessage } from '@/i18n/error'

const { t } = useI18n()
const orgStore = useOrgStore()
const toast = useToast()
const { confirm } = useConfirm()

interface RequiredGeneItem {
  id: string
  gene_id: string
  gene_name: string
  gene_slug: string
  gene_short_description: string | null
  gene_icon: string | null
  gene_category: string | null
}

interface GeneSearchResult {
  id: string
  name: string
  slug: string
  short_description?: string
  category?: string
  icon?: string
}

const loading = ref(true)
const requiredGenes = ref<RequiredGeneItem[]>([])
const actionLoading = ref<string | null>(null)

const showAddDialog = ref(false)
const searchQuery = ref('')
const searchResults = ref<GeneSearchResult[]>([])
const searching = ref(false)
const addingGeneId = ref<string | null>(null)

let searchTimer: ReturnType<typeof setTimeout> | null = null

const orgId = computed(() => orgStore.currentOrgId)

const existingSlugs = computed(() => new Set(requiredGenes.value.map(g => g.gene_slug)))

async function fetchRequiredGenes() {
  if (!orgId.value) return
  loading.value = true
  try {
    const res = await api.get(`/orgs/${orgId.value}/required-genes`)
    requiredGenes.value = res.data.data ?? []
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e))
  } finally {
    loading.value = false
  }
}

async function fetchInitialGenes() {
  searching.value = true
  try {
    const res = await api.get('/genes', {
      params: { page: 1, page_size: 20 },
    })
    searchResults.value = (res.data.data ?? []).filter(
      (g: GeneSearchResult) => !existingSlugs.value.has(g.slug),
    )
  } catch {
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

async function searchGenes() {
  if (!searchQuery.value.trim()) {
    await fetchInitialGenes()
    return
  }
  searching.value = true
  try {
    const res = await api.get('/genes', {
      params: { keyword: searchQuery.value, page: 1, page_size: 20 },
    })
    searchResults.value = (res.data.data ?? []).filter(
      (g: GeneSearchResult) => !existingSlugs.value.has(g.slug),
    )
  } catch {
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) {
    fetchInitialGenes()
    return
  }
  searchTimer = setTimeout(searchGenes, 300)
}

async function addRequiredGene(gene: GeneSearchResult) {
  if (!orgId.value) return
  addingGeneId.value = gene.id
  try {
    const res = await api.post(`/orgs/${orgId.value}/required-genes`, { gene_id: gene.id })
    requiredGenes.value.push(res.data.data)
    searchResults.value = searchResults.value.filter(g => g.id !== gene.id)
    toast.success(t('orgSettings.geneAdded'))
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e))
  } finally {
    addingGeneId.value = null
  }
}

async function removeRequiredGene(rg: RequiredGeneItem) {
  if (!orgId.value) return
  const ok = await confirm({
    title: t('orgSettings.removeConfirmTitle'),
    description: t('orgSettings.removeConfirmBody', { name: rg.gene_name }),
  })
  if (!ok) return

  actionLoading.value = rg.id
  try {
    await api.delete(`/orgs/${orgId.value}/required-genes/${rg.id}`)
    requiredGenes.value = requiredGenes.value.filter(g => g.id !== rg.id)
    toast.success(t('orgSettings.geneRemoved'))
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e))
  } finally {
    actionLoading.value = null
  }
}

function openAddDialog() {
  showAddDialog.value = true
  searchQuery.value = ''
  searchResults.value = []
  fetchInitialGenes()
}

function closeAddDialog() {
  showAddDialog.value = false
}

onMounted(async () => {
  if (!orgStore.currentOrg) await orgStore.fetchMyOrg()
  await fetchRequiredGenes()
})
</script>

<template>
  <div>
    <section>
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-base font-semibold">{{ t('orgSettings.requiredGenesTitle') }}</h2>
          <p class="text-xs text-muted-foreground mt-1">{{ t('orgSettings.requiredGenesDesc') }}</p>
        </div>
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
          @click="openAddDialog"
        >
          <Plus class="w-3.5 h-3.5" />
          {{ t('orgSettings.addGene') }}
        </button>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-12">
        <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="requiredGenes.length === 0"
        class="flex flex-col items-center justify-center py-12 border border-dashed border-border rounded-xl"
      >
        <Dna class="w-8 h-8 text-muted-foreground/50 mb-3" />
        <p class="text-sm text-muted-foreground">{{ t('orgSettings.emptyState') }}</p>
      </div>

      <div v-else class="space-y-2">
        <div
          v-for="rg in requiredGenes"
          :key="rg.id"
          class="flex items-center justify-between p-4 rounded-xl border border-border bg-card"
        >
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <FlaskConical class="w-4 h-4 text-primary" />
            </div>
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium truncate">{{ rg.gene_name }}</span>
                <span
                  v-if="rg.gene_category"
                  class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                >{{ rg.gene_category }}</span>
              </div>
              <p v-if="rg.gene_short_description" class="text-xs text-muted-foreground mt-0.5 truncate">
                {{ rg.gene_short_description }}
              </p>
            </div>
          </div>
          <button
            class="shrink-0 p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
            :disabled="actionLoading === rg.id"
            @click="removeRequiredGene(rg)"
          >
            <Loader2 v-if="actionLoading === rg.id" class="w-4 h-4 animate-spin" />
            <Trash2 v-else class="w-4 h-4" />
          </button>
        </div>
      </div>
    </section>

    <Transition name="fade">
      <div
        v-if="showAddDialog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="closeAddDialog"
      >
        <div class="bg-card border border-border rounded-xl shadow-lg max-w-md w-full mx-4 max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-border">
            <h3 class="text-sm font-semibold">{{ t('orgSettings.addGeneDialogTitle') }}</h3>
            <button class="p-1 rounded-md hover:bg-muted transition-colors" @click="closeAddDialog">
              <X class="w-4 h-4 text-muted-foreground" />
            </button>
          </div>

          <div class="p-4 border-b border-border">
            <div class="relative">
              <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                v-model="searchQuery"
                class="w-full pl-9 pr-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
                :placeholder="t('orgSettings.searchGenePlaceholder')"
                @input="onSearchInput"
              />
            </div>
          </div>

          <div class="flex-1 overflow-y-auto p-4 min-h-[200px] max-h-[400px]">
            <div v-if="searching" class="flex items-center justify-center py-8">
              <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
            </div>

            <div v-else-if="searchResults.length === 0" class="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <p class="text-xs">{{ searchQuery.trim() ? t('orgSettings.noResults') : t('orgSettings.noGenesAvailable') }}</p>
            </div>

            <div v-else class="space-y-2">
              <div
                v-for="gene in searchResults"
                :key="gene.id"
                class="flex items-center justify-between p-3 rounded-lg border border-border hover:border-primary/30 transition-colors"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium truncate">{{ gene.name }}</span>
                    <span
                      v-if="gene.category"
                      class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
                    >{{ gene.category }}</span>
                  </div>
                  <p v-if="gene.short_description" class="text-xs text-muted-foreground mt-0.5 truncate">
                    {{ gene.short_description }}
                  </p>
                </div>
                <button
                  class="shrink-0 ml-3 px-2.5 py-1 rounded-md bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
                  :disabled="addingGeneId === gene.id"
                  @click="addRequiredGene(gene)"
                >
                  <Loader2 v-if="addingGeneId === gene.id" class="w-3 h-3 animate-spin" />
                  <Plus v-else class="w-3 h-3" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
