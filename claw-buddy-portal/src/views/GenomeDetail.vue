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
} from 'lucide-vue-next'
import { useGeneStore } from '@/stores/gene'

const route = useRoute()
const router = useRouter()
const store = useGeneStore()

const genomeId = computed(() => route.params.id as string)
const genome = computed(() => store.currentGenome)

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

async function onMount() {
  await store.fetchGenome(genomeId.value)
}

onMounted(onMount)

function goBack() {
  router.push('/gene-market')
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

      <template v-else-if="genome">
        <header class="flex items-start gap-4 mb-6">
          <div
            class="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center shrink-0"
          >
            <component :is="resolveIcon(genome.icon)" class="w-7 h-7 text-primary" />
          </div>
          <div class="min-w-0 flex-1">
            <h1 class="text-2xl font-bold">{{ genome.name }}</h1>
          </div>
        </header>

        <section v-if="genome.description" class="mb-8">
          <h2 class="text-lg font-semibold mb-3">描述</h2>
          <p class="text-muted-foreground">{{ genome.description }}</p>
        </section>

        <section v-if="genome.gene_slugs?.length" class="mb-8">
          <h2 class="text-lg font-semibold mb-3">包含基因</h2>
          <div class="flex flex-wrap gap-3">
            <div
              v-for="slug in genome.gene_slugs"
              :key="slug"
              class="px-4 py-3 rounded-xl border border-border bg-card"
            >
              {{ slug }}
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

        <div>
          <button
            class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Check class="w-4 h-4" />
            应用
          </button>
        </div>
      </template>

      <div v-else class="py-20 text-center text-muted-foreground">
        未找到该基因组
      </div>
    </div>
  </div>
</template>
