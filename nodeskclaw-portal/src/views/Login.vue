<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { getCurrentLocale, setCurrentLocale } from '@/i18n'
import { resolveApiErrorMessage } from '@/i18n/error'
import { PawPrint, Loader2, Zap, Shield, Globe, Sparkles, Mail, Phone, Eye, EyeOff } from 'lucide-vue-next'
import LocaleSelect from '@/components/shared/LocaleSelect.vue'

const router = useRouter()
const authStore = useAuthStore()
const { t } = useI18n()

const loading = ref(false)
const error = ref('')
const activeTab = ref<'email' | 'phone'>('email')
const isRegister = ref(false)

const emailForm = ref({ email: '', password: '', name: '' })
const showPassword = ref(false)

const phoneForm = ref({ phone: '', code: '' })
const smsSending = ref(false)
const smsCountdown = ref(0)
let smsTimer: ReturnType<typeof setInterval> | null = null
const locale = ref(getCurrentLocale())

const features = [
  { icon: Zap, title: '一键部署', desc: '零配置启动你的 AI 助手' },
  { icon: Shield, title: '企业级安全', desc: '多租户隔离，数据独占' },
  { icon: Globe, title: '即开即用', desc: '自动域名，HTTPS 就绪' },
  { icon: Sparkles, title: '弹性扩展', desc: '按需选择规格，灵活升降配' },
]

const canSubmitEmail = computed(() => {
  if (isRegister.value) {
    return emailForm.value.email && emailForm.value.password.length >= 6
  }
  return emailForm.value.email && emailForm.value.password
})

const canSubmitPhone = computed(() => {
  return phoneForm.value.phone.length >= 8 && phoneForm.value.code.length >= 4
})

function handleOAuthLogin(provider: string) {
  sessionStorage.setItem('oauth_provider', provider)
  if (provider === 'feishu') {
    const clientId = import.meta.env.VITE_FEISHU_APP_ID || ''
    const redirectUri = encodeURIComponent(window.location.origin + `/login/callback/${provider}`)
    const state = Math.random().toString(36).substring(2)
    window.location.href = `https://passport.feishu.cn/suite/passport/oauth/authorize?client_id=${clientId}&redirect_uri=${redirectUri}&response_type=code&state=${state}`
  }
}

async function handleEmailSubmit() {
  if (!canSubmitEmail.value || loading.value) return
  loading.value = true
  try {
    if (isRegister.value) {
      await authStore.emailRegister(
        emailForm.value.email,
        emailForm.value.password,
        emailForm.value.name || emailForm.value.email.split('@')[0],
      )
    } else {
      await authStore.emailLogin(emailForm.value.email, emailForm.value.password)
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

async function handleSendSms() {
  if (!phoneForm.value.phone || smsSending.value || smsCountdown.value > 0) return
  smsSending.value = true
  try {
    await authStore.sendSmsCode(phoneForm.value.phone)
    smsCountdown.value = 60
    smsTimer = setInterval(() => {
      smsCountdown.value--
      if (smsCountdown.value <= 0 && smsTimer) {
        clearInterval(smsTimer)
        smsTimer = null
      }
    }, 1000)
  } catch (e: any) {
    error.value = resolveApiErrorMessage(e, t('auth.sendFailed'))
  } finally {
    smsSending.value = false
  }
}

async function handlePhoneSubmit() {
  if (!canSubmitPhone.value || loading.value) return
  loading.value = true
  try {
    await authStore.smsLogin(phoneForm.value.phone, phoneForm.value.code)
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

// 切换 tab 或模式时清空错误
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
          <span class="text-xl font-bold tracking-tight">NoDeskClaw</span>
        </div>

        <h1 class="text-4xl xl:text-5xl font-bold leading-tight mb-4">
          你的 AI 助手<br />
          <span class="text-primary">云端部署平台</span>
        </h1>
        <p class="text-base text-muted-foreground max-w-md mb-12">
          基于 OpenClaw 的 SaaS 部署平台，让每个人都能拥有自己的 AI 助手。无需运维经验，一键创建，即刻使用。
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
          <span class="text-xl font-bold">NoDeskClaw</span>
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
              :class="activeTab === 'email' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="activeTab = 'email'"
            >
              <Mail class="w-4 h-4" />
              {{ isRegister ? t('auth.emailRegister') : t('auth.emailLogin') }}
            </button>
            <button
              class="flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-md text-sm font-medium transition-all"
              :class="activeTab === 'phone' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'"
              @click="activeTab = 'phone'; isRegister = false"
            >
              <Phone class="w-4 h-4" />
              {{ t('auth.phoneLogin') }}
            </button>
          </div>

          <!-- 邮箱表单 -->
          <form v-if="activeTab === 'email'" class="space-y-4" @submit.prevent="handleEmailSubmit">
            <!-- 注册时的名称 -->
            <div v-if="isRegister" class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">名称</label>
              <input
                v-model="emailForm.name"
                type="text"
                placeholder="你的名字（可选）"
                class="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">邮箱</label>
              <input
                v-model="emailForm.email"
                type="email"
                placeholder="name@example.com"
                required
                class="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
              />
            </div>

            <div class="space-y-1.5">
              <div class="flex items-center justify-between">
                <label class="text-sm font-medium text-foreground">密码</label>
                <button
                  v-if="!isRegister"
                  type="button"
                  tabindex="-1"
                  class="text-xs text-primary hover:text-primary/80 transition-colors"
                >
                  忘记密码？
                </button>
              </div>
              <div class="relative">
                <input
                  v-model="emailForm.password"
                  :type="showPassword ? 'text' : 'password'"
                  :placeholder="isRegister ? '至少 6 位' : '输入密码'"
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
              :disabled="!canSubmitEmail || loading"
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

          <!-- 手机表单 -->
          <form v-if="activeTab === 'phone'" class="space-y-4" @submit.prevent="handlePhoneSubmit">
            <div class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">手机号</label>
              <input
                v-model="phoneForm.phone"
                type="tel"
                placeholder="输入手机号"
                required
                class="w-full h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
              />
            </div>

            <div class="space-y-1.5">
              <label class="text-sm font-medium text-foreground">验证码</label>
              <div class="flex gap-2">
                <input
                  v-model="phoneForm.code"
                  type="text"
                  inputmode="numeric"
                  maxlength="6"
                  placeholder="6 位验证码"
                  required
                  class="flex-1 h-10 px-3 rounded-lg border border-input bg-background text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1 transition-shadow"
                />
                <button
                  type="button"
                  :disabled="!phoneForm.phone || phoneForm.phone.length < 8 || smsSending || smsCountdown > 0"
                  class="shrink-0 h-10 px-4 rounded-lg border border-input text-sm font-medium hover:bg-accent transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                  @click="handleSendSms"
                >
                  <Loader2 v-if="smsSending" class="w-4 h-4 animate-spin" />
                  <template v-else-if="smsCountdown > 0">{{ smsCountdown }}s</template>
                  <template v-else>{{ t('auth.sendCode') }}</template>
                </button>
              </div>
            </div>

            <button
              type="submit"
              :disabled="!canSubmitPhone || loading"
              class="w-full h-10 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-all hover:shadow-lg hover:shadow-primary/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
              {{ t('auth.loginOrRegister') }}
            </button>

            <p class="text-xs text-center text-muted-foreground">
              未注册的手机号将自动创建账户
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
            NoDeskClaw &copy; 2026 &middot; by <a href="https://nodesks.ai/" target="_blank" class="hover:text-muted-foreground transition-colors underline underline-offset-2">NoDesk AI</a>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
