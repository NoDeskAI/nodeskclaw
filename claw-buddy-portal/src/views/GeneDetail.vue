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
  Download,
  ExternalLink,
  X,
  AlertTriangle,
  FileText,
  Copy,
  Check,
} from 'lucide-vue-next'
import { marked } from 'marked'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem, GenomeItem } from '@/stores/gene'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const store = useGeneStore()

const geneId = computed(() => route.params.id as string)
const gene = computed(() => store.currentGene)
const synergies = ref<GeneItem[]>([])
const variants = ref<GeneItem[]>([])
const parentGenomes = ref<GenomeItem[]>([])
const installDialogOpen = ref(false)
const instances = ref<{ id: string; name: string; slug: string; status: string }[]>([])
const instancesLoading = ref(false)
const installedInstanceIds = ref<Set<string>>(new Set())

const statusConfig: Record<string, { label: string; dot: string; text: string; bg: string }> = {
  running: { label: '运行中', dot: 'bg-emerald-500', text: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-950/40' },
  learning: { label: '学习中', dot: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/40' },
  creating: { label: '创建中', dot: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/40' },
  pending: { label: '等待中', dot: 'bg-yellow-500', text: 'text-yellow-600 dark:text-yellow-400', bg: 'bg-yellow-50 dark:bg-yellow-950/40' },
  deploying: { label: '部署中', dot: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-950/40' },
  updating: { label: '更新中', dot: 'bg-amber-500', text: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-950/40' },
  failed: { label: '失败', dot: 'bg-red-500', text: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-950/40' },
  deleting: { label: '删除中', dot: 'bg-gray-400', text: 'text-gray-500 dark:text-gray-400', bg: 'bg-gray-50 dark:bg-gray-950/40' },
}

function getStatusConfig(status: string) {
  return statusConfig[status] ?? { label: status, dot: 'bg-gray-400', text: 'text-gray-500 dark:text-gray-400', bg: 'bg-gray-50 dark:bg-gray-950/40' }
}

const availableInstances = computed(() =>
  instances.value.filter(i => !installedInstanceIds.value.has(i.id))
)
const installedInstances = computed(() =>
  instances.value.filter(i => installedInstanceIds.value.has(i.id))
)

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

const descriptionHtml = computed(() => {
  const d = gene.value?.description
  if (!d) return ''
  return marked(d) as string
})

const skillContentRaw = computed(() => {
  return (gene.value?.manifest as Record<string, any>)?.skill?.content ?? ''
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

const skillContentHtml = computed(() => {
  if (!skillContentRaw.value) return ''
  const { fm, body } = parseFrontmatter(skillContentRaw.value)
  const fmHtml = fm
    ? `<div class="not-prose mb-4 rounded-lg border border-border bg-muted/30 p-4"><div class="text-xs font-medium text-muted-foreground mb-2">YAML Frontmatter</div><pre class="text-sm font-mono leading-relaxed text-foreground whitespace-pre-wrap">${fm.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre></div>`
    : ''
  return fmHtml + (marked(body) as string)
})

const contentViewMode = ref<'rendered' | 'source'>('rendered')

const hasFrontmatter = computed(() => {
  const raw = skillContentRaw.value
  return raw ? raw.trimStart().startsWith('---') : true
})

async function onMount() {
  await store.fetchGene(geneId.value)
  const [s, v, pg] = await Promise.all([
    store.fetchGeneSynergies(geneId.value),
    store.fetchGeneVariants(geneId.value),
    store.fetchGeneGenomes(geneId.value),
  ])
  synergies.value = s
  variants.value = v
  parentGenomes.value = pg
}

onMounted(onMount)

function goBack() {
  router.push('/gene-market')
}

function goToGene(id: string) {
  router.push(`/gene-market/gene/${id}`)
}

function openInstallDialog() {
  installDialogOpen.value = true
  instancesLoading.value = true
  installedInstanceIds.value = new Set()

  const fetchInstances = api.get('/instances').then((res) => {
    instances.value = (res.data.data || []).map((i: { id: string; name: string; slug: string; status: string }) => ({
      id: i.id,
      name: i.name,
      slug: i.slug,
      status: i.status,
    }))
  }).catch(() => {
    instances.value = []
  })

  const fetchInstalled = api.get(`/genes/${geneId.value}/installed-instances`).then((res) => {
    installedInstanceIds.value = new Set(res.data.data || [])
  }).catch(() => {
    installedInstanceIds.value = new Set()
  })

  Promise.all([fetchInstances, fetchInstalled]).finally(() => {
    instancesLoading.value = false
  })
}

function closeInstallDialog() {
  installDialogOpen.value = false
}

function goToInstanceGenes(instanceId: string) {
  router.push({
    path: `/instances/${instanceId}/genes`,
    query: { focus_gene_id: geneId.value },
  })
}

const copiedSlug = ref<string | null>(null)
async function copySlug(slug: string) {
  try {
    await navigator.clipboard.writeText(slug)
    copiedSlug.value = slug
    setTimeout(() => { copiedSlug.value = null }, 1500)
  } catch { /* ignore */ }
}

function selectInstance(instanceId: string) {
  const slug = gene.value?.slug
  if (!slug) return
  store.installGene(instanceId, slug).then(() => {
    closeInstallDialog()
    goToInstanceGenes(instanceId)
  })
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

        <div v-else-if="gene" class="flex items-center gap-4">
          <div class="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <component :is="resolveIcon(gene.icon)" class="w-6 h-6 text-primary" />
          </div>
          <div class="min-w-0 flex-1">
            <h1 class="text-xl font-bold">{{ gene.name }}</h1>
            <div class="flex flex-wrap gap-2 mt-1">
              <span class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">v{{ gene.version }}</span>
              <span class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{{ gene.source }}</span>
              <span v-if="gene.category" class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{{ gene.category }}</span>
            </div>
          </div>
          <button
            class="shrink-0 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            @click="openInstallDialog"
          >
            <Download class="w-4 h-4" />
            学习
          </button>
        </div>
      </div>
    </div>

    <!-- 滚动内容区 -->
    <div class="flex-1 min-h-0 overflow-y-auto">
      <div class="max-w-4xl mx-auto px-6 pt-6 pb-8">
        <template v-if="!store.loading && gene">
          <div v-if="gene.tags?.length" class="flex flex-wrap gap-2 mb-6">
            <span
              v-for="tag in gene.tags"
              :key="tag"
              class="text-xs px-2.5 py-1 rounded-lg bg-primary/10 text-primary"
            >
              {{ tag }}
            </span>
          </div>

          <section v-if="gene.description" class="mb-8">
            <h2 class="text-lg font-semibold mb-3">描述</h2>
            <div
              class="prose prose-sm max-w-none text-foreground prose-headings:text-foreground prose-p:text-foreground prose-a:text-primary"
              v-html="descriptionHtml"
            />
          </section>

          <section v-if="skillContentRaw" class="mb-8">
            <div class="flex items-center justify-between mb-3">
              <h2 class="text-lg font-semibold">基因内容</h2>
              <div class="flex items-center gap-1 rounded-lg border border-border p-0.5">
                <button
                  :class="[
                    'p-1.5 rounded-md transition-colors',
                    contentViewMode === 'rendered' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
                  ]"
                  title="渲染文档"
                  @click="contentViewMode = 'rendered'"
                >
                  <FileText class="w-4 h-4" />
                </button>
                <button
                  :class="[
                    'p-1.5 rounded-md transition-colors',
                    contentViewMode === 'source' ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground',
                  ]"
                  title="查看源码"
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
                <p class="text-xs text-muted-foreground">
                  此基因内容缺少 YAML frontmatter，安装时将强制深度学习由 Agent 自主生成完整内容，部分元数据（如 always、requires 等）可能需要 Agent 补全
                </p>
              </div>
            </div>
            <div
              v-if="contentViewMode === 'rendered'"
              class="rounded-xl border border-border bg-card p-6 prose prose-sm prose-invert max-w-none prose-a:text-primary"
              v-html="skillContentHtml"
            />
            <pre
              v-else
              class="rounded-xl border border-border bg-card p-6 text-sm font-mono leading-relaxed text-foreground overflow-x-auto whitespace-pre-wrap wrap-break-word"
            >{{ skillContentRaw }}</pre>
          </section>

          <section v-if="parentGenomes.length" class="mb-8">
            <h2 class="text-lg font-semibold mb-3">所属基因组</h2>
            <div class="flex gap-4 overflow-x-auto pb-2 -mx-1">
              <div
                v-for="g in parentGenomes"
                :key="g.id"
                class="shrink-0 w-48 p-4 rounded-xl border border-border bg-card hover:border-primary/30 transition cursor-pointer"
                @click="router.push(`/gene-market/genome/${g.id}`)"
              >
                <div class="font-medium truncate mb-1">{{ g.name }}</div>
                <p class="text-xs text-muted-foreground line-clamp-2">
                  {{ g.short_description ?? g.description ?? '' }}
                </p>
              </div>
            </div>
          </section>

          <section v-if="synergies.length" class="mb-8">
            <h2 class="text-lg font-semibold mb-3">推荐搭配</h2>
            <div class="flex gap-4 overflow-x-auto pb-2 -mx-1">
              <div
                v-for="s in synergies"
                :key="s.id"
                class="shrink-0 w-48 p-4 rounded-xl border border-border bg-card hover:border-primary/30 transition cursor-pointer"
                @click="goToGene(s.id)"
              >
                <div class="flex items-center gap-2 mb-1">
                  <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                    <component :is="resolveIcon(s.icon)" class="w-4 h-4 text-primary" />
                  </div>
                  <span class="font-medium truncate">{{ s.name }}</span>
                </div>
                <p class="text-xs text-muted-foreground line-clamp-2">
                  {{ s.short_description ?? s.description ?? '' }}
                </p>
              </div>
            </div>
          </section>

          <section v-if="variants.length" class="mb-8">
            <h2 class="text-lg font-semibold mb-3">Agent 进化版本</h2>
            <div class="space-y-3">
              <div
                v-for="v in variants"
                :key="v.id"
                class="p-4 rounded-xl border border-border bg-card hover:border-primary/30 transition cursor-pointer"
                @click="goToGene(v.id)"
              >
                <div class="flex items-center justify-between gap-4">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-9 h-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                      <component :is="resolveIcon(v.icon)" class="w-4 h-4 text-primary" />
                    </div>
                    <div>
                      <div class="font-medium truncate">{{ v.name }}</div>
                      <div class="text-xs text-muted-foreground">v{{ v.version }}</div>
                    </div>
                  </div>
                  <div class="w-24 shrink-0">
                    <div class="h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        class="h-full rounded-full bg-primary/60"
                        :style="{ width: `${Math.min(100, (v.effectiveness_score ?? 0) * 100)}%` }"
                      />
                    </div>
                  </div>
                </div>
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
                    i <= Math.round(gene.avg_rating ?? 0)
                      ? 'fill-amber-400 text-amber-400'
                      : 'text-muted',
                  ]"
                />
                <span class="ml-2 text-sm text-muted-foreground">
                  {{ (gene.avg_rating ?? 0).toFixed(1) }}
                </span>
              </div>
              <div class="flex-1 min-w-0 max-w-xs">
                <div class="text-xs text-muted-foreground mb-1">效能评分</div>
                <div class="h-2 rounded-full bg-muted overflow-hidden">
                  <div
                    class="h-full rounded-full bg-primary/60"
                    :style="{ width: `${Math.min(100, (gene.effectiveness_score ?? 0) * 100)}%` }"
                  />
                </div>
              </div>
            </div>
          </section>
        </template>

        <div v-else-if="!store.loading" class="py-20 text-center text-muted-foreground">
          未找到该基因
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
            <h3 class="text-lg font-semibold">选择实例</h3>
            <button
              class="p-1.5 rounded-lg hover:bg-muted transition-colors"
              @click="closeInstallDialog"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <p class="text-sm text-muted-foreground mb-4">
            选择要学习基因 {{ gene?.slug }} 的实例
          </p>
          <div v-if="instancesLoading" class="flex justify-center py-8">
            <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
          <div v-else class="max-h-72 overflow-y-auto space-y-4">
            <div v-if="instances.length === 0" class="text-sm text-muted-foreground py-4 text-center">
              暂无可用实例
            </div>
            <template v-else>
              <!-- 可学习 -->
              <div v-if="availableInstances.length > 0">
                <p class="text-xs text-muted-foreground mb-2 px-1">可学习</p>
                <div class="space-y-1.5">
                  <button
                    v-for="inst in availableInstances"
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
                        <div class="absolute left-1/2 -translate-x-1/2 top-full mt-1.5 px-2 py-1 rounded bg-popover border border-border text-xs text-popover-foreground shadow-md whitespace-nowrap opacity-0 group-hover/slug:opacity-100 transition-opacity pointer-events-none z-10">
                          {{ inst.slug }}
                        </div>
                      </div>
                    </div>
                    <span
                      :class="[
                        'text-xs shrink-0 px-2 py-0.5 rounded-full',
                        getStatusConfig(inst.status).text,
                        getStatusConfig(inst.status).bg,
                      ]"
                    >
                      {{ getStatusConfig(inst.status).label }}
                    </span>
                  </button>
                </div>
              </div>
              <!-- 已学习 -->
              <div v-if="installedInstances.length > 0">
                <p class="text-xs text-muted-foreground mb-2 px-1">已学习</p>
                <div class="space-y-1.5">
                  <div
                    v-for="inst in installedInstances"
                    :key="inst.id"
                    class="w-full flex items-center gap-3 px-4 py-3 rounded-lg border border-border bg-muted/20"
                  >
                    <span
                      :class="['w-2 h-2 rounded-full shrink-0', getStatusConfig(inst.status).dot]"
                    />
                    <div class="flex items-center gap-2 min-w-0 flex-1">
                      <div class="flex items-center gap-1 min-w-0">
                        <span class="font-medium text-sm truncate">{{ inst.name }}</span>
                        <button
                          class="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors shrink-0"
                          title="查看实例基因"
                          aria-label="查看实例基因"
                          @click.stop="goToInstanceGenes(inst.id)"
                        >
                          <ExternalLink class="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <div v-if="inst.slug" class="group/slug relative max-w-[50%] flex items-center">
                        <span class="text-[11px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground truncate block">{{ inst.slug }}</span>
                        <button
                          class="ml-0.5 p-0.5 rounded opacity-0 group-hover/slug:opacity-100 transition-opacity text-muted-foreground hover:text-foreground shrink-0"
                          @click.stop="copySlug(inst.slug)"
                        >
                          <Check v-if="copiedSlug === inst.slug" class="w-3 h-3 text-emerald-500" />
                          <Copy v-else class="w-3 h-3" />
                        </button>
                        <div class="absolute left-1/2 -translate-x-1/2 top-full mt-1.5 px-2 py-1 rounded bg-popover border border-border text-xs text-popover-foreground shadow-md whitespace-nowrap opacity-0 group-hover/slug:opacity-100 transition-opacity pointer-events-none z-10">
                          {{ inst.slug }}
                        </div>
                      </div>
                    </div>
                    <span class="text-xs shrink-0 px-2 py-0.5 rounded-full text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-950/40">
                      已学习
                    </span>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
