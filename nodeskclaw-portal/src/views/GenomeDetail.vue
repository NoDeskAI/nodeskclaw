<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft,
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
  Check,
  FileText,
  AlertTriangle,
  Download,
  X,
  Copy,
  ExternalLink,
} from 'lucide-vue-next'
import { renderMarkdown } from '@/utils/markdown'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem } from '@/stores/gene'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const store = useGeneStore()
const { t } = useI18n()

const genomeId = computed(() => route.params.id as string)
const genome = computed(() => store.currentGenome)
const geneMap = ref<Record<string, GeneItem>>({})
const activeGeneTab = ref<string>('')

const installDialogOpen = ref(false)
const instances = ref<{ id: string; name: string; slug: string; status: string }[]>([])
const instancesLoading = ref(false)

const statusConfig: Record<string, { dot: string; text: string; bg: string }> = {
  running: { dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-950/40' },
  learning: { dot: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/40' },
  creating: { dot: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/40' },
  pending: { dot: 'bg-yellow-500', text: 'text-yellow-600 dark:text-yellow-400', bg: 'bg-yellow-50 dark:bg-yellow-950/40' },
  deploying: { dot: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/40' },
  updating: { dot: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-950/40' },
  failed: { dot: 'bg-red-500', text: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-950/40' },
  deleting: { dot: 'bg-gray-400', text: 'text-gray-500 dark:text-gray-400', bg: 'bg-gray-50 dark:bg-gray-950/40' },
}

function getStatusConfig(status: string) {
  return statusConfig[status] ?? { dot: 'bg-gray-400', text: 'text-gray-500 dark:text-gray-400', bg: 'bg-gray-50 dark:bg-gray-950/40' }
}

function getStatusLabel(status: string) {
  const key = `status.${status}`
  const translated = t(key)
  return translated === key ? status : translated
}

const copiedSlug = ref<string | null>(null)
async function copySlug(slug: string) {
  try {
    await navigator.clipboard.writeText(slug)
    copiedSlug.value = slug
    setTimeout(() => { copiedSlug.value = null }, 1500)
  } catch { /* ignore */ }
}

function openInstallDialog() {
  installDialogOpen.value = true
  instancesLoading.value = true
  api.get('/instances').then((res) => {
    instances.value = (res.data.data || []).map((i: { id: string; name: string; slug: string; status: string }) => ({
      id: i.id, name: i.name, slug: i.slug, status: i.status,
    }))
  }).catch(() => {
    instances.value = []
  }).finally(() => {
    instancesLoading.value = false
  })
}

function closeInstallDialog() {
  installDialogOpen.value = false
}

function selectInstance(instanceId: string) {
  store.applyGenome(instanceId, genomeId.value).then(() => {
    closeInstallDialog()
    router.push({ path: `/instances/${instanceId}/genes` })
  })
}

const activeGeneContentRaw = computed(() => {
  const gene = geneMap.value[activeGeneTab.value]
  return (gene?.manifest as Record<string, any>)?.skill?.content ?? ''
})

function parseFrontmatter(content: string): { fm: string; body: string } {
  const trimmed = content.trimStart()
  if (!trimmed.startsWith('---')) return { fm: '', body: content }
  const closing = trimmed.indexOf('---', 3)
  if (closing === -1) return { fm: '', body: content }
  return {
    fm: trimmed.slice(3, closing).trim(),
    body: trimmed.slice(closing + 3).trimStart(),
  }
}

const activeGeneContentHtml = computed(() => {
  if (!activeGeneContentRaw.value) return ''
  const { fm, body } = parseFrontmatter(activeGeneContentRaw.value)
  const fmHtml = fm
    ? `<div class="not-prose mb-4 rounded-lg border border-border bg-muted/30 p-4"><div class="text-xs font-medium text-muted-foreground mb-2">${t('gene.frontmatterLabel')}</div><pre class="text-sm font-mono leading-relaxed text-foreground whitespace-pre-wrap">${fm.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre></div>`
    : ''
  return fmHtml + renderMarkdown(body)
})

const activeGeneDescription = computed(() => {
  return geneMap.value[activeGeneTab.value]?.description ?? ''
})

const contentViewMode = ref<'rendered' | 'source'>('rendered')

const activeGeneHasFrontmatter = computed(() => {
  const raw = activeGeneContentRaw.value
  return raw ? raw.trimStart().startsWith('---') : true
})

const iconMap: Record<string, typeof Package> = {
  code: Code,
  database: Database,
  cpu: Cpu,
  server: Server,
  shield: Shield,
  zap: Zap,
  wrench: Wrench,
  palette: Palette,
  message: MessageSquare,
  network: Network,
  sparkles: Sparkles,
  layers: Layers,
  package: Package,
}

function resolveIcon(iconName?: string) {
  if (!iconName) return Package
  const key = iconName.toLowerCase().replace(/[- ]/g, '')
  return iconMap[key] ?? iconMap[iconName] ?? Package
}

async function fetchGenesForSlugs(slugs: string[]) {
  const results = await Promise.all(
    slugs.map(async (slug) => {
      try {
        const res = await api.get('/genes', { params: { keyword: slug, page_size: 5 } })
        const genes: GeneItem[] = res.data.data || []
        return genes.find((g) => g.slug === slug) || null
      } catch {
        return null
      }
    }),
  )
  const map: Record<string, GeneItem> = {}
  for (const g of results) {
    if (g) map[g.slug] = g
  }
  geneMap.value = map
}

async function onMount() {
  await store.fetchGenome(genomeId.value)
  const slugs = genome.value?.gene_slugs
  if (slugs && slugs.length > 0) {
    activeGeneTab.value = slugs[0]!
    await fetchGenesForSlugs(slugs)
  }
}

onMounted(onMount)

function goBack() {
  router.push('/gene-market')
}

function goToGene(slug: string) {
  const gene = geneMap.value[slug]
  if (gene) {
    router.push(`/gene-market/gene/${gene.id}`)
  }
}
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-3.5rem)] bg-background text-foreground">
    <!-- 固定 header -->
    <div class="shrink-0 border-b border-border">
      <div class="max-w-4xl mx-auto px-6 pt-6 pb-4">
        <button
          class="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors mb-4"
          @click="goBack"
        >
          <ArrowLeft class="w-4 h-4" />
          {{ t('gene.backToMarket') }}
        </button>

        <div v-if="store.loading" class="flex justify-center py-4">
          <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
        </div>

        <div v-else-if="genome" class="flex items-center gap-4">
          <div class="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <component :is="resolveIcon(genome.icon)" class="w-6 h-6 text-primary" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 flex-wrap">
              <h1 class="text-xl font-bold">{{ genome.name }}</h1>
              <span
                v-if="genome.native_tool_count"
                class="shrink-0 inline-flex items-center gap-1 bg-cyan-500/10 text-cyan-400 text-xs px-2 py-0.5 rounded"
              >
                <Wrench class="w-3.5 h-3.5" />
                {{ t('genome.nativeToolCount', { count: genome.native_tool_count }) }}
              </span>
              <span
                v-if="genome.mcp_server_count"
                class="shrink-0 inline-flex items-center gap-1 bg-violet-500/10 text-violet-400 text-xs px-2 py-0.5 rounded"
              >
                <Server class="w-3.5 h-3.5" />
                {{ t('genome.mcpServerCount', { count: genome.mcp_server_count }) }}
              </span>
            </div>
          </div>
          <button
            class="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            @click="openInstallDialog"
          >
            <Download class="w-4 h-4" />
            {{ t('genome.learn') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 滚动内容区 -->
    <div class="flex-1 min-h-0 overflow-y-auto">
      <div class="max-w-4xl mx-auto px-6 pt-6 pb-8">
        <template v-if="!store.loading && genome">
          <section v-if="genome.description" class="mb-8">
            <h2 class="text-lg font-semibold mb-3">{{ t('gene.description') }}</h2>
            <p class="text-muted-foreground">{{ genome.description }}</p>
          </section>

          <section v-if="genome.gene_slugs?.length" class="mb-8">
            <h2 class="text-lg font-semibold mb-4">{{ t('genome.genesIncluded') }}</h2>
            <!-- Tab 栏 -->
            <div class="flex gap-0 border-b border-border mb-0 overflow-x-auto scrollbar-none">
              <button
                v-for="slug in genome.gene_slugs"
                :key="slug"
                :class="[
                  'shrink-0 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px',
                  activeGeneTab === slug
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border',
                ]"
                @click="activeGeneTab = slug"
              >
                {{ geneMap[slug]?.name ?? slug }}
              </button>
            </div>
            <!-- Tab 内容 -->
            <div class="rounded-b-xl border border-t-0 border-border bg-card p-6">
              <div v-if="activeGeneDescription" class="text-sm text-muted-foreground mb-4">
                {{ activeGeneDescription }}
              </div>
              <div v-if="activeGeneContentRaw" class="flex items-center justify-between mb-3">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-medium text-muted-foreground uppercase tracking-wider">SKILL.md</span>
                  <button
                    class="text-xs text-primary hover:underline"
                    @click="goToGene(activeGeneTab)"
                  >
                    {{ t('genome.viewDetail') }}
                  </button>
                </div>
                <div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
                  <button
                    :class="[
                      'p-1.5 rounded-md transition-colors',
                      contentViewMode === 'rendered' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
                    ]"
                    :title="t('gene.renderDocument')"
                    @click="contentViewMode = 'rendered'"
                  >
                    <FileText class="w-3.5 h-3.5" />
                  </button>
                  <button
                    :class="[
                      'p-1.5 rounded-md transition-colors',
                      contentViewMode === 'source' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
                    ]"
                    :title="t('gene.viewSource')"
                    @click="contentViewMode = 'source'"
                  >
                    <Code class="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div
                v-if="activeGeneContentRaw && !activeGeneHasFrontmatter"
                class="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 mb-3"
              >
                <div class="flex items-start gap-2">
                  <AlertTriangle class="w-4 h-4 text-amber-500 shrink-0 mt-0.5" />
                  <p class="text-xs text-muted-foreground">
                    {{ t('gene.frontmatterMissing') }}
                  </p>
                </div>
              </div>
              <div
                v-if="activeGeneContentRaw && contentViewMode === 'rendered'"
                class="prose prose-sm prose-invert max-w-none prose-a:text-primary"
                v-html="activeGeneContentHtml"
              />
              <pre
                v-else-if="activeGeneContentRaw && contentViewMode === 'source'"
                class="text-sm font-mono leading-relaxed text-foreground overflow-x-auto whitespace-pre-wrap wrap-break-word"
              >{{ activeGeneContentRaw }}</pre>
              <div v-else class="py-8 text-center text-sm text-muted-foreground">
                {{ t('genome.noGeneContent') }}
              </div>
            </div>
          </section>

          <section class="mb-8">
            <h2 class="text-lg font-semibold mb-3">{{ t('gene.rating') }}</h2>
            <div class="flex items-center gap-6">
              <div class="flex items-center gap-1">
                <Star
                  v-for="i in 5"
                  :key="i"
                  :class="[
                    'w-5 h-5',
                    i <= Math.round(genome.avg_rating ?? 0)
                      ? 'fill-amber-400 text-amber-400'
                      : 'text-muted',
                  ]"
                />
                <span class="ml-2 text-sm text-muted-foreground">
                  {{ (genome.avg_rating ?? 0).toFixed(1) }}
                </span>
              </div>
            </div>
          </section>
        </template>

        <div v-else-if="!store.loading" class="py-20 text-center text-muted-foreground">
          {{ t('genome.notFound') }}
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="installDialogOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="closeInstallDialog"
      >
        <div
          class="w-full max-w-md mx-4 rounded-xl border border-border bg-card p-6 shadow-lg"
          @click.stop
        >
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-semibold">{{ t('genome.selectInstance') }}</h3>
            <button
              class="p-1.5 rounded-lg hover:bg-muted transition-colors"
              @click="closeInstallDialog"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <p class="text-sm text-muted-foreground mb-4">
            {{ t('genome.selectInstanceHint', { name: genome?.name ?? '' }) }}
          </p>
          <div v-if="instancesLoading" class="flex justify-center py-8">
            <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
          <div v-else class="max-h-72 overflow-y-auto space-y-1.5">
            <div v-if="instances.length === 0" class="text-sm text-muted-foreground py-4 text-center">
              {{ t('gene.noAvailableInstances') }}
            </div>
            <button
              v-for="inst in instances"
              :key="inst.id"
              :disabled="inst.status !== 'running' && inst.status !== 'learning'"
              :class="[
                'w-full flex items-center gap-3 px-4 py-3 rounded-lg border transition text-left',
                inst.status === 'running' || inst.status === 'learning'
                  ? 'border-border bg-background hover:border-emerald-300 hover:bg-emerald-50/30 dark:hover:bg-emerald-950/20 cursor-pointer'
                  : 'border-border bg-muted/30 text-muted-foreground cursor-not-allowed opacity-60',
              ]"
              @click="(inst.status === 'running' || inst.status === 'learning') && selectInstance(inst.id)"
            >
              <span
                :class="['w-2 h-2 rounded-full shrink-0', getStatusConfig(inst.status).dot]"
              />
              <div class="flex items-center gap-2 min-w-0 flex-1">
                <span class="font-medium text-sm truncate">{{ inst.name }}</span>
                <div v-if="inst.slug" class="group/slug relative max-w-[50%] flex items-center">
                  <span class="text-[11px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground truncate block">{{ inst.slug }}</span>
                  <button
                    class="ml-0.5 p-0.5 rounded opacity-0 group-hover/slug:opacity-100 transition-opacity text-muted-foreground hover:text-foreground shrink-0"
                    @click.stop="copySlug(inst.slug)"
                  >
                    <Check v-if="copiedSlug === inst.slug" class="w-3 h-3 text-emerald-500" />
                    <Copy v-else class="w-3 h-3" />
                  </button>
                </div>
              </div>
              <span
                :class="[
                  'text-xs shrink-0 px-2 py-0.5 rounded-full',
                  getStatusConfig(inst.status).text,
                  getStatusConfig(inst.status).bg,
                ]"
              >
                {{ getStatusLabel(inst.status) }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
