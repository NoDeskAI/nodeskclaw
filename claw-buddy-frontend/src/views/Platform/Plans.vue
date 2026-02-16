<script setup lang="ts">
import { onMounted } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { CreditCard, Check, X } from 'lucide-vue-next'
import { useOrgStore } from '@/stores/org'

const orgStore = useOrgStore()

onMounted(() => {
  orgStore.fetchPlans()
})

function formatPrice(cents: number) {
  if (cents === 0) return '免费'
  return `¥${(cents / 100).toFixed(0)}/月`
}

function parseSpecs(json: string): string[] {
  try {
    return JSON.parse(json)
  } catch {
    return []
  }
}

const specLabels: Record<string, string> = {
  small: '小型 (2c/4G)',
  medium: '中型 (4c/8G)',
  large: '大型 (8c/16G)',
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div>
      <h1 class="text-xl font-bold">套餐管理</h1>
      <p class="text-sm text-muted-foreground mt-1">查看和管理平台订阅套餐</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <Card
        v-for="plan in orgStore.plans"
        :key="plan.id"
        class="relative overflow-hidden"
        :class="plan.name === 'pro' ? 'border-primary/50 ring-1 ring-primary/20' : ''"
      >
        <div v-if="plan.name === 'pro'" class="absolute top-0 right-0 px-3 py-0.5 bg-primary text-primary-foreground text-[10px] font-bold rounded-bl-lg">
          推荐
        </div>
        <CardHeader>
          <div class="flex items-center gap-2">
            <CreditCard class="w-5 h-5 text-primary" />
            <CardTitle>{{ plan.display_name }}</CardTitle>
          </div>
          <p class="text-2xl font-bold mt-2">{{ formatPrice(plan.price_monthly) }}</p>
        </CardHeader>
        <CardContent class="space-y-3">
          <div class="space-y-2 text-sm">
            <div class="flex items-center gap-2">
              <Check class="w-4 h-4 text-green-400" />
              <span>最多 {{ plan.max_instances }} 个实例</span>
            </div>
            <div class="flex items-center gap-2">
              <Check class="w-4 h-4 text-green-400" />
              <span>单实例 {{ plan.max_cpu_per_instance }} CPU</span>
            </div>
            <div class="flex items-center gap-2">
              <Check class="w-4 h-4 text-green-400" />
              <span>单实例 {{ plan.max_mem_per_instance }} 内存</span>
            </div>
            <div class="flex items-center gap-2">
              <component :is="plan.dedicated_cluster ? Check : X" class="w-4 h-4" :class="plan.dedicated_cluster ? 'text-green-400' : 'text-zinc-500'" />
              <span :class="plan.dedicated_cluster ? '' : 'text-muted-foreground'">专属集群</span>
            </div>
          </div>
          <div class="pt-2 border-t border-border">
            <p class="text-xs text-muted-foreground mb-1">可用规格</p>
            <div class="flex flex-wrap gap-1">
              <Badge v-for="spec in parseSpecs(plan.allowed_specs)" :key="spec" variant="secondary" class="text-[10px]">
                {{ specLabels[spec] || spec }}
              </Badge>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
