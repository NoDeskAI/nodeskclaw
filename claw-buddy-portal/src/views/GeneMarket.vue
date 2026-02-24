<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  Search,
  Loader2,
  ChevronDown,
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
} from 'lucide-vue-next'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem, GenomeItem } from '@/stores/gene'

const router = useRouter()
const store = useGeneStore()

const viewMode = ref<'genes' | 'genomes'>('genes')
const keyword = ref('')
const selectedTag = ref<string | null>(null)
const selectedCategory = ref<string | null>(null)
const sortBy = ref('popularity')
const page = ref(1)
const pageSize = ref(12)

const categories = [
  { value: '开发', label: '开发' },
  { value: '数据', label: '数据' },
  { value: '运维', label: '运维' },
  { value: '网络', label: '网络' },
  { value: '创意', label: '创意' },
  { value: '沟通', label: '沟通' },
  { value: '安全', label: '安全' },
  { value: '效率', label: '效率' },
]

const sortOptions = [
  { value: 'popularity', label: '热门' },
  { value: 'rating', label: '评分' },
  { value: 'effectiveness', label: '效能' },
  { value: 'newest', label: '最新' },
]

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

const featuredItems = computed(() =>
  viewMode.value === 'genes' ? store.featuredGenes : store.featuredGenomes,
)

const hasFeatured = computed(() => featuredItems.value.length > 0)

const totalCount = computed(() =>
  viewMode.value === 'genes' ? store.totalGenes : store.totalGenomes,
)

const totalPages = computed(() => Math.ceil(totalCount.value / pageSize.value) || 1)
const canPrev = computed(() => page.value > 1)
const canNext = computed(() => page.value < totalPages.value)

async function loadData() {
  if (viewMode.value === 'genes') {
    await store.fetchGenes({
      keyword: keyword.value || undefined,
      tag: selectedTag.value || undefined,
      category: selectedCategory.value || undefined,
      sort: sortBy.value,
      page: page.value,
      page_size: pageSize.value,
    })
  } else {
    await store.fetchGenomes({
      keyword: keyword.value || undefined,
      page: page.value,
      page_size: pageSize.value,
    })
  }
}

async function loadFeatured() {
  if (viewMode.value === 'genes') {
    await store.fetchFeaturedGenes()
  } else {
    await store.fetchFeaturedGenomes()
  }
}

async function onMount() {
  await store.fetchGeneTags()
  await loadFeatured()
  await loadData()
}

onMounted(onMount)

watch([viewMode, keyword, selectedTag, selectedCategory, sortBy], () => {
  page.value = 1
  loadFeatured()
  loadData()
})

watch(page, loadData)

function goToGene(id: string) {
  router.push(`/gene-market/gene/${id}`)
}

function goToGenome(id: string) {
  router.push(`/gene-market/genome/${id}`)
}

</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <div class="max-w-6xl mx-auto px-6 py-8">
      <h1 class="text-2xl font-bold mb-6">基因市场</h1>

      <div class="flex flex-wrap items-center gap-2 mb-4">
        <button
          :class="[
            'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            viewMode === 'genes'
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted',
          ]"
          @click="viewMode = 'genes'"
        >
          基因
        </button>
        <button
          :class="[
            'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
            viewMode === 'genomes'
              ? 'bg-primary/10 text-primary'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted',
          ]"
          @click="viewMode = 'genomes'"
        >
          基因组
        </button>
      </div>

      <div class="flex flex-wrap gap-3 mb-6">
        <div class="relative flex-1 min-w-[200px]">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            v-model="keyword"
            type="text"
            placeholder="搜索关键词"
            class="w-full pl-10 pr-4 py-2 rounded-lg border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        <div v-if="viewMode === 'genes'" class="flex flex-wrap gap-2">
          <button
            v-for="t in store.tagStats"
            :key="t.tag"
            :class="[
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              selectedTag === t.tag
                ? 'bg-primary/10 text-primary'
                : 'bg-muted/50 text-muted-foreground hover:text-foreground hover:bg-muted',
            ]"
            @click="selectedTag = selectedTag === t.tag ? null : t.tag"
          >
            {{ t.tag }}
          </button>
        </div>

        <div v-if="viewMode === 'genes'" class="relative">
          <select
            v-model="selectedCategory"
            class="appearance-none pl-4 pr-10 py-2 rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
          >
            <option :value="null">全部分类</option>
            <option v-for="c in categories" :key="c.value" :value="c.value">
              {{ c.label }}
            </option>
          </select>
          <ChevronDown class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        </div>

        <div class="relative">
          <select
            v-model="sortBy"
            class="appearance-none pl-4 pr-10 py-2 rounded-lg border border-border bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 cursor-pointer"
          >
            <option v-for="s in sortOptions" :key="s.value" :value="s.value">
              {{ s.label }}
            </option>
          </select>
          <ChevronDown class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
        </div>
      </div>

      <div v-if="store.loading" class="flex justify-center py-20">
        <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
      </div>

      <template v-else>
        <section v-if="hasFeatured" class="mb-8">
          <h2 class="text-lg font-semibold mb-4">精选</h2>
          <div class="flex gap-4 overflow-x-auto pb-2 -mx-1 scrollbar-thin">
            <div
              v-for="item in featuredItems"
              :key="item.id"
              class="shrink-0 w-64 p-4 rounded-xl border border-border bg-card hover:border-primary/30 transition cursor-pointer"
              @click="viewMode === 'genes' ? goToGene((item as GeneItem).id) : goToGenome((item as GenomeItem).id)"
            >
              <div class="flex items-start gap-3 mb-2">
                <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <component
                    :is="resolveIcon((item as GeneItem).icon ?? (item as GenomeItem).icon)"
                    class="w-5 h-5 text-primary"
                  />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="font-medium truncate">{{ item.name }}</div>
                  <p class="text-xs text-muted-foreground line-clamp-2 mt-0.5">
                    {{ (item as GeneItem).short_description ?? (item as GenomeItem).short_description ?? '' }}
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-2 text-xs text-muted-foreground">
                <span class="flex items-center gap-0.5">
                  <Star class="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                  {{ ((item as GeneItem).avg_rating ?? (item as GenomeItem).avg_rating ?? 0).toFixed(1) }}
                </span>
                <span>{{ (item as GeneItem).install_count ?? (item as GenomeItem).install_count ?? 0 }} 安装</span>
              </div>
            </div>
          </div>
        </section>

        <section>
          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            <template v-if="viewMode === 'genes'">
              <div
                v-for="gene in store.genes"
                :key="gene.id"
                class="p-4 rounded-xl border border-border bg-card hover:border-primary/30 transition cursor-pointer"
                @click="goToGene(gene.id)"
              >
              <div class="flex items-start gap-3 mb-2">
                <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <component :is="resolveIcon(gene.icon)" class="w-5 h-5 text-primary" />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="font-medium truncate">{{ gene.name }}</span>
                    <span class="shrink-0 text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                      v{{ gene.version }}
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
                  class="text-xs px-2 py-0.5 rounded bg-primary/10 text-primary"
                >
                  {{ tag }}
                </span>
              </div>
              <div class="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
                <span class="flex items-center gap-0.5">
                  <Star class="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                  {{ (gene.avg_rating ?? 0).toFixed(1) }}
                </span>
                <div class="flex-1 min-w-0">
                  <div class="h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      class="h-full rounded-full bg-primary/60"
                      :style="{ width: `${Math.min(100, (gene.effectiveness_score ?? 0) * 100)}%` }"
                    />
                  </div>
                </div>
                <span class="shrink-0">{{ gene.install_count ?? 0 }} 安装</span>
              </div>
              </div>
            </template>
            <template v-else>
              <div
                v-for="genome in store.genomes"
                :key="genome.id"
                class="p-4 rounded-xl border border-border bg-card hover:border-primary/30 transition cursor-pointer"
                @click="goToGenome(genome.id)"
              >
              <div class="flex items-start gap-3 mb-2">
                <div class="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <component :is="resolveIcon(genome.icon)" class="w-5 h-5 text-primary" />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="font-medium truncate">{{ genome.name }}</div>
                  <p class="text-xs text-muted-foreground line-clamp-2 mt-1">
                    {{ genome.short_description ?? genome.description ?? '' }}
                  </p>
                </div>
              </div>
              <div class="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
                <span class="flex items-center gap-0.5">
                  <Star class="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                  {{ (genome.avg_rating ?? 0).toFixed(1) }}
                </span>
                <span class="shrink-0">{{ genome.install_count ?? 0 }} 安装</span>
              </div>
            </div>
            </template>
          </div>
        </section>

        <div
          v-if="totalPages > 1"
          class="flex items-center justify-center gap-2 mt-8"
        >
          <button
            :disabled="!canPrev"
            :class="[
              'px-3 py-1.5 rounded-lg text-sm transition-colors',
              canPrev
                ? 'text-foreground hover:bg-muted'
                : 'text-muted-foreground cursor-not-allowed',
            ]"
            @click="page = Math.max(1, page - 1)"
          >
            上一页
          </button>
          <span class="text-sm text-muted-foreground">
            {{ page }} / {{ totalPages }}
          </span>
          <button
            :disabled="!canNext"
            :class="[
              'px-3 py-1.5 rounded-lg text-sm transition-colors',
              canNext
                ? 'text-foreground hover:bg-muted'
                : 'text-muted-foreground cursor-not-allowed',
            ]"
            @click="page = Math.min(totalPages, page + 1)"
          >
            下一页
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
