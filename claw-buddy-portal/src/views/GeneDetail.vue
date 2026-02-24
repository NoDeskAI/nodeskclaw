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
  X,
} from 'lucide-vue-next'
import { marked } from 'marked'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem } from '@/stores/gene'
import api from '@/services/api'

const route = useRoute()
const router = useRouter()
const store = useGeneStore()

const geneId = computed(() => route.params.id as string)
const gene = computed(() => store.currentGene)
const synergies = ref<GeneItem[]>([])
const variants = ref<GeneItem[]>([])
const installDialogOpen = ref(false)
const instances = ref<{ id: string; name: string; status: string }[]>([])
const instancesLoading = ref(false)

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

async function onMount() {
  await store.fetchGene(geneId.value)
  const [s, v] = await Promise.all([
    store.fetchGeneSynergies(geneId.value),
    store.fetchGeneVariants(geneId.value),
  ])
  synergies.value = s
  variants.value = v
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
  api
    .get('/instances')
    .then((res) => {
      instances.value = (res.data.data || []).map((i: { id: string; name: string; status: string }) => ({
        id: i.id,
        name: i.name,
        status: i.status,
      }))
    })
    .catch(() => {
      instances.value = []
    })
    .finally(() => {
      instancesLoading.value = false
    })
}

function closeInstallDialog() {
  installDialogOpen.value = false
}

function selectInstance(instanceId: string) {
  const slug = gene.value?.slug
  if (!slug) return
  store.installGene(instanceId, slug).then(() => {
    closeInstallDialog()
    router.push(`/instances/${instanceId}`)
  })
}
</script>

<template>
  <div class="min-h-screen bg-background text-foreground">
    <div class="max-w-4xl mx-auto px-6 py-8">
      <button
        class="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors mb-6"
        @click="goBack"
      >
        <ArrowLeft class="w-4 h-4" />
        返回基因市场
      </button>

      <div v-if="store.loading" class="flex justify-center py-20">
        <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
      </div>

      <template v-else-if="gene">
        <header class="flex items-start gap-4 mb-6">
          <div
            class="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center shrink-0"
          >
            <component :is="resolveIcon(gene.icon)" class="w-7 h-7 text-primary" />
          </div>
          <div class="min-w-0 flex-1">
            <h1 class="text-2xl font-bold">{{ gene.name }}</h1>
            <div class="flex flex-wrap gap-2 mt-2">
              <span
                class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground"
              >
                v{{ gene.version }}
              </span>
              <span
                class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground"
              >
                {{ gene.source }}
              </span>
              <span
                v-if="gene.category"
                class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground"
              >
                {{ gene.category }}
              </span>
            </div>
          </div>
        </header>

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
              <div class="text-xs text-muted-foreground mb-1">效能</div>
              <div class="h-2 rounded-full bg-muted overflow-hidden">
                <div
                  class="h-full rounded-full bg-primary/60"
                  :style="{ width: `${Math.min(100, (gene.effectiveness_score ?? 0) * 100)}%` }"
                />
              </div>
            </div>
          </div>
        </section>

        <div>
          <button
            class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            @click="openInstallDialog"
          >
            <Download class="w-4 h-4" />
            安装 ({{ gene.slug }})
          </button>
        </div>
      </template>

      <div v-else class="py-20 text-center text-muted-foreground">
        未找到该基因
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
            选择要安装基因 {{ gene?.slug }} 的实例
          </p>
          <div v-if="instancesLoading" class="flex justify-center py-8">
            <Loader2 class="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
          <div v-else class="space-y-2 max-h-64 overflow-y-auto">
            <button
              v-for="inst in instances"
              :key="inst.id"
              :disabled="inst.status !== 'running'"
              :class="[
                'w-full flex items-center justify-between px-4 py-3 rounded-lg border transition text-left',
                inst.status === 'running'
                  ? 'border-border bg-background hover:border-primary/30 cursor-pointer'
                  : 'border-border bg-muted/30 text-muted-foreground cursor-not-allowed',
              ]"
              @click="inst.status === 'running' && selectInstance(inst.id)"
            >
              <span class="font-medium truncate">{{ inst.name }}</span>
              <span class="text-xs shrink-0 ml-2">{{ inst.status === 'running' ? '运行中' : inst.status }}</span>
            </button>
            <p v-if="!instancesLoading && instances.length === 0" class="text-sm text-muted-foreground py-4 text-center">
              暂无可用实例
            </p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
