<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'
import { User, LogOut, Building2 } from 'lucide-vue-next'

const authStore = useAuthStore()
const router = useRouter()
const { t } = useI18n()

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-6 py-8">
    <h1 class="text-xl font-bold mb-6">{{ t('common.settings') }}</h1>

    <!-- 用户信息 -->
    <div class="p-4 rounded-xl border border-border bg-card space-y-4">
      <div class="flex items-center gap-4">
        <div class="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
          <img
            v-if="authStore.user?.avatar_url"
            :src="authStore.user.avatar_url"
            class="w-14 h-14 rounded-full"
            alt="头像"
          />
          <User v-else class="w-7 h-7 text-primary" />
        </div>
        <div>
          <div class="font-medium text-lg">{{ authStore.user?.name }}</div>
          <div class="text-sm text-muted-foreground">{{ authStore.user?.email || '-' }}</div>
        </div>
      </div>
    </div>

    <!-- 操作 -->
    <div class="mt-6 space-y-3">
      <button
        class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-border bg-card text-sm hover:bg-card/80 transition-colors text-red-400"
        @click="handleLogout"
      >
        <LogOut class="w-4 h-4" />
        {{ t('common.logout') }}
      </button>
    </div>
  </div>
</template>
