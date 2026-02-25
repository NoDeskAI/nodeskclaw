<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
} from 'lucide-vue-next'
import { marked } from 'marked'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem } from '@/stores/gene'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const store = useGeneStore()

const genomeId = computed(() => route.params.id as string)
const genome = computed(() => store.currentGenome)
const geneMap = ref<Record<string, GeneItem>>({})
const activeGeneTab = ref<string>('')

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
    ? `<div class="not-prose mb-4 rounded-lg border border-border bg-muted/30 p-4"><div class="text-xs font-medium text-muted-foreground mb-2">YAML Frontmatter</div><pre class="text-sm font-mono leading-relaxed text-foreground whitespace-pre-wrap">${fm.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre></div>`
    : ''
  return fmHtml + (marked(body) as string)
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
          返回基因市场
        </button>

        <div v-if="store.loading" class="flex justify-center py-4">
          <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
        </div>

        <div v-else-if="genome" class="flex items-center gap-4">
          <div class="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <component :is="resolveIcon(genome.icon)" class="w-6 h-6 text-primary" />
          </div>
          <div class="min-w-0 flex-1">
            <h1 class="text-xl font-bold">{{ genome.name }}</h1>
          </div>
          <button
            class="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Check class="w-4 h-4" />
            应用
          </button>
        </div>
      </div>
    </div>

    <!-- 滚动内容区 -->
    <div class="flex-1 min-h-0 overflow-y-auto">
      <div class="max-w-4xl mx-auto px-6 pt-6 pb-8">
        <template v-if="!store.loading && genome">
          <section v-if="genome.description" class="mb-8">
            <h2 class="text-lg font-semibold mb-3">描述</h2>
            <p class="text-muted-foreground">{{ genome.description }}</p>
          </section>

          <section v-if="genome.gene_slugs?.length" class="mb-8">
            <h2 class="text-lg font-semibold mb-4">包含基因</h2>
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
                    查看详情
                  </button>
                </div>
                <div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
                  <button
                    :class="[
                      'p-1.5 rounded-md transition-colors',
                      contentViewMode === 'rendered' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
                    ]"
                    title="渲染文档"
                    @click="contentViewMode = 'rendered'"
                  >
                    <FileText class="w-3.5 h-3.5" />
                  </button>
                  <button
                    :class="[
                      'p-1.5 rounded-md transition-colors',
                      contentViewMode === 'source' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
                    ]"
                    title="查看源码"
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
                    此基因内容缺少 YAML frontmatter，安装时将强制深度学习由 Agent 自主生成完整内容，部分元数据（如 always、requires 等）可能需要 Agent 补全
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
                暂无基因内容
              </div>
            </div>
          </section>

          <section class="mb-8">
            <h2 class="text-lg font-semibold mb-3">评分</h2>
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
          未找到该基因组
        </div>
      </div>
    </div>
  </div>
</template>
