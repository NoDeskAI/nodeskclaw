<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useNotify } from '@/components/ui/notify/useNotify'
import { useGeneStore } from '@/stores/gene'
import type { GeneItem, GenomeItem } from '@/stores/gene'
import {
  Dna,
  Download,
  TrendingUp,
  AlertCircle,
  Sparkles,
  Activity,
  Plus,
  Pencil,
  Trash2,
  Check,
  X,
  Search,
  Loader2,
  Eye,
  EyeOff,
  Star as StarIcon,
  RefreshCw,
} from 'lucide-vue-next'

const store = useGeneStore()
const notify = useNotify()
const activeTab = ref('overview')

const geneKeyword = ref('')
const geneCategory = ref<string | undefined>(undefined)
const genePublished = ref<string | undefined>(undefined)
const genePage = ref(1)
const genePageSize = 20

const genomeKeyword = ref('')
const genomePublished = ref<string | undefined>(undefined)
const genomePage = ref(1)
const genomePageSize = 20

const showGeneDialog = ref(false)
const editingGene = ref<GeneItem | null>(null)
const geneForm = ref({
  name: '',
  slug: '',
  description: '',
  short_description: '',
  category: '',
  tags: '',
  icon: '',
  version: '1.0.0',
  is_featured: false,
  is_published: true,
})

const showGenomeDialog = ref(false)
const editingGenome = ref<GenomeItem | null>(null)
const genomeForm = ref({
  name: '',
  slug: '',
  description: '',
  short_description: '',
  icon: '',
  gene_slugs: '',
  is_featured: false,
  is_published: true,
})

const saving = ref(false)
const reviewingId = ref<string | null>(null)

const geneTotalPages = computed(() => Math.ceil(store.totalGenes / genePageSize) || 1)
const genomeTotalPages = computed(() => Math.ceil(store.totalGenomes / genomePageSize) || 1)

function formatDate(s: string | null): string {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatMetricType(t: string): string {
  const map: Record<string, string> = {
    user_positive: '用户正向',
    user_negative: '用户负向',
    task_success: '任务成功',
      agent_self_eval: 'AI 员工自评',
  }
  return map[t] ?? t
}

async function loadOverview() {
  await Promise.all([store.fetchStats(), store.fetchActivity(50), store.fetchPendingGenes()])
}

async function loadGenes() {
  await store.fetchGenes({
    keyword: geneKeyword.value || undefined,
    category: geneCategory.value || undefined,
    is_published: genePublished.value === 'true' ? true : genePublished.value === 'false' ? false : undefined,
    page: genePage.value,
    page_size: genePageSize,
  })
}

async function loadGenomes() {
  await store.fetchGenomes({
    keyword: genomeKeyword.value || undefined,
    is_published: genomePublished.value === 'true' ? true : genomePublished.value === 'false' ? false : undefined,
    page: genomePage.value,
    page_size: genomePageSize,
  })
}

onMounted(loadOverview)

watch(activeTab, (tab) => {
  if (tab === 'overview') loadOverview()
  else if (tab === 'genes') loadGenes()
  else if (tab === 'genomes') loadGenomes()
  else if (tab === 'review') store.fetchPendingGenes()
})

let geneSearchTimer: ReturnType<typeof setTimeout> | null = null
watch(geneKeyword, () => {
  if (geneSearchTimer) clearTimeout(geneSearchTimer)
  geneSearchTimer = setTimeout(() => { genePage.value = 1; loadGenes() }, 300)
})
watch([geneCategory, genePublished], () => { genePage.value = 1; loadGenes() })
watch(genePage, loadGenes)

let genomeSearchTimer: ReturnType<typeof setTimeout> | null = null
watch(genomeKeyword, () => {
  if (genomeSearchTimer) clearTimeout(genomeSearchTimer)
  genomeSearchTimer = setTimeout(() => { genomePage.value = 1; loadGenomes() }, 300)
})
watch(genomePublished, () => { genomePage.value = 1; loadGenomes() })
watch(genomePage, loadGenomes)

function openCreateGene() {
  editingGene.value = null
  geneForm.value = { name: '', slug: '', description: '', short_description: '', category: '', tags: '', icon: '', version: '1.0.0', is_featured: false, is_published: true }
  showGeneDialog.value = true
}

function openEditGene(gene: GeneItem) {
  editingGene.value = gene
  geneForm.value = {
    name: gene.name,
    slug: gene.slug,
    description: gene.description ?? '',
    short_description: gene.short_description ?? '',
    category: gene.category ?? '',
    tags: (gene.tags ?? []).join(', '),
    icon: gene.icon ?? '',
    version: gene.version,
    is_featured: gene.is_featured,
    is_published: gene.is_published,
  }
  showGeneDialog.value = true
}

async function saveGene() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: geneForm.value.name,
      description: geneForm.value.description || undefined,
      short_description: geneForm.value.short_description || undefined,
      category: geneForm.value.category || undefined,
      tags: geneForm.value.tags ? geneForm.value.tags.split(',').map((s) => s.trim()).filter(Boolean) : [],
      icon: geneForm.value.icon || undefined,
      version: geneForm.value.version,
      is_featured: geneForm.value.is_featured,
      is_published: geneForm.value.is_published,
    }
    if (editingGene.value) {
      await store.updateGene(editingGene.value.id, payload)
      notify.success('基因已更新')
    } else {
      payload.slug = geneForm.value.slug
      await store.createGene(payload)
      notify.success('基因已创建')
    }
    showGeneDialog.value = false
    loadGenes()
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message || '操作失败'
    notify.error(msg)
  } finally {
    saving.value = false
  }
}

async function handleDeleteGene(gene: GeneItem) {
  if (!confirm(`确认删除基因「${gene.name}」?`)) return
  try {
    await store.deleteGene(gene.id)
    notify.success('基因已删除')
    loadGenes()
  } catch {
    notify.error('删除失败')
  }
}

async function toggleGenePublish(gene: GeneItem) {
  try {
    await store.updateGene(gene.id, { is_published: !gene.is_published })
    notify.success(gene.is_published ? '已下架' : '已发布')
    loadGenes()
  } catch {
    notify.error('操作失败')
  }
}

function openCreateGenome() {
  editingGenome.value = null
  genomeForm.value = { name: '', slug: '', description: '', short_description: '', icon: '', gene_slugs: '', is_featured: false, is_published: true }
  showGenomeDialog.value = true
}

function openEditGenome(genome: GenomeItem) {
  editingGenome.value = genome
  genomeForm.value = {
    name: genome.name,
    slug: genome.slug,
    description: genome.description ?? '',
    short_description: genome.short_description ?? '',
    icon: genome.icon ?? '',
    gene_slugs: (genome.gene_slugs ?? []).join(', '),
    is_featured: genome.is_featured,
    is_published: genome.is_published,
  }
  showGenomeDialog.value = true
}

async function saveGenome() {
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      name: genomeForm.value.name,
      description: genomeForm.value.description || undefined,
      short_description: genomeForm.value.short_description || undefined,
      icon: genomeForm.value.icon || undefined,
      gene_slugs: genomeForm.value.gene_slugs ? genomeForm.value.gene_slugs.split(',').map((s) => s.trim()).filter(Boolean) : [],
      is_featured: genomeForm.value.is_featured,
      is_published: genomeForm.value.is_published,
    }
    if (editingGenome.value) {
      await store.updateGenome(editingGenome.value.id, payload)
      notify.success('基因组已更新')
    } else {
      payload.slug = genomeForm.value.slug
      await store.createGenome(payload)
      notify.success('基因组已创建')
    }
    showGenomeDialog.value = false
    loadGenomes()
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message || '操作失败'
    notify.error(msg)
  } finally {
    saving.value = false
  }
}

async function handleDeleteGenome(genome: GenomeItem) {
  if (!confirm(`确认删除基因组「${genome.name}」?`)) return
  try {
    await store.deleteGenome(genome.id)
    notify.success('基因组已删除')
    loadGenomes()
  } catch {
    notify.error('删除失败')
  }
}

async function toggleGenomePublish(genome: GenomeItem) {
  try {
    await store.updateGenome(genome.id, { is_published: !genome.is_published })
    notify.success(genome.is_published ? '已下架' : '已发布')
    loadGenomes()
  } catch {
    notify.error('操作失败')
  }
}

async function handleReview(geneId: string, action: 'approve' | 'reject') {
  reviewingId.value = geneId
  try {
    await store.reviewGene(geneId, action)
    store.pendingGenes = store.pendingGenes.filter((g) => g.id !== geneId)
    notify.success(action === 'approve' ? '已通过' : '已拒绝')
  } catch {
    notify.error('操作失败')
  } finally {
    reviewingId.value = null
  }
}

const categories = ['开发', '数据', '运维', '网络', '创意', '沟通', '安全', '效率']
</script>

<template>
  <div class="p-6 space-y-6">
    <h1 class="text-2xl font-bold">基因运营</h1>

    <Tabs v-model="activeTab">
      <TabsList>
        <TabsTrigger value="overview">概览</TabsTrigger>
        <TabsTrigger value="genes">基因管理</TabsTrigger>
        <TabsTrigger value="genomes">基因组管理</TabsTrigger>
        <TabsTrigger value="review">审核队列</TabsTrigger>
      </TabsList>

      <!-- 概览 Tab -->
      <TabsContent value="overview" class="space-y-6">
        <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent class="pt-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1">
                <Dna class="w-4 h-4" />
                <span class="text-sm">基因总数</span>
              </div>
              <div class="text-2xl font-bold">{{ store.stats?.total_genes ?? 0 }}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent class="pt-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1">
                <Download class="w-4 h-4" />
                <span class="text-sm">总学习数</span>
              </div>
              <div class="text-2xl font-bold">{{ store.stats?.total_installs ?? 0 }}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent class="pt-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1">
                <TrendingUp class="w-4 h-4" />
                <span class="text-sm">学习中</span>
              </div>
              <div class="text-2xl font-bold">{{ store.stats?.learning_count ?? 0 }}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent class="pt-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1">
                <AlertCircle class="w-4 h-4" />
                <span class="text-sm">失败数</span>
              </div>
              <div class="text-2xl font-bold">{{ store.stats?.failed_count ?? 0 }}</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent class="pt-4">
              <div class="flex items-center gap-2 text-muted-foreground mb-1">
                <Sparkles class="w-4 h-4" />
                <span class="text-sm">AI 员工创造</span>
              </div>
              <div class="text-2xl font-bold">{{ store.stats?.agent_created_count ?? 0 }}</div>
            </CardContent>
          </Card>
        </div>

        <div class="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader class="pb-3">
              <CardTitle class="text-base">活动流</CardTitle>
            </CardHeader>
            <CardContent class="max-h-[320px] overflow-y-auto divide-y divide-border -mt-2">
              <div
                v-for="a in store.activity"
                :key="a.id"
                class="py-2 text-sm"
              >
                <span class="font-medium">{{ a.gene_name }}</span>
                <span class="text-muted-foreground mx-1">{{ formatMetricType(a.metric_type) }}</span>
                <span class="text-muted-foreground">{{ formatDate(a.created_at) }}</span>
              </div>
              <div v-if="store.activity.length === 0" class="py-8 text-center text-muted-foreground text-sm">
                暂无活动
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader class="pb-3">
              <div class="flex items-center justify-between">
                <CardTitle class="text-base">待审核</CardTitle>
                <Badge v-if="store.pendingGenes.length > 0" variant="secondary">
                  {{ store.pendingGenes.length }}
                </Badge>
              </div>
            </CardHeader>
            <CardContent class="max-h-[320px] overflow-y-auto divide-y divide-border -mt-2">
              <div
                v-for="g in store.pendingGenes"
                :key="g.id"
                class="py-2 flex items-center justify-between gap-3"
              >
                <div class="min-w-0 flex-1">
                  <div class="font-medium text-sm">{{ g.name }}</div>
                  <div class="text-xs text-muted-foreground">{{ g.slug }}</div>
                </div>
                <div class="flex items-center gap-1.5 shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    class="h-7 text-green-500 hover:text-green-400 hover:bg-green-500/10"
                    :disabled="reviewingId === g.id"
                    @click="handleReview(g.id, 'approve')"
                  >
                    <Check class="w-3.5 h-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    class="h-7 text-red-500 hover:text-red-400 hover:bg-red-500/10"
                    :disabled="reviewingId === g.id"
                    @click="handleReview(g.id, 'reject')"
                  >
                    <X class="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
              <div v-if="store.pendingGenes.length === 0" class="py-8 text-center text-muted-foreground text-sm">
                暂无待审核基因
              </div>
            </CardContent>
          </Card>
        </div>
      </TabsContent>

      <!-- 基因管理 Tab -->
      <TabsContent value="genes" class="space-y-4">
        <div class="flex flex-wrap items-center gap-3">
          <div class="relative flex-1 min-w-[200px] max-w-[320px]">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input v-model="geneKeyword" placeholder="搜索基因" class="pl-9" />
          </div>
          <Select v-model="geneCategory">
            <SelectTrigger class="w-[120px]">
              <SelectValue placeholder="全部分类" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem :value="undefined as unknown as string">全部分类</SelectItem>
              <SelectItem v-for="c in categories" :key="c" :value="c">{{ c }}</SelectItem>
            </SelectContent>
          </Select>
          <Select v-model="genePublished">
            <SelectTrigger class="w-[120px]">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem :value="undefined as unknown as string">全部状态</SelectItem>
              <SelectItem value="true">已发布</SelectItem>
              <SelectItem value="false">未发布</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" @click="loadGenes">
            <RefreshCw class="w-3.5 h-3.5 mr-1.5" />
            刷新
          </Button>
          <Button size="sm" @click="openCreateGene">
            <Plus class="w-3.5 h-3.5 mr-1.5" />
            创建基因
          </Button>
        </div>

        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>分类</TableHead>
                <TableHead>来源</TableHead>
                <TableHead class="text-center">学习数</TableHead>
                <TableHead class="text-center">评分</TableHead>
                <TableHead class="text-center">状态</TableHead>
                <TableHead class="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-if="store.loading">
                <TableCell :colspan="8" class="text-center py-10">
                  <Loader2 class="w-5 h-5 animate-spin inline-block text-muted-foreground" />
                </TableCell>
              </TableRow>
              <TableRow v-else-if="store.genes.length === 0">
                <TableCell :colspan="8" class="text-center py-10 text-muted-foreground">
                  暂无数据
                </TableCell>
              </TableRow>
              <TableRow v-for="gene in store.genes" :key="gene.id">
                <TableCell class="font-medium">
                  {{ gene.name }}
                  <Badge v-if="gene.is_featured" variant="secondary" class="ml-1.5 text-[10px]">精选</Badge>
                </TableCell>
                <TableCell class="text-muted-foreground font-mono text-xs">{{ gene.slug }}</TableCell>
                <TableCell>{{ gene.category || '-' }}</TableCell>
                <TableCell>
                  <Badge :variant="gene.source === 'official' ? 'default' : 'secondary'">
                    {{ gene.source === 'official' ? '官方' : gene.source === 'agent' ? 'AI 员工' : gene.source }}
                  </Badge>
                </TableCell>
                <TableCell class="text-center">{{ gene.install_count }}</TableCell>
                <TableCell class="text-center">
                  <span class="inline-flex items-center gap-0.5">
                    <StarIcon class="w-3 h-3 fill-amber-400 text-amber-400" />
                    {{ (gene.avg_rating ?? 0).toFixed(1) }}
                  </span>
                </TableCell>
                <TableCell class="text-center">
                  <Badge :variant="gene.is_published ? 'default' : 'outline'" class="text-[10px]">
                    {{ gene.is_published ? '已发布' : '未发布' }}
                  </Badge>
                </TableCell>
                <TableCell class="text-right">
                  <div class="flex items-center justify-end gap-1">
                    <Button size="icon" variant="ghost" class="h-7 w-7" @click="toggleGenePublish(gene)">
                      <Eye v-if="!gene.is_published" class="w-3.5 h-3.5" />
                      <EyeOff v-else class="w-3.5 h-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" class="h-7 w-7" @click="openEditGene(gene)">
                      <Pencil class="w-3.5 h-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" class="h-7 w-7 text-red-500 hover:text-red-400" @click="handleDeleteGene(gene)">
                      <Trash2 class="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>

        <div v-if="geneTotalPages > 1" class="flex items-center justify-center gap-2">
          <Button size="sm" variant="outline" :disabled="genePage <= 1" @click="genePage--">
            上一页
          </Button>
          <span class="text-sm text-muted-foreground">{{ genePage }} / {{ geneTotalPages }}</span>
          <Button size="sm" variant="outline" :disabled="genePage >= geneTotalPages" @click="genePage++">
            下一页
          </Button>
        </div>
      </TabsContent>

      <!-- 基因组管理 Tab -->
      <TabsContent value="genomes" class="space-y-4">
        <div class="flex flex-wrap items-center gap-3">
          <div class="relative flex-1 min-w-[200px] max-w-[320px]">
            <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input v-model="genomeKeyword" placeholder="搜索基因组" class="pl-9" />
          </div>
          <Select v-model="genomePublished">
            <SelectTrigger class="w-[120px]">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem :value="undefined as unknown as string">全部状态</SelectItem>
              <SelectItem value="true">已发布</SelectItem>
              <SelectItem value="false">未发布</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" @click="loadGenomes">
            <RefreshCw class="w-3.5 h-3.5 mr-1.5" />
            刷新
          </Button>
          <Button size="sm" @click="openCreateGenome">
            <Plus class="w-3.5 h-3.5 mr-1.5" />
            创建基因组
          </Button>
        </div>

        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>包含基因</TableHead>
                <TableHead class="text-center">学习数</TableHead>
                <TableHead class="text-center">评分</TableHead>
                <TableHead class="text-center">状态</TableHead>
                <TableHead class="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-if="store.loading">
                <TableCell :colspan="7" class="text-center py-10">
                  <Loader2 class="w-5 h-5 animate-spin inline-block text-muted-foreground" />
                </TableCell>
              </TableRow>
              <TableRow v-else-if="store.genomes.length === 0">
                <TableCell :colspan="7" class="text-center py-10 text-muted-foreground">
                  暂无数据
                </TableCell>
              </TableRow>
              <TableRow v-for="genome in store.genomes" :key="genome.id">
                <TableCell class="font-medium">
                  {{ genome.name }}
                  <Badge v-if="genome.is_featured" variant="secondary" class="ml-1.5 text-[10px]">精选</Badge>
                </TableCell>
                <TableCell class="text-muted-foreground font-mono text-xs">{{ genome.slug }}</TableCell>
                <TableCell>
                  <div class="flex flex-wrap gap-1">
                    <Badge v-for="s in (genome.gene_slugs ?? []).slice(0, 3)" :key="s" variant="outline" class="text-[10px]">
                      {{ s }}
                    </Badge>
                    <span v-if="(genome.gene_slugs ?? []).length > 3" class="text-xs text-muted-foreground">
                      +{{ (genome.gene_slugs ?? []).length - 3 }}
                    </span>
                  </div>
                </TableCell>
                <TableCell class="text-center">{{ genome.install_count }}</TableCell>
                <TableCell class="text-center">
                  <span class="inline-flex items-center gap-0.5">
                    <StarIcon class="w-3 h-3 fill-amber-400 text-amber-400" />
                    {{ (genome.avg_rating ?? 0).toFixed(1) }}
                  </span>
                </TableCell>
                <TableCell class="text-center">
                  <Badge :variant="genome.is_published ? 'default' : 'outline'" class="text-[10px]">
                    {{ genome.is_published ? '已发布' : '未发布' }}
                  </Badge>
                </TableCell>
                <TableCell class="text-right">
                  <div class="flex items-center justify-end gap-1">
                    <Button size="icon" variant="ghost" class="h-7 w-7" @click="toggleGenomePublish(genome)">
                      <Eye v-if="!genome.is_published" class="w-3.5 h-3.5" />
                      <EyeOff v-else class="w-3.5 h-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" class="h-7 w-7" @click="openEditGenome(genome)">
                      <Pencil class="w-3.5 h-3.5" />
                    </Button>
                    <Button size="icon" variant="ghost" class="h-7 w-7 text-red-500 hover:text-red-400" @click="handleDeleteGenome(genome)">
                      <Trash2 class="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>

        <div v-if="genomeTotalPages > 1" class="flex items-center justify-center gap-2">
          <Button size="sm" variant="outline" :disabled="genomePage <= 1" @click="genomePage--">
            上一页
          </Button>
          <span class="text-sm text-muted-foreground">{{ genomePage }} / {{ genomeTotalPages }}</span>
          <Button size="sm" variant="outline" :disabled="genomePage >= genomeTotalPages" @click="genomePage++">
            下一页
          </Button>
        </div>
      </TabsContent>

      <!-- 审核队列 Tab -->
      <TabsContent value="review" class="space-y-4">
        <div class="flex items-center gap-3">
          <Button size="sm" variant="outline" @click="store.fetchPendingGenes()">
            <RefreshCw class="w-3.5 h-3.5 mr-1.5" />
            刷新
          </Button>
        </div>

        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>审核状态</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead class="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-if="store.pendingGenes.length === 0">
                <TableCell :colspan="6" class="text-center py-10 text-muted-foreground">
                  暂无待审核基因
                </TableCell>
              </TableRow>
              <TableRow v-for="gene in store.pendingGenes" :key="gene.id">
                <TableCell class="font-medium">{{ gene.name }}</TableCell>
                <TableCell class="text-muted-foreground font-mono text-xs">{{ gene.slug }}</TableCell>
                <TableCell>
                  <Badge :variant="gene.source === 'official' ? 'default' : 'secondary'">
                    {{ gene.source === 'official' ? '官方' : gene.source === 'agent' ? 'AI 员工' : gene.source }}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant="outline">{{ gene.review_status }}</Badge>
                </TableCell>
                <TableCell class="text-muted-foreground text-sm">{{ formatDate(gene.created_at) }}</TableCell>
                <TableCell class="text-right">
                  <div class="flex items-center justify-end gap-1.5">
                    <Button
                      size="sm"
                      variant="ghost"
                      class="h-7 text-green-500 hover:text-green-400 hover:bg-green-500/10"
                      :disabled="reviewingId === gene.id"
                      @click="handleReview(gene.id, 'approve')"
                    >
                      <Loader2 v-if="reviewingId === gene.id" class="w-3.5 h-3.5 animate-spin mr-1" />
                      <Check v-else class="w-3.5 h-3.5 mr-1" />
                      通过
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      class="h-7 text-red-500 hover:text-red-400 hover:bg-red-500/10"
                      :disabled="reviewingId === gene.id"
                      @click="handleReview(gene.id, 'reject')"
                    >
                      <X class="w-3.5 h-3.5 mr-1" />
                      拒绝
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </TabsContent>
    </Tabs>

    <!-- 基因编辑弹窗 -->
    <Dialog v-model:open="showGeneDialog">
      <DialogContent class="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{{ editingGene ? '编辑基因' : '创建基因' }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1.5">
              <label class="text-sm font-medium">名称</label>
              <Input v-model="geneForm.name" placeholder="基因名称" />
            </div>
            <div class="space-y-1.5">
              <label class="text-sm font-medium">Slug</label>
              <Input v-model="geneForm.slug" placeholder="gene-slug" :disabled="!!editingGene" />
            </div>
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">简短描述</label>
            <Input v-model="geneForm.short_description" placeholder="一句话描述" />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">详细描述</label>
            <textarea
              v-model="geneForm.description"
              rows="3"
              class="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="详细描述"
            />
          </div>
          <div class="grid grid-cols-3 gap-4">
            <div class="space-y-1.5">
              <label class="text-sm font-medium">分类</label>
              <Select v-model="geneForm.category">
                <SelectTrigger><SelectValue placeholder="选择分类" /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="c in categories" :key="c" :value="c">{{ c }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-1.5">
              <label class="text-sm font-medium">版本</label>
              <Input v-model="geneForm.version" placeholder="1.0.0" />
            </div>
            <div class="space-y-1.5">
              <label class="text-sm font-medium">图标</label>
              <Input v-model="geneForm.icon" placeholder="icon-name" />
            </div>
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">标签（逗号分隔）</label>
            <Input v-model="geneForm.tags" placeholder="标签1, 标签2" />
          </div>
          <div class="flex items-center gap-6">
            <label class="flex items-center gap-2 text-sm">
              <input v-model="geneForm.is_published" type="checkbox" class="rounded" />
              发布
            </label>
            <label class="flex items-center gap-2 text-sm">
              <input v-model="geneForm.is_featured" type="checkbox" class="rounded" />
              精选
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showGeneDialog = false">取消</Button>
          <Button :disabled="saving || !geneForm.name" @click="saveGene">
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin mr-1.5" />
            {{ editingGene ? '保存' : '创建' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 基因组编辑弹窗 -->
    <Dialog v-model:open="showGenomeDialog">
      <DialogContent class="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{{ editingGenome ? '编辑基因组' : '创建基因组' }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-1.5">
              <label class="text-sm font-medium">名称</label>
              <Input v-model="genomeForm.name" placeholder="基因组名称" />
            </div>
            <div class="space-y-1.5">
              <label class="text-sm font-medium">Slug</label>
              <Input v-model="genomeForm.slug" placeholder="genome-slug" :disabled="!!editingGenome" />
            </div>
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">简短描述</label>
            <Input v-model="genomeForm.short_description" placeholder="一句话描述" />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">详细描述</label>
            <textarea
              v-model="genomeForm.description"
              rows="3"
              class="flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              placeholder="详细描述"
            />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">包含基因 Slug（逗号分隔）</label>
            <Input v-model="genomeForm.gene_slugs" placeholder="gene-a, gene-b, gene-c" />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">图标</label>
            <Input v-model="genomeForm.icon" placeholder="icon-name" />
          </div>
          <div class="flex items-center gap-6">
            <label class="flex items-center gap-2 text-sm">
              <input v-model="genomeForm.is_published" type="checkbox" class="rounded" />
              发布
            </label>
            <label class="flex items-center gap-2 text-sm">
              <input v-model="genomeForm.is_featured" type="checkbox" class="rounded" />
              精选
            </label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showGenomeDialog = false">取消</Button>
          <Button :disabled="saving || !genomeForm.name" @click="saveGenome">
            <Loader2 v-if="saving" class="w-4 h-4 animate-spin mr-1.5" />
            {{ editingGenome ? '保存' : '创建' }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
