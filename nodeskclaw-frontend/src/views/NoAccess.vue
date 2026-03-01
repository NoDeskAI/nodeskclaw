<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { ShieldOff } from 'lucide-vue-next'

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-background">
    <div class="text-center max-w-md px-6">
      <ShieldOff class="w-16 h-16 mx-auto mb-6 text-muted-foreground" />
      <h1 class="text-2xl font-semibold mb-3">{{ t('no_access.title') }}</h1>
      <p class="text-muted-foreground mb-8">{{ t('no_access.description') }}</p>
      <Button variant="outline" @click="handleLogout">
        {{ t('no_access.logout') }}
      </Button>
    </div>
  </div>
</template>
