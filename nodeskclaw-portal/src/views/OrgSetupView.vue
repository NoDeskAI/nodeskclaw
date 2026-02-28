<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { resolveApiErrorMessage } from '@/i18n/error'
import api from '@/services/api'
import { PawPrint, Building2, Loader2, ChevronDown } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const form = ref({
  name: '',
  slug: '',
  job_title: '',
})
const loading = ref(false)
const error = ref('')
const slugManuallyEdited = ref(false)

const JOB_TITLE_OPTIONS = [
  { value: 'founder', labelKey: 'orgSetup.jobTitles.founder' },
  { value: 'cto', labelKey: 'orgSetup.jobTitles.cto' },
  { value: 'engineer', labelKey: 'orgSetup.jobTitles.engineer' },
  { value: 'pm', labelKey: 'orgSetup.jobTitles.pm' },
  { value: 'designer', labelKey: 'orgSetup.jobTitles.designer' },
  { value: 'ops', labelKey: 'orgSetup.jobTitles.ops' },
  { value: 'manager', labelKey: 'orgSetup.jobTitles.manager' },
  { value: 'other', labelKey: 'orgSetup.jobTitles.other' },
]

function toSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[\u4e00-\u9fff]/g, '')
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 64)
}

watch(() => form.value.name, (val) => {
  if (!slugManuallyEdited.value) {
    form.value.slug = toSlug(val)
  }
})

const slugValid = computed(() => {
  return /^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$/.test(form.value.slug)
})

const canSubmit = computed(() => {
  return form.value.name.trim() && slugValid.value && form.value.job_title
})

async function handleSubmit() {
  if (!canSubmit.value || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const provider = authStore.lastOAuthProvider || 'feishu'
    await api.post('/orgs/oauth-setup', {
      provider,
      name: form.value.name.trim(),
      slug: form.value.slug,
      job_title: form.value.job_title,
    })
    await authStore.fetchUser()
    router.replace('/')
  } catch (e: any) {
    error.value = resolveApiErrorMessage(e, t('orgSetup.setupFailed'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background px-4">
    <div class="w-full max-w-md space-y-8">
      <!-- Logo -->
      <div class="flex flex-col items-center gap-3">
        <div class="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center">
          <PawPrint class="w-7 h-7 text-primary" />
        </div>
        <h1 class="text-2xl font-bold">{{ t('orgSetup.title') }}</h1>
        <p class="text-sm text-muted-foreground text-center max-w-sm">
          {{ t('orgSetup.subtitle') }}
        </p>
      </div>

      <!-- 表单 -->
      <form class="space-y-5" @submit.prevent="handleSubmit">
        <!-- 企业名称 -->
        <div class="space-y-1.5">
          <label class="text-sm font-medium text-foreground">{{ t('orgSetup.orgName') }}</label>
          <div class="relative">
            <Building2 class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              v-model="form.name"
              type="text"
              :placeholder="t('orgSetup.orgNamePlaceholder')"
              required
              class="w-full h-10 pl-10 pr-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
            />
          </div>
        </div>

        <!-- 企业标识符 -->
        <div class="space-y-1.5">
          <label class="text-sm font-medium text-foreground">{{ t('orgSetup.orgSlug') }}</label>
          <input
            v-model="form.slug"
            type="text"
            :placeholder="t('orgSetup.orgSlugPlaceholder')"
            required
            class="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
            @input="slugManuallyEdited = true"
          />
          <p v-if="form.slug && !slugValid" class="text-xs text-destructive">
            {{ t('orgSetup.slugInvalid') }}
          </p>
          <p v-else class="text-xs text-muted-foreground">
            {{ t('orgSetup.slugHint') }}
          </p>
        </div>

        <!-- 职位 -->
        <div class="space-y-1.5">
          <label class="text-sm font-medium text-foreground">{{ t('orgSetup.jobTitle') }}</label>
          <div class="relative">
            <select
              v-model="form.job_title"
              required
              class="w-full h-10 px-3 pr-8 rounded-lg border border-input bg-background text-sm appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
              :class="{ 'text-muted-foreground': !form.job_title }"
            >
              <option value="" disabled>{{ t('orgSetup.jobTitlePlaceholder') }}</option>
              <option v-for="opt in JOB_TITLE_OPTIONS" :key="opt.value" :value="opt.value">
                {{ t(opt.labelKey) }}
              </option>
            </select>
            <ChevronDown class="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
          </div>
        </div>

        <!-- 错误提示 -->
        <Transition
          enter-active-class="transition duration-200 ease-out"
          enter-from-class="opacity-0 -translate-y-1"
          enter-to-class="opacity-100 translate-y-0"
          leave-active-class="transition duration-150 ease-in"
          leave-from-class="opacity-100 translate-y-0"
          leave-to-class="opacity-0 -translate-y-1"
        >
          <p v-if="error" class="text-sm text-destructive text-center bg-destructive/10 rounded-lg py-2.5 px-3 border border-destructive/20">
            {{ error }}
          </p>
        </Transition>

        <!-- 提交按钮 -->
        <button
          type="submit"
          :disabled="!canSubmit || loading"
          class="w-full h-10 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-all hover:shadow-lg hover:shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
          {{ t('orgSetup.submit') }}
        </button>
      </form>

      <p class="text-[11px] text-muted-foreground/50 text-center">
        NoDeskClaw &copy; 2026 &middot; by <a href="https://nodesks.ai/" target="_blank" class="hover:text-muted-foreground transition-colors underline underline-offset-2">NoDesk AI</a>
      </p>
    </div>
  </div>
</template>
