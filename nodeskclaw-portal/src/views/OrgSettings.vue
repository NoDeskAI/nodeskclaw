<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { useOrgStore } from '@/stores/org'
import { Settings, Users, Dna, Mail } from 'lucide-vue-next'

const { t } = useI18n()
const route = useRoute()
const orgStore = useOrgStore()

const navItems = [
  { name: 'OrgMembers', label: () => t('orgSettings.humanMembers'), icon: Users },
  { name: 'OrgSettingsGenes', label: () => t('orgSettings.requiredGenesTab'), icon: Dna },
  { name: 'OrgSettingsSmtp', label: () => t('orgSettings.smtpConfigTab'), icon: Mail },
]

onMounted(async () => {
  if (!orgStore.currentOrg) await orgStore.fetchMyOrg()
})
</script>

<template>
  <div class="flex flex-col h-[calc(100vh-3.5rem)] max-w-4xl mx-auto px-6">
    <div class="shrink-0 flex items-center gap-3 pt-8 pb-4">
      <Settings class="w-6 h-6 text-primary" />
      <h1 class="text-xl font-bold">{{ t('orgSettings.title') }}</h1>
    </div>

    <div class="flex gap-6 flex-1 min-h-0 pb-8">
      <nav class="w-40 shrink-0 space-y-1">
        <router-link
          v-for="item in navItems"
          :key="item.name"
          :to="{ name: item.name }"
          class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors"
          :class="route.name === item.name
            ? 'bg-primary/10 text-primary font-medium'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'"
        >
          <component :is="item.icon" class="w-4 h-4" />
          {{ item.label() }}
        </router-link>
      </nav>

      <div class="flex-1 min-w-0 overflow-y-auto pr-3">
        <div class="pb-4">
          <router-view />
        </div>
      </div>
    </div>
  </div>
</template>
