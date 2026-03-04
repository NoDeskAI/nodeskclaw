<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft,
  Loader2,
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
  Dna,
  Pencil,
  Trash2,
} from 'lucide-vue-next'
import { useGeneStore } from '@/stores/gene'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'

const route = useRoute()
const router = useRouter()
const store = useGeneStore()
const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()

const templateId = computed(() => route.params.id as string)
const tpl = computed(() => store.currentTemplate)
const deleting = ref(false)

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

onMounted(() => {
  store.fetchTemplate(templateId.value)
})

function useThisTemplate() {
  router.push({ name: 'CreateInstance', query: { template_id: templateId.value } })
}

async function handleDelete() {
  const ok = await confirm({
    description: t('template.deleteConfirm'),
    variant: 'danger',
  })
  if (!ok) return
  deleting.value = true
  try {
    await store.deleteTemplate(templateId.value)
    toast.success(t('template.deleted'))
    router.push('/gene-market')
  } catch {
    toast.error(t('template.deleteFailed'))
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-3.5rem)] bg-background text-foreground">
    <div class="shrink-0 border-b border-border">
      <div class="max-w-4xl mx-auto px-6 py-4">
        <button
          class="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors mb-4"
          @click="router.push('/gene-market')"
        >
          <ArrowLeft class="w-4 h-4" />
          {{ t('template.backToMarket') }}
        </button>
      </div>
    </div>

    <div class="flex-1 min-h-0 overflow-y-auto">
      <div class="max-w-4xl mx-auto px-6 py-6">
        <div v-if="store.loading" class="flex justify-center py-20">
          <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
        </div>

        <template v-else-if="tpl">
          <div class="flex items-start gap-4 mb-8">
            <div class="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <component :is="resolveIcon(tpl.icon)" class="w-7 h-7 text-primary" />
            </div>
            <div class="flex-1 min-w-0">
              <h1 class="text-2xl font-bold mb-1">{{ tpl.name }}</h1>
              <p v-if="tpl.short_description" class="text-muted-foreground">{{ tpl.short_description }}</p>
              <div class="flex items-center gap-4 mt-3 text-sm text-muted-foreground">
                <span class="flex items-center gap-1">
                  <Dna class="w-4 h-4" />
                  {{ t('template.geneCount', { count: tpl.gene_slugs?.length ?? 0 }) }}
                </span>
                <span class="flex items-center gap-1">
                  <Download class="w-4 h-4" />
                  {{ t('template.useCount', { count: tpl.use_count ?? 0 }) }}
                </span>
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button
                class="px-4 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                @click="useThisTemplate"
              >
                {{ t('template.useTemplate') }}
              </button>
              <button
                class="p-2 rounded-lg text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                :disabled="deleting"
                @click="handleDelete"
              >
                <Loader2 v-if="deleting" class="w-4 h-4 animate-spin" />
                <Trash2 v-else class="w-4 h-4" />
              </button>
            </div>
          </div>

          <div v-if="tpl.description" class="mb-8">
            <h2 class="text-lg font-semibold mb-3">{{ t('template.description') }}</h2>
            <p class="text-muted-foreground whitespace-pre-wrap">{{ tpl.description }}</p>
          </div>

          <div>
            <h2 class="text-lg font-semibold mb-3">{{ t('template.includedGenes') }}</h2>
            <div v-if="!tpl.genes || tpl.genes.length === 0" class="text-muted-foreground text-sm py-8 text-center">
              {{ t('template.noGenes') }}
            </div>
            <div v-else class="space-y-2">
              <div
                v-for="gene in tpl.genes"
                :key="gene.slug"
                class="flex items-center gap-3 p-3 rounded-lg border border-border bg-card"
              >
                <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                  <component :is="resolveIcon(gene.icon)" class="w-4 h-4 text-primary" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-sm">{{ gene.name }}</div>
                  <div v-if="gene.short_description" class="text-xs text-muted-foreground line-clamp-1">{{ gene.short_description }}</div>
                </div>
                <span v-if="gene.category" class="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
                  {{ gene.category }}
                </span>
              </div>
            </div>
          </div>
        </template>

        <div v-else class="text-center py-20 text-muted-foreground">
          {{ t('template.notFound') }}
        </div>
      </div>
    </div>
  </div>
</template>
