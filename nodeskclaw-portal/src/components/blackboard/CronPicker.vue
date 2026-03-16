<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { t } = useI18n()

type CronMode = 'hourly' | 'daily' | 'weekly' | 'monthly' | 'custom'

const mode = ref<CronMode>('daily')
const hourlyInterval = ref(4)
const dailyTime = ref('09:00')
const weeklyDay = ref(1)
const weeklyTime = ref('09:00')
const monthlyDays = ref<number[]>([1])
const monthlyTime = ref('14:00')
const customExpr = ref('')

const hourlyOptions = [1, 2, 3, 4, 6, 8, 12]

const modes: { key: CronMode; labelKey: string }[] = [
  { key: 'hourly', labelKey: 'blackboard.cronModeHourly' },
  { key: 'daily', labelKey: 'blackboard.cronModeDaily' },
  { key: 'weekly', labelKey: 'blackboard.cronModeWeekly' },
  { key: 'monthly', labelKey: 'blackboard.cronModeMonthly' },
  { key: 'custom', labelKey: 'blackboard.cronModeCustom' },
]

const weekDays = computed(() => [
  { value: 0, label: t('blackboard.cronSun') },
  { value: 1, label: t('blackboard.cronMon') },
  { value: 2, label: t('blackboard.cronTue') },
  { value: 3, label: t('blackboard.cronWed') },
  { value: 4, label: t('blackboard.cronThu') },
  { value: 5, label: t('blackboard.cronFri') },
  { value: 6, label: t('blackboard.cronSat') },
])

const isValid = computed(() => {
  if (mode.value === 'custom') {
    const parts = customExpr.value.trim().split(/\s+/)
    return parts.length >= 5
  }
  if (mode.value === 'monthly') return monthlyDays.value.length > 0
  return true
})

defineExpose({ isValid })

function buildCron(): string {
  switch (mode.value) {
    case 'hourly':
      return `0 */${hourlyInterval.value} * * *`
    case 'daily': {
      const [h, m] = dailyTime.value.split(':')
      return `${parseInt(m)} ${parseInt(h)} * * *`
    }
    case 'weekly': {
      const [h, m] = weeklyTime.value.split(':')
      return `${parseInt(m)} ${parseInt(h)} * * ${weeklyDay.value}`
    }
    case 'monthly': {
      const [h, m] = monthlyTime.value.split(':')
      const days = [...monthlyDays.value].sort((a, b) => a - b).join(',')
      return `${parseInt(m)} ${parseInt(h)} ${days} * *`
    }
    case 'custom':
      return customExpr.value.trim()
  }
}

function parseCron(expr: string) {
  const parts = expr.trim().split(/\s+/)
  if (parts.length < 5) {
    mode.value = 'custom'
    customExpr.value = expr
    return
  }

  const [minute, hour, dom, , dow] = parts

  if (hour.startsWith('*/') && dom === '*' && dow === '*') {
    const n = parseInt(hour.slice(2))
    if (hourlyOptions.includes(n)) {
      mode.value = 'hourly'
      hourlyInterval.value = n
      return
    }
  }

  if (dom === '*' && dow === '*' && /^\d+$/.test(hour) && /^\d+$/.test(minute)) {
    mode.value = 'daily'
    dailyTime.value = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
    return
  }

  if (dom === '*' && /^\d+$/.test(dow) && /^\d+$/.test(hour) && /^\d+$/.test(minute)) {
    mode.value = 'weekly'
    weeklyDay.value = parseInt(dow)
    weeklyTime.value = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
    return
  }

  if (dom !== '*' && dow === '*' && /^\d+$/.test(hour) && /^\d+$/.test(minute)) {
    const days = dom.split(',').map(Number).filter(n => !isNaN(n) && n >= 1 && n <= 31)
    if (days.length > 0) {
      mode.value = 'monthly'
      monthlyDays.value = days
      monthlyTime.value = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
      return
    }
  }

  mode.value = 'custom'
  customExpr.value = expr
}

let skipEmit = false

watch([mode, hourlyInterval, dailyTime, weeklyDay, weeklyTime, monthlyDays, monthlyTime, customExpr], () => {
  if (skipEmit) return
  emit('update:modelValue', buildCron())
}, { deep: true })

watch(() => props.modelValue, (val) => {
  if (val === buildCron()) return
  skipEmit = true
  parseCron(val)
  skipEmit = false
})

onMounted(() => {
  if (props.modelValue) {
    skipEmit = true
    parseCron(props.modelValue)
    skipEmit = false
  }
})

const hourlyDropdownOpen = ref(false)
const weekdayDropdownOpen = ref(false)

function toggleMonthDay(day: number) {
  const idx = monthlyDays.value.indexOf(day)
  if (idx >= 0) {
    if (monthlyDays.value.length > 1) monthlyDays.value.splice(idx, 1)
  } else {
    monthlyDays.value.push(day)
  }
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex flex-wrap gap-1">
      <button
        v-for="m in modes"
        :key="m.key"
        class="px-2.5 py-1 text-xs rounded-md transition-colors"
        :class="mode === m.key
          ? 'bg-primary text-primary-foreground'
          : 'bg-muted text-muted-foreground hover:text-foreground'"
        @click="mode = m.key"
      >
        {{ t(m.labelKey) }}
      </button>
    </div>

    <div v-if="mode === 'hourly'" class="flex items-center gap-2">
      <span class="text-sm text-muted-foreground">{{ t('blackboard.cronInterval') }}</span>
      <div class="relative">
        <button
          class="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-border bg-background hover:bg-muted/50 min-w-[4rem]"
          @click="hourlyDropdownOpen = !hourlyDropdownOpen"
        >
          {{ hourlyInterval }}
          <ChevronDown class="w-3.5 h-3.5 text-muted-foreground" />
        </button>
        <div
          v-if="hourlyDropdownOpen"
          class="absolute z-10 mt-1 w-full bg-card border border-border rounded-lg shadow-lg py-1"
        >
          <button
            v-for="n in hourlyOptions"
            :key="n"
            class="w-full px-3 py-1.5 text-sm text-left hover:bg-muted/50"
            :class="n === hourlyInterval ? 'text-primary font-medium' : ''"
            @click="hourlyInterval = n; hourlyDropdownOpen = false"
          >
            {{ n }}
          </button>
        </div>
      </div>
    </div>

    <div v-else-if="mode === 'daily'" class="flex items-center gap-2">
      <span class="text-sm text-muted-foreground">{{ t('blackboard.cronTime') }}</span>
      <input
        v-model="dailyTime"
        type="time"
        class="px-3 py-1.5 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
    </div>

    <div v-else-if="mode === 'weekly'" class="flex items-center gap-2 flex-wrap">
      <div class="relative">
        <button
          class="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border border-border bg-background hover:bg-muted/50 min-w-[5rem]"
          @click="weekdayDropdownOpen = !weekdayDropdownOpen"
        >
          {{ weekDays.find(d => d.value === weeklyDay)?.label }}
          <ChevronDown class="w-3.5 h-3.5 text-muted-foreground" />
        </button>
        <div
          v-if="weekdayDropdownOpen"
          class="absolute z-10 mt-1 w-full bg-card border border-border rounded-lg shadow-lg py-1"
        >
          <button
            v-for="d in weekDays"
            :key="d.value"
            class="w-full px-3 py-1.5 text-sm text-left hover:bg-muted/50"
            :class="d.value === weeklyDay ? 'text-primary font-medium' : ''"
            @click="weeklyDay = d.value; weekdayDropdownOpen = false"
          >
            {{ d.label }}
          </button>
        </div>
      </div>
      <input
        v-model="weeklyTime"
        type="time"
        class="px-3 py-1.5 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
      />
    </div>

    <div v-else-if="mode === 'monthly'" class="space-y-2">
      <div>
        <span class="text-sm text-muted-foreground">{{ t('blackboard.cronMonthlyDays') }}</span>
        <div class="flex flex-wrap gap-1 mt-1.5">
          <button
            v-for="d in 31"
            :key="d"
            class="w-7 h-7 text-xs rounded transition-colors"
            :class="monthlyDays.includes(d)
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-muted-foreground hover:text-foreground'"
            @click="toggleMonthDay(d)"
          >
            {{ d }}
          </button>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-sm text-muted-foreground">{{ t('blackboard.cronTime') }}</span>
        <input
          v-model="monthlyTime"
          type="time"
          class="px-3 py-1.5 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
    </div>

    <div v-else-if="mode === 'custom'" class="space-y-1">
      <input
        v-model="customExpr"
        :placeholder="t('blackboard.cronExpr')"
        class="w-full px-3 py-1.5 text-sm rounded-lg border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 font-mono"
      />
      <p v-if="customExpr && !isValid" class="text-xs text-destructive">
        {{ t('blackboard.cronInvalid') }}
      </p>
    </div>
  </div>
</template>
