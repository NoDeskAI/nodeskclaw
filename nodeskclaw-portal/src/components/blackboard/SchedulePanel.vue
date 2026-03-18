<script setup lang="ts">
import { ref, computed } from 'vue'
import { Timer, Plus, Pencil, Trash2, X, Loader2 } from 'lucide-vue-next'
import { useWorkspaceStore, type ScheduleInfo } from '@/stores/workspace'
import { useI18n } from 'vue-i18n'
import { useConfirm } from '@/composables/useConfirm'
import { useToast } from '@/composables/useToast'
import { resolveApiErrorMessage } from '@/i18n/error'
import CronPicker from './CronPicker.vue'

const props = defineProps<{
  workspaceId: string
}>()

const { t } = useI18n()
const store = useWorkspaceStore()
const { confirm } = useConfirm()
const toast = useToast()

const schedules = computed(() => store.schedules)
const presets = computed(() => store.schedulePresets)
const canManage = computed(() => store.hasPermission('manage_settings'))

const dialogOpen = ref(false)
const editingId = ref<string | null>(null)
const submitting = ref(false)

const form = ref({
  name: '',
  cron_expr: '0 */4 * * *',
  message_template: '',
})

const cronPickerRef = ref<InstanceType<typeof CronPicker> | null>(null)

const formValid = computed(() => {
  if (!form.value.name.trim()) return false
  if (!form.value.cron_expr.trim()) return false
  if (!form.value.message_template.trim()) return false
  if (cronPickerRef.value && !cronPickerRef.value.isValid) return false
  return true
})

function cronToHuman(expr: string): string {
  const parts = expr.trim().split(/\s+/)
  if (parts.length < 5) return expr

  const [minute, hour, dom, , dow] = parts

  if (hour.startsWith('*/')) {
    const n = hour.slice(2)
    return t('blackboard.cronEveryNHours', { n })
  }

  if (dom === '*' && dow === '*' && /^\d+$/.test(hour) && /^\d+$/.test(minute)) {
    return t('blackboard.cronDailyAt', { time: `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}` })
  }

  if (dom === '*' && /^\d+$/.test(dow) && /^\d+$/.test(hour) && /^\d+$/.test(minute)) {
    const days = [
      t('blackboard.cronSun'), t('blackboard.cronMon'), t('blackboard.cronTue'),
      t('blackboard.cronWed'), t('blackboard.cronThu'), t('blackboard.cronFri'), t('blackboard.cronSat'),
    ]
    const dayName = days[Number(dow)] || dow
    const time = `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
    return t('blackboard.cronWeeklyAt', { day: dayName, time })
  }

  return expr
}

function openCreate() {
  editingId.value = null
  form.value = { name: '', cron_expr: '0 */4 * * *', message_template: '' }
  dialogOpen.value = true
}

function openEdit(schedule: ScheduleInfo) {
  editingId.value = schedule.id
  form.value = {
    name: schedule.name,
    cron_expr: schedule.cron_expr,
    message_template: schedule.message_template,
  }
  dialogOpen.value = true
}

function presetLabel(preset: { name: string; label: string }): string {
  const key = `blackboard.preset_${preset.name}`
  const translated = t(key)
  return translated === key ? preset.label : translated
}

function applyPreset(preset: { name: string; label: string; cron_expr: string; message_template: string }) {
  form.value.name = presetLabel(preset)
  form.value.cron_expr = preset.cron_expr
  form.value.message_template = preset.message_template
}

async function handleSubmit() {
  if (!formValid.value || submitting.value) return
  submitting.value = true
  try {
    if (editingId.value) {
      await store.updateSchedule(props.workspaceId, editingId.value, {
        name: form.value.name.trim(),
        cron_expr: form.value.cron_expr,
        message_template: form.value.message_template.trim(),
      })
      toast.success(t('blackboard.scheduleUpdated'))
    } else {
      await store.createSchedule(props.workspaceId, {
        name: form.value.name.trim(),
        cron_expr: form.value.cron_expr,
        message_template: form.value.message_template.trim(),
      })
      toast.success(t('blackboard.scheduleCreated'))
    }
    dialogOpen.value = false
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function handleDelete(schedule: ScheduleInfo) {
  const ok = await confirm({
    title: t('blackboard.deleteSchedule'),
    description: t('blackboard.deleteScheduleConfirm', { name: schedule.name }),
    variant: 'danger',
  })
  if (!ok) return
  try {
    await store.deleteSchedule(props.workspaceId, schedule.id)
    toast.success(t('blackboard.scheduleDeleted'))
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e))
  }
}

async function toggle(schedule: ScheduleInfo) {
  try {
    await store.toggleScheduleActive(props.workspaceId, schedule.id, !schedule.is_active)
  } catch (e: unknown) {
    toast.error(resolveApiErrorMessage(e))
  }
}
</script>

<template>
  <div class="space-y-3">
    <h3 class="text-sm font-medium text-muted-foreground flex items-center gap-1.5">
      <Timer class="w-4 h-4" />
      {{ t('blackboard.schedules') }}
      <button
        v-if="canManage"
        class="ml-auto p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
        :aria-label="t('blackboard.addSchedule')"
        :title="t('blackboard.addSchedule')"
        @click="openCreate"
      >
        <Plus class="w-3.5 h-3.5" />
      </button>
    </h3>

    <div v-if="schedules.length === 0" class="text-sm text-muted-foreground px-1">
      {{ t('blackboard.noSchedules') }}
    </div>

    <div v-else class="space-y-2">
      <div
        v-for="schedule in schedules"
        :key="schedule.id"
        class="group flex items-center justify-between px-3 py-2.5 rounded-lg bg-muted/50"
      >
        <div class="flex-1 min-w-0 mr-3">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium truncate">{{ schedule.name }}</span>
            <span class="text-xs px-1.5 py-0.5 rounded bg-muted text-muted-foreground shrink-0">
              {{ cronToHuman(schedule.cron_expr) }}
            </span>
          </div>
          <p class="text-xs text-muted-foreground mt-0.5 line-clamp-1">{{ schedule.message_template }}</p>
        </div>

        <div class="flex items-center gap-1.5 shrink-0">
          <template v-if="canManage">
            <button
              class="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-muted transition-all text-muted-foreground hover:text-foreground"
              :aria-label="t('blackboard.editSchedule')"
              :title="t('blackboard.editSchedule')"
              @click="openEdit(schedule)"
            >
              <Pencil class="w-3.5 h-3.5" />
            </button>
            <button
              class="p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-muted transition-all text-muted-foreground hover:text-destructive"
              :aria-label="t('blackboard.deleteSchedule')"
              :title="t('blackboard.deleteSchedule')"
              @click="handleDelete(schedule)"
            >
              <Trash2 class="w-3.5 h-3.5" />
            </button>
          </template>
          <button
            v-if="canManage"
            role="switch"
            :aria-checked="schedule.is_active"
            class="relative inline-flex h-5 w-9 shrink-0 rounded-full transition-colors duration-200"
            :class="schedule.is_active ? 'bg-primary' : 'bg-muted-foreground/30'"
            @click="toggle(schedule)"
          >
            <span
              class="pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform duration-200 mt-0.5"
              :class="schedule.is_active ? 'translate-x-[18px]' : 'translate-x-0.5'"
            />
          </button>
          <span
            v-else
            class="text-xs px-1.5 py-0.5 rounded"
            :class="schedule.is_active ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'"
          >
            {{ schedule.is_active ? t('blackboard.scheduleActive') : t('blackboard.scheduleInactive') }}
          </span>
        </div>
      </div>
    </div>

    <!-- Create / Edit Dialog -->
    <Teleport to="body">
      <div
        v-if="dialogOpen"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        @click.self="dialogOpen = false"
      >
        <div class="bg-card rounded-2xl border border-border shadow-xl w-full max-w-lg mx-4 p-6 space-y-5">
          <div class="flex items-center justify-between">
            <h3 class="font-semibold text-base">
              {{ editingId ? t('blackboard.editSchedule') : t('blackboard.addSchedule') }}
            </h3>
            <button class="text-muted-foreground hover:text-foreground" @click="dialogOpen = false">
              <X class="w-4 h-4" />
            </button>
          </div>

          <!-- Preset Templates -->
          <div v-if="!editingId && presets.length > 0">
            <p class="text-xs text-muted-foreground mb-2">{{ t('blackboard.presetTemplates') }}</p>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="preset in presets"
                :key="preset.name"
                class="px-2.5 py-1 text-xs rounded-md border border-border hover:bg-muted/50 transition-colors"
                @click="applyPreset(preset)"
              >
                {{ presetLabel(preset) }}
              </button>
            </div>
          </div>

          <!-- Name -->
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('blackboard.scheduleName') }}</label>
            <input
              v-model="form.name"
              class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
              :placeholder="t('blackboard.scheduleNameRequired')"
            />
          </div>

          <!-- Cron Picker -->
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('blackboard.scheduleCron') }}</label>
            <CronPicker ref="cronPickerRef" v-model="form.cron_expr" />
          </div>

          <!-- Message Template -->
          <div>
            <label class="block text-sm text-muted-foreground mb-1">{{ t('blackboard.scheduleMessage') }}</label>
            <textarea
              v-model="form.message_template"
              rows="3"
              class="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/30"
              :placeholder="t('blackboard.scheduleMessageRequired')"
            />
          </div>

          <!-- Actions -->
          <div class="flex justify-end gap-2 pt-1">
            <button
              class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted/50 transition-colors"
              @click="dialogOpen = false"
            >
              {{ t('common.cancel') }}
            </button>
            <button
              class="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 flex items-center gap-1.5"
              :disabled="!formValid || submitting"
              @click="handleSubmit"
            >
              <Loader2 v-if="submitting" class="w-3.5 h-3.5 animate-spin" />
              {{ t('common.confirm') }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
