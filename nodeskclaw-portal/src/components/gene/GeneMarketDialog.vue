<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  X,
  Search,
  Loader2,
  Star,
  Package,
  Code,
  Database,
  Cpu,
  Server,
  Shield,
  Zap,
  Wrench,
  Palette,
  MessageSquare,
  Network,
  Sparkles,
  Layers,
  Download,
  ArrowLeft,
  Check,
  FileText,
  AlertTriangle,
} from 'lucide-vue-next'
import { renderMarkdown } from '@/utils/markdown'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem, GenomeItem } from '@/stores/gene'
import api from '@/services/api'
import { useToast } from '@/composables/useToast'
import CustomSelect from '@/components/shared/CustomSelect.vue'

const props = defineProps<{
  modelValue: boolean
  instanceId: string
  installedSkillNames?: Set<string>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  installed: []
}>()

const { t } = useI18n()
const store = useGeneStore()
const toast = useToast()

// ── View state ──────────────────────────────────

type ViewState = 'list' | 'gene-detail' | 'genome-detail'
const viewState = ref<ViewState>('list')
const viewMode = ref<'genes' | 'genomes'>('genes')

// ── List state (independent from store.loading) ─

const dialogLoading = ref(false)
const genes = ref<GeneItem[]>([])
const genomes = ref<GenomeItem[]>([])
const totalGenes = ref(0)
const totalGenomes = ref(0)
const tagStats = ref<{ tag: string; count: number }[]>([])

const keyword = ref('')
const selectedTag = ref<string | null>(null)
const selectedCategory = ref<string | null>(null)
const sortBy = ref('popularity')
const page = ref(1)
const pageSize = 12

const categories = ['开发', '数据', '运维', '网络', '创意', '沟通', '安全', '效率']
const sortOptions = ['popularity', 'rating', 'effectiveness', 'newest']

// ── Installed gene tracking ─────────────────────

const localInstalledSlugs = ref<Set<string>>(new Set())

const installedSlugs = computed(() => {
  const base = props.installedSkillNames ?? new Set<string>()
  const merged = new Set(base)
  for (const slug of localInstalledSlugs.value) merged.add(slug)
  return merged
})

function isInstalled(slug: string): boolean {
  return installedSlugs.value.has(slug)
}

// ── Data loading ────────────────────────────────

async function loadGenes() {
  dialogLoading.value = true
  try {
    const res = await api.get('/genes', {
      params: {
        keyword: keyword.value || undefined,
        tag: selectedTag.value || undefined,
        category: selectedCategory.value || undefined,
        sort: sortBy.value,
        page: page.value,
        page_size: pageSize,
      },
    })
    genes.value = res.data.data || []
    totalGenes.value = res.data.pagination?.total || 0
  } catch {
    genes.value = []
    totalGenes.value = 0
  } finally {
    dialogLoading.value = false
  }
}

async function loadGenomes() {
  dialogLoading.value = true
  try {
    const res = await api.get('/genomes', {
      params: {
        keyword: keyword.value || undefined,
        page: page.value,
        page_size: pageSize,
      },
    })
    genomes.value = res.data.data || []
    totalGenomes.value = res.data.pagination?.total || 0
  } catch {
    genomes.value = []
    totalGenomes.value = 0
  } finally {
    dialogLoading.value = false
  }
}

async function loadTags() {
  try {
    const res = await api.get('/genes/tags')
    tagStats.value = res.data.data || []
  } catch {
    tagStats.value = []
  }
}

async function loadData() {
  if (viewMode.value === 'genes') await loadGenes()
  else await loadGenomes()
}

// ── Gene detail state ───────────────────────────

const detailGene = ref<GeneItem | null>(null)
const detailGenome = ref<GenomeItem | null>(null)
const detailLoading = ref(false)
const installing = ref(false)
const contentViewMode = ref<'rendered' | 'source'>('rendered')

const genomeGeneMap = ref<Record<string, GeneItem>>({})
const activeGenomeGeneTab = ref('')

async function openGeneDetail(id: string) {
  viewState.value = 'gene-detail'
  detailLoading.value = true
  contentViewMode.value = 'rendered'
  try {
    const res = await api.get(`/genes/${id}`)
    detailGene.value = res.data.data
  } catch {
    detailGene.value = null
  } finally {
    detailLoading.value = false
  }
}

async function openGenomeDetail(id: string) {
  viewState.value = 'genome-detail'
  detailLoading.value = true
  contentViewMode.value = 'rendered'
  genomeGeneMap.value = {}
  activeGenomeGeneTab.value = ''
  try {
    const res = await api.get(`/genomes/${id}`)
    detailGenome.value = res.data.data
    const slugs = detailGenome.value?.gene_slugs
    if (slugs?.length) {
      activeGenomeGeneTab.value = slugs[0]!
      await fetchGenesForSlugs(slugs)
    }
  } catch {
    detailGenome.value = null
  } finally {
    detailLoading.value = false
  }
}

async function fetchGenesForSlugs(slugs: string[]) {
  const results = await Promise.all(
    slugs.map(async (slug) => {
      try {
        const res = await api.get('/genes', { params: { keyword: slug, page_size: 5 } })
        const list: GeneItem[] = res.data.data || []
        return list.find((g) => g.slug === slug) || null
      } catch {
        return null
      }
    }),
  )
  const map: Record<string, GeneItem> = {}
  for (const g of results) {
    if (g) map[g.slug] = g
  }
  genomeGeneMap.value = map
}

function goBackToList() {
  viewState.value = 'list'
  detailGene.value = null
  detailGenome.value = null
}

// ── Install actions ─────────────────────────────

async function handleInstallGene(slug: string) {
  installing.value = true
  try {
    await store.installGene(props.instanceId, slug)
    localInstalledSlugs.value.add(slug)
    toast.success(t('geneMarketDialog.learnSuccess'))
    emit('installed')
  } catch {
    toast.error(t('geneMarketDialog.learnFailed'))
  } finally {
    installing.value = false
  }
}

async function handleApplyGenome(genomeId: string) {
  installing.value = true
  try {
    await store.applyGenome(props.instanceId, genomeId)
    toast.success(t('geneMarketDialog.genomeApplySuccess'))
    emit('installed')
  } catch {
    toast.error(t('geneMarketDialog.learnFailed'))
  } finally {
    installing.value = false
  }
}

// ── Helpers ─────────────────────────────────────

const geneMetaKeyMap: Record<string, string> = {
  开发: 'geneMeta.development',
  数据: 'geneMeta.data',
  运维: 'geneMeta.ops',
  网络: 'geneMeta.network',
  创意: 'geneMeta.creativity',
  沟通: 'geneMeta.communication',
  安全: 'geneMeta.security',
  效率: 'geneMeta.efficiency',
  性格: 'geneMeta.personality',
  能力: 'geneMeta.ability',
  知识: 'geneMeta.knowledge',
}

function localizeGeneMeta(value?: string) {
  if (!value) return ''
  const key = geneMetaKeyMap[value]
  if (!key) return value
  const translated = t(key)
  return translated === key ? value : translated
}

function getSortLabel(value: string) {
  const map: Record<string, string> = {
    popularity: 'geneMarket.sortPopularity',
    rating: 'geneMarket.sortRating',
    effectiveness: 'geneMarket.sortEffectiveness',
    newest: 'geneMarket.sortNewest',
  }
  const key = map[value]
  if (!key) return value
  const translated = t(key)
  return translated === key ? value : translated
}

const categorySelectOptions = computed(() => [
  { value: null, label: t('geneMarket.allCategories') },
  ...categories.map(c => ({ value: c, label: localizeGeneMeta(c) })),
])

const sortSelectOptions = computed(() =>
  sortOptions.map(s => ({ value: s, label: getSortLabel(s) }))
)

const iconMap: Record<string, typeof Package> = {
  code: Code, database: Database, cpu: Cpu, server: Server,
  shield: Shield, zap: Zap, wrench: Wrench, palette: Palette,
  message: MessageSquare, network: Network, sparkles: Sparkles,
  layers: Layers, package: Package,
}

function resolveIcon(iconName?: string) {
  if (!iconName) return Package
  const key = iconName.toLowerCase().replace(/[- ]/g, '')
  return iconMap[key] ?? iconMap[iconName] ?? Package
}

function hasNativeTools(gene: GeneItem): boolean {
  const toolAllow = gene.manifest?.tool_allow
  if (Array.isArray(toolAllow) && toolAllow.length > 0) return true
  const mcpServers = gene.manifest?.mcp_servers
  if (Array.isArray(mcpServers) && mcpServers.length > 0) return true
  const tags = gene.tags ?? []
  return tags.some((t) => ['mcp', 'tools'].includes(String(t).toLowerCase()))
}

// ── Gene detail computed ────────────────────────

const toolAllowList = computed(() => {
  const ta = (detailGene.value?.manifest as Record<string, any>)?.tool_allow
  return Array.isArray(ta) ? ta : []
})

const descriptionHtml = computed(() => {
  const d = detailGene.value?.description
  if (!d) return ''
  return renderMarkdown(d)
})

const skillContentRaw = computed(() => {
  return (detailGene.value?.manifest as Record<string, any>)?.skill?.content ?? ''
})

function parseFrontmatter(content: string): { fm: string; body: string } {
  const trimmed = content.trimStart()
  if (!trimmed.startsWith('---')) return { fm: '', body: content }
  const closing = trimmed.indexOf('---', 3)
  if (closing === -1) return { fm: '', body: content }
  return { fm: trimmed.slice(3, closing).trim(), body: trimmed.slice(closing + 3).trimStart() }
}

const skillContentHtml = computed(() => {
  if (!skillContentRaw.value) return ''
  const { fm, body } = parseFrontmatter(skillContentRaw.value)
  const fmHtml = fm
    ? `<div class="not-prose mb-4 rounded-lg border border-border bg-muted/30 p-4"><div class="text-xs font-medium text-muted-foreground mb-2">${t('gene.frontmatterLabel')}</div><pre class="text-sm font-mono leading-relaxed text-foreground whitespace-pre-wrap">${fm.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre></div>`
    : ''
  return fmHtml + renderMarkdown(body)
})

const hasFrontmatter = computed(() => {
  const raw = skillContentRaw.value
  return raw ? raw.trimStart().startsWith('---') : true
})

// ── Genome detail computed ──────────────────────

const activeGenomeGeneContentRaw = computed(() => {
  const gene = genomeGeneMap.value[activeGenomeGeneTab.value]
  return (gene?.manifest as Record<string, any>)?.skill?.content ?? ''
})

const activeGenomeGeneContentHtml = computed(() => {
  if (!activeGenomeGeneContentRaw.value) return ''
  const { fm, body } = parseFrontmatter(activeGenomeGeneContentRaw.value)
  const fmHtml = fm
    ? `<div class="not-prose mb-4 rounded-lg border border-border bg-muted/30 p-4"><div class="text-xs font-medium text-muted-foreground mb-2">${t('gene.frontmatterLabel')}</div><pre class="text-sm font-mono leading-relaxed text-foreground whitespace-pre-wrap">${fm.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre></div>`
    : ''
  return fmHtml + renderMarkdown(body)
})

const activeGenomeGeneHasFrontmatter = computed(() => {
  const raw = activeGenomeGeneContentRaw.value
  return raw ? raw.trimStart().startsWith('---') : true
})

// ── Pagination ──────────────────────────────────

const totalCount = computed(() => viewMode.value === 'genes' ? totalGenes.value : totalGenomes.value)
const totalPages = computed(() => Math.ceil(totalCount.value / pageSize) || 1)
const canPrev = computed(() => page.value > 1)
const canNext = computed(() => page.value < totalPages.value)

// ── Dialog open/close ───────────────────────────

function close() {
  emit('update:modelValue', false)
}

watch(() => props.modelValue, async (open) => {
  if (open) {
    viewState.value = 'list'
    viewMode.value = 'genes'
    keyword.value = ''
    selectedTag.value = null
    selectedCategory.value = null
    sortBy.value = 'popularity'
    page.value = 1
    localInstalledSlugs.value = new Set()
    await loadTags()
    await loadData()
  }
})

// ── Watchers for filters ────────────────────────

let keywordTimer: ReturnType<typeof setTimeout> | null = null

watch(keyword, () => {
  if (keywordTimer) clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => {
    page.value = 1
    loadData()
  }, 300)
})

watch([viewMode, selectedTag, selectedCategory, sortBy], () => {
  page.value = 1
  loadData()
})

watch(page, loadData)

onUnmounted(() => {
  if (keywordTimer) clearTimeout(keywordTimer)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="modelValue"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      @click.self="close"
    >
      <div
        class="w-full max-w-4xl mx-4 rounded-xl border border-border bg-card shadow-xl flex flex-col h-[85vh]"
        @click.stop
      >
        <!-- Header -->
        <div class="shrink-0 flex items-center justify-between px-6 py-4 border-b border-border">
          <div class="flex items-center gap-3">
            <button
              v-if="viewState !== 'list'"
              class="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
              @click="goBackToList"
            >
              <ArrowLeft class="w-4 h-4" />
            </button>
            <h3 class="text-lg font-semibold">
              <template v-if="viewState === 'list'">{{ t('geneMarketDialog.title') }}</template>
              <template v-else-if="viewState === 'gene-detail'">{{ detailGene?.name ?? '' }}</template>
              <template v-else>{{ detailGenome?.name ?? '' }}</template>
            </h3>
          </div>
          <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="close">
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Content -->
        <div class="flex-1 min-h-0 px-6 py-4">

          <!-- ═══ LIST VIEW ═══ -->
          <template v-if="viewState === 'list'">
            <div class="flex h-full min-h-0 flex-col">
              <div class="flex-1 min-h-0 overflow-y-auto">
                <!-- Tabs -->
                <div class="flex items-center gap-2 mb-4">
                  <button
                    :class="['px-4 py-2 rounded-lg text-sm font-medium transition-colors', viewMode === 'genes' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted']"
                    @click="viewMode = 'genes'"
                  >
                    {{ t('geneMarket.tabGenes') }}
                  </button>
                  <button
                    :class="['px-4 py-2 rounded-lg text-sm font-medium transition-colors', viewMode === 'genomes' ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted']"
                    @click="viewMode = 'genomes'"
                  >
                    {{ t('geneMarket.tabGenomes') }}
                  </button>
                </div>

                <!-- Filters -->
                <div class="flex flex-wrap gap-3 mb-4">
                  <div class="relative flex-1 min-w-[180px]">
                    <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                    <input
                      v-model="keyword"
                      type="text"
                      :placeholder="t('geneMarket.searchPlaceholder')"
                      class="w-full pl-10 pr-4 py-2 rounded-lg border border-border bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 text-sm"
                    />
                  </div>
                  <CustomSelect
                    v-if="viewMode === 'genes'"
                    v-model="selectedCategory"
                    :options="categorySelectOptions"
                  />
                  <CustomSelect v-model="sortBy" :options="sortSelectOptions" />
                </div>

                <!-- Tags -->
                <div v-if="viewMode === 'genes' && tagStats.length" class="flex flex-wrap gap-1.5 mb-4">
                  <button
                    v-for="ts in tagStats"
                    :key="ts.tag"
                    :class="['px-2.5 py-1 rounded-lg text-xs font-medium transition-colors', selectedTag === ts.tag ? 'bg-primary/10 text-primary' : 'bg-muted/50 text-muted-foreground hover:text-foreground hover:bg-muted']"
                    @click="selectedTag = selectedTag === ts.tag ? null : ts.tag"
                  >
                    {{ localizeGeneMeta(ts.tag) }}
                  </button>
                </div>

                <!-- Loading -->
                <div v-if="dialogLoading" class="flex justify-center py-16">
                  <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
                </div>

                <!-- Gene cards -->
                <template v-else-if="viewMode === 'genes'">
                  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    <div
                      v-for="gene in genes"
                      :key="gene.id"
                      class="p-4 rounded-xl border border-border bg-background hover:border-primary/30 transition cursor-pointer relative overflow-hidden"
                      @click="openGeneDetail(gene.id)"
                    >
                      <div
                        v-if="isInstalled(gene.slug)"
                        class="absolute top-0 right-0 w-6 h-6 bg-green-600 rounded-bl-lg flex items-center justify-center"
                      >
                        <Check class="w-3 h-3 text-white" />
                      </div>
                      <div class="flex items-start gap-3 mb-2">
                        <div class="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                          <component :is="resolveIcon(gene.icon)" class="w-4 h-4 text-primary" />
                        </div>
                        <div class="min-w-0 flex-1">
                          <div class="flex items-center gap-2 flex-wrap">
                            <span class="font-medium text-sm truncate">{{ gene.name }}</span>
                            <span class="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">v{{ gene.version }}</span>
                            <span
                              v-if="hasNativeTools(gene)"
                              class="shrink-0 bg-cyan-500/10 text-cyan-400 text-[10px] px-1.5 py-0.5 rounded"
                            >
                              {{ t('geneMarket.hasNativeTools') }}
                            </span>
                          </div>
                          <p class="text-xs text-muted-foreground line-clamp-2 mt-1">
                            {{ gene.short_description ?? gene.description ?? '' }}
                          </p>
                        </div>
                      </div>
                      <div class="flex flex-wrap gap-1 mt-2">
                        <span
                          v-for="tag in gene.tags.slice(0, 3)"
                          :key="tag"
                          class="text-[10px] px-1.5 py-0.5 rounded bg-primary/10 text-primary"
                        >
                          {{ localizeGeneMeta(tag) }}
                        </span>
                      </div>
                      <div class="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                        <span class="flex items-center gap-0.5">
                          <Star class="w-3 h-3 fill-amber-400 text-amber-400" />
                          {{ (gene.avg_rating ?? 0).toFixed(1) }}
                        </span>
                        <div class="flex-1 min-w-0">
                          <div class="h-1 rounded-full bg-muted overflow-hidden">
                            <div class="h-full rounded-full bg-primary/60" :style="{ width: `${Math.min(100, (gene.effectiveness_score ?? 0) * 100)}%` }" />
                          </div>
                        </div>
                        <span class="shrink-0">{{ t('geneMarket.learnCount', { count: gene.install_count ?? 0 }) }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="genes.length === 0" class="py-12 text-center text-muted-foreground text-sm">
                    {{ t('geneMarket.searchPlaceholder') }}
                  </div>
                </template>

                <!-- Genome cards -->
                <template v-else>
                  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    <div
                      v-for="genome in genomes"
                      :key="genome.id"
                      class="p-4 rounded-xl border border-border bg-background hover:border-primary/30 transition cursor-pointer"
                      @click="openGenomeDetail(genome.id)"
                    >
                      <div class="flex items-start gap-3 mb-2">
                        <div class="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                          <component :is="resolveIcon(genome.icon)" class="w-4 h-4 text-primary" />
                        </div>
                        <div class="min-w-0 flex-1">
                          <div class="flex items-center gap-2 flex-wrap">
                            <span class="font-medium text-sm truncate">{{ genome.name }}</span>
                            <span
                              v-if="genome.native_tool_count"
                              class="shrink-0 inline-flex items-center gap-1 bg-cyan-500/10 text-cyan-400 text-[10px] px-1.5 py-0.5 rounded"
                            >
                              <Wrench class="w-3 h-3" />
                              {{ t('genome.nativeToolCount', { count: genome.native_tool_count }) }}
                            </span>
                            <span
                              v-if="genome.mcp_server_count"
                              class="shrink-0 inline-flex items-center gap-1 bg-violet-500/10 text-violet-400 text-[10px] px-1.5 py-0.5 rounded"
                            >
                              <Server class="w-3 h-3" />
                              {{ t('genome.mcpServerCount', { count: genome.mcp_server_count }) }}
                            </span>
                          </div>
                          <p class="text-xs text-muted-foreground line-clamp-2 mt-1">
                            {{ genome.short_description ?? genome.description ?? '' }}
                          </p>
                        </div>
                      </div>
                      <div class="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                        <span class="flex items-center gap-0.5">
                          <Star class="w-3 h-3 fill-amber-400 text-amber-400" />
                          {{ (genome.avg_rating ?? 0).toFixed(1) }}
                        </span>
                        <span class="shrink-0">{{ t('geneMarket.learnCount', { count: genome.install_count ?? 0 }) }}</span>
                      </div>
                    </div>
                  </div>
                  <div v-if="genomes.length === 0" class="py-12 text-center text-muted-foreground text-sm">
                    {{ t('geneMarket.searchPlaceholder') }}
                  </div>
                </template>
              </div>
              <div v-if="totalPages > 1" class="shrink-0 flex items-center justify-center gap-2 mt-4 pt-4 border-t border-border">
                <button
                  :disabled="!canPrev"
                  :class="['px-3 py-1.5 rounded-lg text-sm transition-colors', canPrev ? 'text-foreground hover:bg-muted' : 'text-muted-foreground cursor-not-allowed']"
                  @click="page = Math.max(1, page - 1)"
                >
                  {{ t('geneMarket.prevPage') }}
                </button>
                <span class="text-sm text-muted-foreground">{{ page }} / {{ totalPages }}</span>
                <button
                  :disabled="!canNext"
                  :class="['px-3 py-1.5 rounded-lg text-sm transition-colors', canNext ? 'text-foreground hover:bg-muted' : 'text-muted-foreground cursor-not-allowed']"
                  @click="page = Math.min(totalPages, page + 1)"
                >
                  {{ t('geneMarket.nextPage') }}
                </button>
              </div>
            </div>
          </template>

          <!-- ═══ GENE DETAIL VIEW ═══ -->
          <template v-else-if="viewState === 'gene-detail'">
            <div class="h-full overflow-y-auto">
              <div v-if="detailLoading" class="flex justify-center py-16">
                <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
              </div>
              <template v-else-if="detailGene">
                <!-- Gene header info -->
                <div class="flex items-center gap-4 mb-6">
                  <div class="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                    <component :is="resolveIcon(detailGene.icon)" class="w-6 h-6 text-primary" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex flex-wrap gap-2 mt-1">
                      <span class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">v{{ detailGene.version }}</span>
                      <span class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{{ detailGene.source }}</span>
                      <span v-if="detailGene.category" class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{{ localizeGeneMeta(detailGene.category) }}</span>
                      <span
                        v-if="toolAllowList.length"
                        class="shrink-0 bg-cyan-500/10 text-cyan-400 text-[10px] px-1.5 py-0.5 rounded"
                      >
                        {{ t('geneMarket.hasNativeTools') }}
                      </span>
                    </div>
                  </div>
                  <button
                    v-if="!isInstalled(detailGene.slug)"
                    class="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                    :disabled="installing"
                    @click="handleInstallGene(detailGene.slug)"
                  >
                    <Loader2 v-if="installing" class="w-4 h-4 animate-spin" />
                    <Download v-else class="w-4 h-4" />
                    {{ t('geneMarketDialog.learnForInstance') }}
                  </button>
                  <span
                    v-else
                    class="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-green-500/10 text-green-500 text-sm"
                  >
                    <Check class="w-4 h-4" />
                    {{ t('geneMarketDialog.alreadyLearned') }}
                  </span>
                </div>

                <!-- Tags -->
                <div v-if="detailGene.tags?.length" class="flex flex-wrap gap-2 mb-6">
                  <span
                    v-for="tag in detailGene.tags"
                    :key="tag"
                    class="text-xs px-2.5 py-1 rounded-lg bg-primary/10 text-primary"
                  >
                    {{ localizeGeneMeta(tag) }}
                  </span>
                </div>

                <!-- Description -->
                <section v-if="detailGene.description" class="mb-6">
                  <h2 class="text-base font-semibold mb-2">{{ t('gene.description') }}</h2>
                  <div
                    class="prose prose-sm max-w-none text-foreground prose-headings:text-foreground prose-p:text-foreground prose-a:text-primary"
                    v-html="descriptionHtml"
                  />
                </section>

                <!-- Tool capabilities -->
                <section v-if="toolAllowList.length" class="mb-6">
                  <h2 class="text-base font-semibold mb-2">{{ t('gene.toolCapabilities') }}</h2>
                  <div class="flex flex-wrap gap-2">
                    <div
                      v-for="tool in toolAllowList"
                      :key="tool"
                      class="flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-background"
                    >
                      <Wrench class="w-4 h-4 text-cyan-400" />
                      <span class="text-sm font-mono">{{ tool }}</span>
                    </div>
                  </div>
                </section>

                <!-- Gene content -->
                <section v-if="skillContentRaw" class="mb-6">
                  <div class="flex items-center justify-between mb-2">
                    <h2 class="text-base font-semibold">{{ t('gene.content') }}</h2>
                    <div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
                      <button
                        :class="['p-1.5 rounded-md transition-colors', contentViewMode === 'rendered' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground']"
                        :title="t('gene.renderDocument')"
                        @click="contentViewMode = 'rendered'"
                      >
                        <FileText class="w-4 h-4" />
                      </button>
                      <button
                        :class="['p-1.5 rounded-md transition-colors', contentViewMode === 'source' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground']"
                        :title="t('gene.viewSource')"
                        @click="contentViewMode = 'source'"
                      >
                        <Code class="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div
                    v-if="!hasFrontmatter"
                    class="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 mb-3"
                  >
                    <div class="flex items-start gap-2">
                      <AlertTriangle class="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                      <p class="text-xs text-muted-foreground">{{ t('gene.frontmatterMissing') }}</p>
                    </div>
                  </div>
                  <div
                    v-if="contentViewMode === 'rendered'"
                    class="rounded-xl border border-border bg-background p-6 prose prose-sm prose-invert max-w-none prose-a:text-primary"
                    v-html="skillContentHtml"
                  />
                  <pre
                    v-else
                    class="rounded-xl border border-border bg-background p-6 text-sm font-mono leading-relaxed text-foreground overflow-x-auto whitespace-pre-wrap wrap-break-word"
                  >{{ skillContentRaw }}</pre>
                </section>

                <!-- Rating -->
                <section class="mb-4">
                  <h2 class="text-base font-semibold mb-2">{{ t('gene.rating') }}</h2>
                  <div class="flex items-center gap-6">
                    <div class="flex items-center gap-1">
                      <Star
                        v-for="i in 5"
                        :key="i"
                        :class="['w-4 h-4', i <= Math.round(detailGene.avg_rating ?? 0) ? 'fill-amber-400 text-amber-400' : 'text-muted']"
                      />
                      <span class="ml-2 text-sm text-muted-foreground">{{ (detailGene.avg_rating ?? 0).toFixed(1) }}</span>
                    </div>
                    <div class="flex-1 min-w-0 max-w-xs">
                      <div class="text-xs text-muted-foreground mb-1">{{ t('gene.effectivenessScore') }}</div>
                      <div class="h-1.5 rounded-full bg-muted overflow-hidden">
                        <div class="h-full rounded-full bg-primary/60" :style="{ width: `${Math.min(100, (detailGene.effectiveness_score ?? 0) * 100)}%` }" />
                      </div>
                    </div>
                  </div>
                </section>
              </template>
            </div>
          </template>

          <!-- ═══ GENOME DETAIL VIEW ═══ -->
          <template v-else-if="viewState === 'genome-detail'">
            <div class="h-full overflow-y-auto">
              <div v-if="detailLoading" class="flex justify-center py-16">
                <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
              </div>
              <template v-else-if="detailGenome">
              <!-- Genome header info -->
              <div class="flex items-center gap-4 mb-6">
                <div class="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
                  <component :is="resolveIcon(detailGenome.icon)" class="w-6 h-6 text-primary" />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span
                      v-if="detailGenome.native_tool_count"
                      class="shrink-0 inline-flex items-center gap-1 bg-cyan-500/10 text-cyan-400 text-xs px-2 py-0.5 rounded"
                    >
                      <Wrench class="w-3.5 h-3.5" />
                      {{ t('genome.nativeToolCount', { count: detailGenome.native_tool_count }) }}
                    </span>
                    <span
                      v-if="detailGenome.mcp_server_count"
                      class="shrink-0 inline-flex items-center gap-1 bg-violet-500/10 text-violet-400 text-xs px-2 py-0.5 rounded"
                    >
                      <Server class="w-3.5 h-3.5" />
                      {{ t('genome.mcpServerCount', { count: detailGenome.mcp_server_count }) }}
                    </span>
                  </div>
                </div>
                <button
                  class="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                  :disabled="installing"
                  @click="handleApplyGenome(detailGenome.id)"
                >
                  <Loader2 v-if="installing" class="w-4 h-4 animate-spin" />
                  <Download v-else class="w-4 h-4" />
                  {{ t('geneMarketDialog.learnForInstance') }}
                </button>
              </div>

              <!-- Description -->
              <section v-if="detailGenome.description" class="mb-6">
                <h2 class="text-base font-semibold mb-2">{{ t('gene.description') }}</h2>
                <p class="text-muted-foreground text-sm">{{ detailGenome.description }}</p>
              </section>

              <!-- Included genes -->
              <section v-if="detailGenome.gene_slugs?.length" class="mb-6">
                <h2 class="text-base font-semibold mb-3">{{ t('genome.genesIncluded') }}</h2>
                <div class="flex gap-0 border-b border-border mb-0 overflow-x-auto scrollbar-none">
                  <button
                    v-for="slug in detailGenome.gene_slugs"
                    :key="slug"
                    :class="['shrink-0 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px inline-flex items-center gap-1', activeGenomeGeneTab === slug ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border']"
                    @click="activeGenomeGeneTab = slug"
                  >
                    {{ genomeGeneMap[slug]?.name ?? slug }}
                    <Check
                      v-if="genomeGeneMap[slug]?.slug && isInstalled(genomeGeneMap[slug]!.slug)"
                      class="w-3.5 h-3.5 text-green-500"
                    />
                  </button>
                </div>
                <div class="rounded-b-xl border border-t-0 border-border bg-background p-6">
                  <div v-if="genomeGeneMap[activeGenomeGeneTab]?.description" class="text-sm text-muted-foreground mb-4">
                    {{ genomeGeneMap[activeGenomeGeneTab]?.description }}
                  </div>
                  <div v-if="activeGenomeGeneContentRaw" class="flex items-center justify-between mb-3">
                    <span class="text-xs font-medium text-muted-foreground uppercase tracking-wider">SKILL.md</span>
                    <div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
                      <button
                        :class="['p-1.5 rounded-md transition-colors', contentViewMode === 'rendered' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground']"
                        :title="t('gene.renderDocument')"
                        @click="contentViewMode = 'rendered'"
                      >
                        <FileText class="w-3.5 h-3.5" />
                      </button>
                      <button
                        :class="['p-1.5 rounded-md transition-colors', contentViewMode === 'source' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground']"
                        :title="t('gene.viewSource')"
                        @click="contentViewMode = 'source'"
                      >
                        <Code class="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                  <div
                    v-if="activeGenomeGeneContentRaw && !activeGenomeGeneHasFrontmatter"
                    class="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 mb-3"
                  >
                    <div class="flex items-start gap-2">
                      <AlertTriangle class="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                      <p class="text-xs text-muted-foreground">{{ t('gene.frontmatterMissing') }}</p>
                    </div>
                  </div>
                  <div
                    v-if="activeGenomeGeneContentRaw && contentViewMode === 'rendered'"
                    class="prose prose-sm prose-invert max-w-none prose-a:text-primary"
                    v-html="activeGenomeGeneContentHtml"
                  />
                  <pre
                    v-else-if="activeGenomeGeneContentRaw && contentViewMode === 'source'"
                    class="text-sm font-mono leading-relaxed text-foreground overflow-x-auto whitespace-pre-wrap wrap-break-word"
                  >{{ activeGenomeGeneContentRaw }}</pre>
                  <div v-else class="py-8 text-center text-sm text-muted-foreground">
                    {{ t('genome.noGeneContent') }}
                  </div>
                </div>
              </section>

              <!-- Rating -->
              <section class="mb-4">
                <h2 class="text-base font-semibold mb-2">{{ t('gene.rating') }}</h2>
                <div class="flex items-center gap-1">
                  <Star
                    v-for="i in 5"
                    :key="i"
                    :class="['w-4 h-4', i <= Math.round(detailGenome.avg_rating ?? 0) ? 'fill-amber-400 text-amber-400' : 'text-muted']"
                  />
                  <span class="ml-2 text-sm text-muted-foreground">{{ (detailGenome.avg_rating ?? 0).toFixed(1) }}</span>
                </div>
              </section>
              </template>
            </div>
          </template>

        </div>
      </div>
    </div>
  </Teleport>
</template>
