<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { getCurrentLocale, setCurrentLocale } from '@/i18n'
import { resolveApiErrorMessage } from '@/i18n/error'
import { PawPrint, Loader2, Zap, Shield, Globe, Sparkles, KeyRound, MessageSquareCode, Eye, EyeOff } from 'lucide-vue-next'
import LocaleSelect from '@/components/shared/LocaleSelect.vue'

const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const loading = ref(false)
const error = ref('')
const activeTab = ref<'account' | 'code'>('account')
const isRegister = ref(false)

const accountForm = ref({ account: '', password: '', name: '' })
const showPassword = ref(false)

const codeForm = ref({ account: '', code: '' })
const codeSending = ref(false)
const codeCountdown = ref(0)
let codeTimer: ReturnType<typeof setInterval> | null = null
const locale = ref(getCurrentLocale())

const features = [
  { icon: Zap, title: '一键部署', desc: '零配置启动你的 AI 员工' },
  { icon: Shield, title: '企业级安全', desc: '多租户隔离，数据独占' },
  { icon: Globe, title: '即开即用', desc: '自动域名，HTTPS 就绪' },
  { icon: Sparkles, title: '弹性扩展', desc: '按需选择规格，灵活升降配' },
]

const isAccountEmail = computed(() => accountForm.value.account.includes('@'))

const canSubmitAccount = computed(() => {
  if (isRegister.value) {
    return isAccountEmail.value && accountForm.value.password.length >= 6
  }
  return accountForm.value.account && accountForm.value.password
})

const canSubmitCode = computed(() => {
  return codeForm.value.account.length >= 5 && codeForm.value.code.length >= 4
})

function handleOAuthLogin(provider: string) {
  sessionStorage.setItem('oauth_provider', provider)
  if (provider === 'feishu') {
    const clientId = import.meta.env.VITE_FEISHU_APP_ID || ''
    const redirectUri = encodeURIComponent(window.location.origin + `/login/callback/${provider}`)
    const state = Math.random().toString(36).substring(2)
    window.location.href = `https://passport.feishu.cn/suite/passport/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&state=${state}&scope=contact:user.email:readonly`
  }
}

async function handleAccountSubmit() {
  if (!canSubmitAccount.value || loading.value) return
  loading.value = true
  try {
    if (isRegister.value) {
      await authStore.emailRegister(
        accountForm.value.account,
        accountForm.value.password,
        accountForm.value.name || accountForm.value.account.split('@')[0],
      )
    } else {
      await authStore.accountLogin(accountForm.value.account, accountForm.value.password)
    }
    error.value = ''
    router.replace('/')
  } catch (e: any) {
    error.value = resolveApiErrorMessage(
      e,
      isRegister.value ? t('auth.registerFailed') : t('auth.loginFailed'),
    )
  } finally {
    loading.value = false
  }
}

async function handleSendCode() {
  if (!codeForm.value.account || codeSending.value || codeCountdown.value > 0) return
  codeSending.value = true
  try {
    await authStore.sendVerificationCode(codeForm.value.account)
    codeCountdown.value = 60
    codeTimer = setInterval(() => {
      codeCountdown.value--
      if (codeCountdown.value <= 0 && codeTimer) {
        clearInterval(codeTimer)
        codeTimer = null
      }
    }, 1000)
  } catch (e: any) {
    error.value = resolveApiErrorMessage(e, t('auth.sendFailed'))
  } finally {
    codeSending.value = false
  }
}

async function handleCodeSubmit() {
  if (!canSubmitCode.value || loading.value) return
  loading.value = true
  try {
    await authStore.verificationCodeLogin(codeForm.value.account, codeForm.value.code)
    error.value = ''
    router.replace('/')
  } catch (e: any) {
    error.value = resolveApiErrorMessage(e, t('auth.loginFailed'))
  } finally {
    loading.value = false
  }
}

function onLocaleChange(value: string) {
  locale.value = setCurrentLocale(value)
}

watch(activeTab, () => { error.value = '' })
watch(isRegister, () => { error.value = '' })

</script>

<template>
  <div class="min-h-screen flex">
    <!-- 左侧品牌区 -->
    <div class="hidden lg:flex lg:w-[55%] relative overflow-hidden bg-linear-to-br from-primary/20 via-background to-background">
      <div class="absolute inset-0">
        <div class="absolute top-1/4 left-1/4 w-96 h-96 rounded-full bg-primary/5 blur-3xl" />
        <div class="absolute bottom-1/4 right-1/4 w-64 h-64 rounded-full bg-primary/8 blur-3xl" />
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full border border-primary/5" />
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[400px] h-[400px] rounded-full border border-primary/8" />
      </div>

      <div class="relative z-10 flex flex-col justify-center px-16 xl:px-24">
        <div class="flex items-center gap-3 mb-6">
          <div class="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center">
            <PawPrint class="w-6 h-6 text-primary" />
          </div>
          <span class="text-xl font-bold tracking-tight">DeskClaw</span>
          <span class="px-1.5 py-0.5 text-[10px] font-semibold leading-none rounded bg-primary/15 text-primary">Beta</span>
        </div>

        <h1 class="text-4xl xl:text-5xl font-bold leading-tight mb-4">
          你的 AI 员工<br />
          <span class="text-primary">云端部署平台</span>
        </h1>
        <p class="text-base text-muted-foreground max-w-md mb-12">
          基于 DeskClaw 的 SaaS 部署平台，让每个人都能拥有自己的 AI 员工。无需运维经验，一键创建，即刻使用。
        </p>

        <div class="grid grid-cols-2 gap-4 max-w-md">
          <div
            v-for="f in features"
            :key="f.title"
            class="flex items-start gap-3 p-3 rounded-xl bg-card/40 backdrop-blur-sm border border-border/50"
          >
            <div class="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
              <component :is="f.icon" class="w-4 h-4 text-primary" />
            </div>
            <div>
              <div class="text-sm font-medium">{{ f.title }}</div>
              <div class="text-xs text-muted-foreground mt-0.5">{{ f.desc }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧登录区 -->
    <div class="flex-1 flex items-center justify-center px-6">
      <div class="w-full max-w-sm space-y-6">
        <div class="flex justify-end">
          <LocaleSelect :model-value="locale" @update:model-value="onLocaleChange" />
        </div>
        <!-- 移动端 Logo -->
        <div class="flex flex-col items-center gap-3 lg:hidden">
          <div class="w-12 h-12 rounded-xl bg-primary/15 flex items-center justify-center">
            <PawPrint class="w-7 h-7 text-primary" />
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xl font-bold">DeskClaw</span>
            <span class="px-1.5 py-0.5 text-[10px] font-semibold leading-none rounded bg-primary/15 text-primary">Beta</span>
          </div>
        </div>

        <!-- 标题 -->
        <div class="space-y-1 text-center lg:text-left">
          <h2 class="text-2xl font-bold">{{ isRegister ? t('auth.createAccount') : t('auth.welcomeBack') }}</h2>
          <p class="text-sm text-muted-foreground">
            {{ isRegister ? t('auth.registerSubtitle') : t('auth.loginSubtitle') }}
          </p>
        </div>

          <!-- Tab 切换 -->
          <div class="flex rounded-lg bg-muted p-1 gap-1">
            <button
              class="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md text-sm font-medium transition-all"
              :class="activeTab === 'account' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="activeTab = 'account'"
            >
              <KeyRound class="w-4 h-4" />
              {{ t('auth.accountPasswordLogin') }}
            </button>
            <button
              class="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md text-sm font-medium transition-all"
              :class="activeTab === 'code' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="activeTab = 'code'; isRegister = false"
            >
              <MessageSquareCode class="w-4 h-4" />
              {{ t('auth.verificationCodeLogin') }}
            </button>
          </div>

          <!-- 账号密码表单 -->
          <form v-if="activeTab === 'account'" class="space-y-4" @submit.prevent="handleAccountSubmit">
            <div v-if="isRegister" class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">{{ t('auth.nameLabel') }}</label>
              <input
                v-model="accountForm.name"
                type="text"
                :placeholder="t('auth.namePlaceholder')"
                class="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">{{ t('auth.accountLabel') }}</label>
              <input
                v-model="accountForm.account"
                :type="isRegister ? 'email' : 'text'"
                :placeholder="isRegister ? t('auth.emailPlaceholder') : t('auth.accountPlaceholder')"
                required
                class="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">{{ t('auth.passwordLabel') }}</label>
              <div class="relative">
                <input
                  v-model="accountForm.password"
                  :type="showPassword ? 'text' : 'password'"
                  :placeholder="isRegister ? t('auth.passwordMinLength') : t('auth.passwordPlaceholder')"
                  required
                  class="w-full h-10 px-3 pr-10 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
                />
                <button
                  type="button"
                  tabindex="-1"
                  class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  @click="showPassword = !showPassword"
                >
                  <EyeOff v-if="showPassword" class="w-4 h-4" />
                  <Eye v-else class="w-4 h-4" />
                </button>
              </div>
            </div>

            <button
              type="submit"
              :disabled="!canSubmitAccount || loading"
              class="w-full h-10 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-all hover:shadow-lg hover:shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
              {{ isRegister ? t('auth.register') : t('auth.login') }}
            </button>

            <p class="text-sm text-center text-muted-foreground">
              {{ isRegister ? t('auth.hasAccount') : t('auth.noAccount') }}
              <button
                type="button"
                class="text-primary hover:text-primary/80 font-medium transition-colors"
                @click="isRegister = !isRegister"
              >
                {{ isRegister ? t('auth.signInNow') : t('auth.signUpNow') }}
              </button>
            </p>
          </form>

          <!-- 验证码表单 -->
          <form v-if="activeTab === 'code'" class="space-y-4" @submit.prevent="handleCodeSubmit">
            <div class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">{{ t('auth.accountLabel') }}</label>
              <input
                v-model="codeForm.account"
                type="text"
                :placeholder="t('auth.accountPlaceholder')"
                required
                class="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">{{ t('auth.codeLabel') }}</label>
              <div class="flex gap-2">
                <input
                  v-model="codeForm.code"
                  type="text"
                  inputmode="numeric"
                  maxlength="6"
                  :placeholder="t('auth.codePlaceholder')"
                  required
                  class="flex-1 h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
                />
                <button
                  type="button"
                  :disabled="!codeForm.account || codeForm.account.length < 5 || codeSending || codeCountdown > 0"
                  class="shrink-0 h-10 px-4 rounded-lg border border-input text-sm font-medium hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                  @click="handleSendCode"
                >
                  <Loader2 v-if="codeSending" class="w-4 h-4 animate-spin" />
                  <template v-else-if="codeCountdown > 0">{{ codeCountdown }}s</template>
                  <template v-else>{{ t('auth.sendCode') }}</template>
                </button>
              </div>
            </div>

            <button
              type="submit"
              :disabled="!canSubmitCode || loading"
              class="w-full h-10 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-all hover:shadow-lg hover:shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
              {{ t('auth.login') }}
            </button>

            <p class="text-xs text-center text-muted-foreground">
              {{ t('auth.codeLoginHint') }}
            </p>
          </form>

          <!-- 第三方登录分割线 -->
          <div class="relative my-2">
            <div class="absolute inset-0 flex items-center">
              <div class="w-full border-t border-border" />
            </div>
            <div class="relative flex justify-center text-xs">
              <span class="bg-background px-2 text-muted-foreground">{{ t('auth.orContinueWith') }}</span>
            </div>
          </div>

          <!-- 飞书登录 -->
          <button
            class="w-full h-10 rounded-lg border border-input bg-background text-sm font-medium hover:bg-accent transition-colors flex items-center justify-center gap-2"
            @click="handleOAuthLogin('feishu')"
          >
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none"><path d="M3.536 7.382L13.539 4l1.636 5.676-11.64 3.03V7.383z" fill="#00D6B9"/><path d="M20.464 10.03L13.54 4l-3.073 5.676L20.464 17V10.03z" fill="#133C9A"/><path d="M5.172 12.706L10.465 9.676 20.464 17l-8.925 3.03-6.367-7.324z" fill="#3370FF"/><path d="M5.172 12.706L3.536 7.382l6.929 2.294-5.293 3.03z" fill="#00B2A6"/></svg>
            {{ t('auth.feishuLogin') }}
          </button>

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

        <!-- 底部 -->
        <div class="pt-4 text-center">
          <p class="text-[11px] text-muted-foreground/50">
            DeskClaw &copy; 2026 &middot; by <a href="https://nodesks.ai/" target="_blank" class="hover:text-muted-foreground transition-colors underline underline-offset-2">NoDesk AI</a>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
