<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Save, Trash2, Loader2, Users, Palette, UserPlus, Search, Shield, ShieldCheck, X, LayoutTemplate, ChevronRight } from 'lucide-vue-next'
import Workspace2D from '@/components/hex2d/Workspace2D.vue'
import {
  useWorkspaceStore,
  WORKSPACE_PERMISSIONS,
  PERMISSION_PRESETS,
  type TemplateCollectPreview,
  type WorkspaceMemberInfo,
} from '@/stores/workspace'
import { useAuthStore } from '@/stores/auth'
import { resolveApiErrorMessage } from '@/i18n/error'
import { useToast } from '@/composables/useToast'
import { useConfirm } from '@/composables/useConfirm'
import CustomSelect from '@/components/shared/CustomSelect.vue'
import {
  buildTopoNodes,
  buildTopoEdges,
  buildMockAgents,
  specGeneSlugs as _specGeneSlugs,
  specLlmProviders as _specLlmProviders,
  resourceSummary as _resourceSummary,
  specGeneCount as _specGeneCount,
  allSelectableKeys,
  countAgentKeysInSelection,
  keysToExcludedIndices,
  keysToExcludedCorridorCoords,
} from '@/utils/templateTopology'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useWorkspaceStore()
const authStore = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()

const workspaceId = computed(() => route.params.id as string)
const canManageMembers = computed(() => store.hasPermission('manage_members'))
const canManageSettings = computed(() => store.hasPermission('manage_settings'))
const canDeleteWorkspace = computed(() => store.hasPermission('delete_workspace'))

const name = ref('')
const description = ref('')
const color = ref('#a78bfa')
const saving = ref(false)
const deleting = ref(false)

const colors = [
  '#a78bfa', '#60a5fa', '#34d399', '#fbbf24',
  '#f87171', '#f472b6', '#38bdf8', '#a3e635',
]

onMounted(async () => {
  await store.fetchWorkspace(workspaceId.value)
  await store.fetchMyPermissions(workspaceId.value)
  await store.fetchMembers(workspaceId.value)
  if (store.currentWorkspace) {
    name.value = store.currentWorkspace.name
    description.value = store.currentWorkspace.description
    color.value = store.currentWorkspace.color
  }
})

async function handleSave() {
  saving.value = true
  try {
    await store.updateWorkspace(workspaceId.value, {
      name: name.value.trim(),
      description: description.value.trim(),
      color: color.value,
    })
    toast.success(t('workspaceSettings.saved'))
  } catch (e) {
    toast.error(resolveApiErrorMessage(e, t('workspaceSettings.saveFailed')))
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  const ok = await confirm({
    title: t('workspaceSettings.deleteWorkspace'),
    description: t('workspaceSettings.deleteConfirm'),
    variant: 'danger',
  })
  if (!ok) return
  deleting.value = true
  try {
    await store.deleteWorkspace(workspaceId.value)
    router.push('/')
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, t('workspaceSettings.deleteFailed')))
  } finally {
    deleting.value = false
  }
}

// ── Member Management ────────────────────────────────

const PRESET_KEYS = ['administrator', 'collaborator', 'observer', 'custom'] as const

function presetLabel(key: string): string {
  return t(`workspaceSettings.preset_${key}`)
}

const presetOptions = computed(() =>
  PRESET_KEYS.map(pk => ({ value: pk, label: presetLabel(pk) }))
)

function permLabel(key: string): string {
  return t(`workspaceSettings.perm_${key}`)
}

function detectPreset(isAdmin: boolean, permissions: string[]): string {
  if (isAdmin) return 'administrator'
  const sorted = [...permissions].sort()
  for (const [key, preset] of Object.entries(PERMISSION_PRESETS)) {
    if (!preset.is_admin && [...preset.permissions].sort().join(',') === sorted.join(',')) {
      return key
    }
  }
  return 'custom'
}

// ── Add Member Dialog ────────────────────────────────

const showAddDialog = ref(false)
const searchQuery = ref('')
const searchResults = ref<{ user_id: string; name: string; email: string; avatar_url: string | null }[]>([])
const searching = ref(false)
const addPreset = ref('collaborator')
const addPermissions = ref<string[]>([...PERMISSION_PRESETS.collaborator.permissions])
const addIsAdmin = ref(false)
const addingUserId = ref<string | null>(null)

function onPresetChange(presetKey: string) {
  addPreset.value = presetKey
  if (presetKey === 'administrator') {
    addIsAdmin.value = true
    addPermissions.value = [...WORKSPACE_PERMISSIONS]
  } else if (presetKey === 'custom') {
    addIsAdmin.value = false
  } else {
    addIsAdmin.value = false
    const preset = PERMISSION_PRESETS[presetKey]
    addPermissions.value = preset ? [...preset.permissions] : []
  }
}

function onAddPermToggle(perm: string) {
  if (addIsAdmin.value) return
  const idx = addPermissions.value.indexOf(perm)
  if (idx >= 0) addPermissions.value.splice(idx, 1)
  else addPermissions.value.push(perm)
  addPreset.value = detectPreset(addIsAdmin.value, addPermissions.value)
}

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(doSearch, 300)
}

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) { searchResults.value = []; return }
  searching.value = true
  try {
    searchResults.value = await store.searchOrgUsers(workspaceId.value, q)
  } catch (e) {
    console.error('search error:', e)
  } finally {
    searching.value = false
  }
}

async function handleAddMember(userId: string) {
  addingUserId.value = userId
  try {
    await store.addMember(workspaceId.value, userId, addPermissions.value, addIsAdmin.value)
    toast.success(t('workspaceSettings.memberAdded'))
    searchResults.value = searchResults.value.filter(u => u.user_id !== userId)
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, t('workspaceSettings.addMemberFailed')))
  } finally {
    addingUserId.value = null
  }
}

function openAddDialog() {
  searchQuery.value = ''
  searchResults.value = []
  addPreset.value = 'collaborator'
  addPermissions.value = [...PERMISSION_PRESETS.collaborator.permissions]
  addIsAdmin.value = false
  showAddDialog.value = true
}

// ── Edit Member ──────────────────────────────────────

const editingMemberId = ref<string | null>(null)
const editPreset = ref('custom')
const editPermissions = ref<string[]>([])
const editIsAdmin = ref(false)
const editSaving = ref(false)

function startEdit(member: WorkspaceMemberInfo) {
  editingMemberId.value = member.user_id
  editIsAdmin.value = member.is_admin
  editPermissions.value = [...member.permissions]
  editPreset.value = detectPreset(member.is_admin, member.permissions)
}

function cancelEdit() {
  editingMemberId.value = null
}

function onEditPresetChange(presetKey: string) {
  editPreset.value = presetKey
  if (presetKey === 'administrator') {
    editIsAdmin.value = true
    editPermissions.value = [...WORKSPACE_PERMISSIONS]
  } else if (presetKey === 'custom') {
    editIsAdmin.value = false
  } else {
    editIsAdmin.value = false
    const preset = PERMISSION_PRESETS[presetKey]
    editPermissions.value = preset ? [...preset.permissions] : []
  }
}

function onEditPermToggle(perm: string) {
  if (editIsAdmin.value) return
  const idx = editPermissions.value.indexOf(perm)
  if (idx >= 0) editPermissions.value.splice(idx, 1)
  else editPermissions.value.push(perm)
  editPreset.value = detectPreset(editIsAdmin.value, editPermissions.value)
}

async function handleSavePermissions() {
  if (!editingMemberId.value) return
  editSaving.value = true
  try {
    await store.updateMember(
      workspaceId.value,
      editingMemberId.value,
      editIsAdmin.value ? undefined : editPermissions.value,
      editIsAdmin.value,
    )
    toast.success(t('workspaceSettings.permissionsUpdated'))
    editingMemberId.value = null
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, t('workspaceSettings.updateFailed')))
  } finally {
    editSaving.value = false
  }
}

// ── Remove Member ────────────────────────────────────

// ── Save as Template ─────────────────────────────────

const showTemplateDialog = ref(false)
const templateName = ref('')
const templateDesc = ref('')
const savingTemplate = ref(false)
const templatePreviewLoading = ref(false)
const templatePreviewError = ref('')
const templatePreview = ref<TemplateCollectPreview | null>(null)

const saveSelectedKeys = ref<Set<string>>(new Set())

function handleTopoToggle(key: string) {
  const s = new Set(saveSelectedKeys.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  saveSelectedKeys.value = s
}

const saveSelectedCount = computed(() =>
  countAgentKeysInSelection((templatePreview.value?.agent_specs ?? []) as Record<string, unknown>[], saveSelectedKeys.value)
)

const selectedSpecIndex = ref<number | null>(null)
const selectedSpec = computed(() =>
  selectedSpecIndex.value !== null ? templatePreview.value?.agent_specs[selectedSpecIndex.value] ?? null : null
)

function openSpecDetail(index: number) {
  selectedSpecIndex.value = index
}

function closeSpecDetail() {
  selectedSpecIndex.value = null
}

const previewTopoNodes = computed(() => {
  const preview = templatePreview.value
  if (!preview) return []
  return buildTopoNodes({
    agent_specs: preview.agent_specs as Record<string, unknown>[],
    human_specs: preview.human_specs as Record<string, unknown>[],
    topology_snapshot: preview.topology_snapshot as { nodes?: Record<string, unknown>[]; edges?: Record<string, unknown>[] } | undefined,
  })
})

const previewTopoEdges = computed(() => {
  const preview = templatePreview.value
  if (!preview) return []
  return buildTopoEdges({
    agent_specs: [],
    human_specs: [],
    topology_snapshot: preview.topology_snapshot as { nodes?: Record<string, unknown>[]; edges?: Record<string, unknown>[] } | undefined,
  })
})

const previewAgents = computed(() =>
  buildMockAgents((templatePreview.value?.agent_specs ?? []) as Record<string, unknown>[])
)

const specGeneSlugs = _specGeneSlugs
const specLlmProviders = _specLlmProviders
const resourceSummary = _resourceSummary
const specGeneCount = _specGeneCount

async function openTemplateDialog() {
  templateName.value = store.currentWorkspace?.name ? `${store.currentWorkspace.name}` : ''
  templateDesc.value = ''
  templatePreview.value = null
  templatePreviewError.value = ''
  templatePreviewLoading.value = true
  showTemplateDialog.value = true
  try {
    templatePreview.value = await store.fetchTemplateCollectPreview(workspaceId.value)
    const specs = templatePreview.value?.agent_specs ?? []
    const topo = templatePreview.value?.topology_snapshot as { nodes?: Record<string, unknown>[] } | undefined
    saveSelectedKeys.value = allSelectableKeys(specs as Record<string, unknown>[], topo)
  } catch (e) {
    templatePreviewError.value = resolveApiErrorMessage(e, t('workspaceSettings.templatePreviewFailed'))
  } finally {
    templatePreviewLoading.value = false
  }
}

async function handleSaveAsTemplate() {
  if (!templateName.value.trim() || saveSelectedCount.value === 0) return
  savingTemplate.value = true
  const specs = templatePreview.value?.agent_specs ?? []
  const excluded = keysToExcludedIndices(specs as Record<string, unknown>[], saveSelectedKeys.value)
  const topo = templatePreview.value?.topology_snapshot as { nodes?: Record<string, unknown>[] } | undefined
  const excludedCorridors = keysToExcludedCorridorCoords(topo, saveSelectedKeys.value)
  try {
    await store.saveAsTemplate({
      name: templateName.value.trim(),
      description: templateDesc.value.trim(),
      workspace_id: workspaceId.value,
      visibility: 'org_private',
      excluded_agent_indices: excluded.length > 0 ? excluded : undefined,
      excluded_corridor_coords: excludedCorridors.length > 0 ? excludedCorridors : undefined,
    })
    toast.success(t('workspaceSettings.templateSaved'))
    showTemplateDialog.value = false
    templatePreview.value = null
    templatePreviewError.value = ''
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, t('workspaceSettings.templateSaveFailed')))
  } finally {
    savingTemplate.value = false
  }
}

// ── Remove Member ────────────────────────────────────

const removingUserId = ref<string | null>(null)

async function handleRemoveMember(member: WorkspaceMemberInfo) {
  if (member.user_id === authStore.user?.id) {
    toast.error(t('workspaceSettings.cannotRemoveSelf'))
    return
  }
  if (member.is_admin) {
    const adminCount = store.members.filter(m => m.is_admin).length
    if (adminCount <= 1) {
      toast.error(t('workspaceSettings.lastAdmin'))
      return
    }
  }
  const ok = await confirm({
    title: t('workspaceSettings.removeMemberTitle'),
    description: t('workspaceSettings.removeMemberConfirm', { name: member.user_name }),
    variant: 'danger',
  })
  if (!ok) return
  removingUserId.value = member.user_id
  try {
    await store.removeMember(workspaceId.value, member.user_id)
    toast.success(t('workspaceSettings.memberRemoved'))
  } catch (e: any) {
    toast.error(resolveApiErrorMessage(e, t('workspaceSettings.removeFailed')))
  } finally {
    removingUserId.value = null
  }
}
</script>

<template>
  <div class="max-w-xl mx-auto px-6 py-8">
    <!-- Header -->
    <div class="flex items-center gap-3 mb-8">
      <button class="p-1.5 rounded-lg hover:bg-muted transition-colors" @click="router.push(`/workspace/${workspaceId}`)">
        <ArrowLeft class="w-5 h-5" />
      </button>
      <h1 class="text-xl font-bold">{{ t('workspaceSettings.title') }}</h1>
    </div>

    <div class="space-y-6">
      <!-- Basic Settings -->
      <div class="space-y-2">
        <label class="text-sm font-medium">{{ t('workspaceSettings.nameLabel') }}</label>
        <input
          v-model="name"
          :disabled="!canManageSettings"
          class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50 disabled:opacity-50"
        />
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium">{{ t('workspaceSettings.descriptionLabel') }}</label>
        <textarea
          v-model="description"
          :disabled="!canManageSettings"
          rows="3"
          class="w-full px-3 py-2 rounded-lg bg-muted border border-border text-sm outline-none focus:ring-1 focus:ring-primary/50 resize-none disabled:opacity-50"
        />
      </div>

      <div class="space-y-2">
        <label class="text-sm font-medium flex items-center gap-1.5">
          <Palette class="w-4 h-4 text-muted-foreground" />
          {{ t('workspaceSettings.themeColor') }}
        </label>
        <div class="flex gap-2">
          <button
            v-for="c in colors"
            :key="c"
            class="w-8 h-8 rounded-full border-2 transition-all"
            :class="[
              color === c ? 'border-white scale-110' : 'border-transparent hover:scale-105',
              !canManageSettings ? 'opacity-50 pointer-events-none' : '',
            ]"
            :style="{ backgroundColor: c }"
            @click="color = c"
          />
        </div>
      </div>

      <!-- Members -->
      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-medium flex items-center gap-1.5">
            <Users class="w-4 h-4 text-muted-foreground" />
            {{ t('workspaceSettings.members', { count: store.members.length }) }}
          </h3>
          <button
            v-if="canManageMembers"
            class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:bg-primary/90 transition-colors"
            @click="openAddDialog"
          >
            <UserPlus class="w-3.5 h-3.5" />
            {{ t('workspaceSettings.addMember') }}
          </button>
        </div>

        <div class="space-y-2">
          <div
            v-for="m in store.members"
            :key="m.user_id"
            class="rounded-lg bg-muted overflow-hidden"
          >
            <div class="flex items-center gap-3 py-2.5 px-3">
              <div class="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center text-xs font-medium shrink-0">
                {{ m.user_name?.[0] || '?' }}
              </div>
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium truncate">{{ m.user_name }}</p>
                <div class="flex items-center gap-1.5 mt-0.5">
                  <span v-if="m.is_admin" class="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary">
                    <ShieldCheck class="w-3 h-3" />
                    {{ t('workspaceSettings.preset_administrator') }}
                  </span>
                  <span
                    v-for="perm in m.permissions.slice(0, 3)"
                    v-else
                    :key="perm"
                    class="text-[10px] px-1.5 py-0.5 rounded bg-accent text-accent-foreground"
                  >{{ permLabel(perm) }}</span>
                  <span v-if="!m.is_admin && m.permissions.length > 3" class="text-[10px] text-muted-foreground">
                    +{{ m.permissions.length - 3 }}
                  </span>
                </div>
              </div>
              <div v-if="canManageMembers" class="flex items-center gap-1 shrink-0">
                <button
                  class="p-1 rounded hover:bg-accent transition-colors text-muted-foreground hover:text-foreground"
                  :title="t('workspaceSettings.editPermissions')"
                  @click="editingMemberId === m.user_id ? cancelEdit() : startEdit(m)"
                >
                  <Shield class="w-3.5 h-3.5" />
                </button>
                <button
                  v-if="m.user_id !== authStore.user?.id"
                  class="p-1 rounded hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                  :disabled="removingUserId === m.user_id"
                  @click="handleRemoveMember(m)"
                >
                  <Loader2 v-if="removingUserId === m.user_id" class="w-3.5 h-3.5 animate-spin" />
                  <Trash2 v-else class="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <!-- Edit permissions inline -->
            <div v-if="editingMemberId === m.user_id" class="border-t border-border/50 px-3 py-3 space-y-3">
              <div class="flex items-center gap-2">
                <label class="text-xs text-muted-foreground shrink-0">{{ t('workspaceSettings.presetRole') }}</label>
                <CustomSelect
                  :model-value="editPreset"
                  :options="presetOptions"
                  size="xs"
                  trigger-class="flex-1"
                  @update:model-value="(v: string | null) => onEditPresetChange(v!)"
                />
              </div>
              <div class="grid grid-cols-2 gap-1.5">
                <label
                  v-for="perm in WORKSPACE_PERMISSIONS"
                  :key="perm"
                  class="flex items-center gap-1.5 text-xs cursor-pointer select-none"
                  :class="editIsAdmin ? 'opacity-50' : ''"
                >
                  <input
                    type="checkbox"
                    :checked="editPermissions.includes(perm)"
                    :disabled="editIsAdmin"
                    class="rounded border-border"
                    @change="onEditPermToggle(perm)"
                  />
                  {{ permLabel(perm) }}
                </label>
              </div>
              <div class="flex justify-end gap-2">
                <button class="px-3 py-1 text-xs rounded bg-muted hover:bg-accent transition-colors" @click="cancelEdit">
                  {{ t('workspaceSettings.cancel') }}
                </button>
                <button
                  class="px-3 py-1 text-xs rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                  :disabled="editSaving"
                  @click="handleSavePermissions"
                >
                  <Loader2 v-if="editSaving" class="w-3 h-3 animate-spin inline mr-1" />
                  {{ t('workspaceSettings.save') }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Save / Template / Delete -->
      <div class="flex gap-3">
        <button
          v-if="canManageSettings"
          class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          :disabled="saving"
          @click="handleSave"
        >
          <Loader2 v-if="saving" class="w-4 h-4 animate-spin" />
          <Save v-else class="w-4 h-4" />
          {{ t('workspaceSettings.save') }}
        </button>
        <button
          v-if="canManageSettings"
          class="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent text-accent-foreground text-sm font-medium hover:bg-accent/80 transition-colors"
          @click="openTemplateDialog"
        >
          <LayoutTemplate class="w-4 h-4" />
          {{ t('workspaceSettings.saveAsTemplate') }}
        </button>
        <button
          v-if="canDeleteWorkspace"
          class="px-4 py-2.5 rounded-lg border border-destructive text-destructive text-sm font-medium hover:bg-destructive/10 transition-colors disabled:opacity-50"
          :disabled="deleting"
          @click="handleDelete"
        >
          <Loader2 v-if="deleting" class="w-4 h-4 animate-spin" />
          <Trash2 v-else class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Save as Template Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showTemplateDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="showTemplateDialog = false">
          <div class="bg-card rounded-xl shadow-2xl w-full max-w-lg border border-border max-h-[90vh] flex flex-col">
            <div class="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
              <h3 class="text-sm font-semibold">{{ t('workspaceSettings.saveAsTemplate') }}</h3>
              <button type="button" class="p-1 rounded hover:bg-muted" @click="showTemplateDialog = false">
                <X class="w-4 h-4" />
              </button>
            </div>
            <div class="px-5 py-4 space-y-4 overflow-y-auto">
              <div class="space-y-1.5">
                <label class="text-xs font-medium text-muted-foreground">{{ t('workspaceSettings.templateNameLabel') }}</label>
                <input
                  v-model="templateName"
                  class="w-full px-3 py-2 text-sm rounded-lg bg-muted border border-border outline-none focus:ring-1 focus:ring-primary/50"
                  :placeholder="t('workspaceSettings.templateNamePlaceholder')"
                />
              </div>
              <div class="space-y-1.5">
                <label class="text-xs font-medium text-muted-foreground">{{ t('workspaceSettings.templateDescLabel') }}</label>
                <textarea
                  v-model="templateDesc"
                  rows="2"
                  class="w-full px-3 py-2 text-sm rounded-lg bg-muted border border-border outline-none focus:ring-1 focus:ring-primary/50 resize-none"
                  :placeholder="t('workspaceSettings.templateDescPlaceholder')"
                />
              </div>

              <div v-if="templatePreviewLoading" class="flex items-center gap-2 text-xs text-muted-foreground py-2">
                <Loader2 class="w-4 h-4 animate-spin" />
                {{ t('workspaceSettings.templatePreviewLoading') }}
              </div>
              <p v-else-if="templatePreviewError" class="text-xs text-red-400">{{ templatePreviewError }}</p>

              <div v-else-if="templatePreview" class="space-y-4">
                <div class="rounded-lg border border-border p-3 space-y-2">
                  <p class="text-xs font-medium text-muted-foreground">{{ t('workspaceSettings.teamPreviewTitle') }}</p>
                  <ul class="text-xs space-y-1 max-h-40 overflow-y-auto">
                    <li
                      v-for="(spec, si) in templatePreview.agent_specs"
                      :key="si"
                      class="flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-muted/50 transition-colors cursor-pointer"
                      @click="openSpecDetail(si)"
                    >
                      <div class="flex-1 min-w-0">
                        <span class="font-medium text-foreground">{{ (spec.display_name as string) || (spec.label as string) || '—' }}</span>
                        <span class="text-muted-foreground ml-2">
                          {{ t('workspaceSettings.templatePreviewGeneLine', { count: specGeneCount(spec) }) }}
                          <template v-if="resourceSummary(spec)"> · {{ resourceSummary(spec) }}</template>
                        </span>
                      </div>
                      <ChevronRight class="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                    </li>
                  </ul>
                  <template v-if="templatePreview.human_specs.length">
                    <p class="text-xs font-medium text-muted-foreground pt-1">{{ t('workspaceSettings.humanPlaceholdersTitle') }}</p>
                    <ul class="text-xs space-y-1 text-muted-foreground">
                      <li v-for="(h, hi) in templatePreview.human_specs" :key="hi">
                        {{ (h as { display_name?: string }).display_name || '—' }}
                        ({{ t('workspaceSettings.humanPlaceholderRow') }})
                      </li>
                    </ul>
                  </template>
                </div>

                <div v-if="previewTopoNodes.length" class="rounded-lg border border-border overflow-hidden">
                  <p class="text-xs font-medium text-muted-foreground px-3 pt-2.5 pb-1">{{ t('workspaceSettings.topoSelectHint') }}</p>
                  <div class="h-[280px] bg-[#0a0a1a]">
                    <Workspace2D
                      :agents="previewAgents"
                      blackboard-content=""
                      :selected-agent-id="null"
                      :selected-hex="null"
                      :topology-nodes="previewTopoNodes"
                      :topology-edges="previewTopoEdges"
                      :selectable="true"
                      :selected-keys="saveSelectedKeys"
                      :selectable-types="['agent', 'corridor']"
                      @toggle-node="handleTopoToggle"
                    />
                  </div>
                </div>
              </div>

              <div class="flex justify-end gap-2 shrink-0">
                <button type="button" class="px-4 py-2 text-sm rounded-lg hover:bg-muted transition-colors" @click="showTemplateDialog = false">
                  {{ t('workspaceSettings.cancel') }}
                </button>
                <button
                  type="button"
                  class="px-4 py-2 text-sm rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                  :disabled="savingTemplate || !templateName.trim() || templatePreviewLoading || saveSelectedCount === 0"
                  @click="handleSaveAsTemplate"
                >
                  <Loader2 v-if="savingTemplate" class="w-4 h-4 animate-spin inline mr-1" />
                  {{ t('workspaceSettings.saveTemplateWithCount', { n: saveSelectedCount }) }}
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Agent Spec Detail Sub-dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="selectedSpec" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" @click.self="closeSpecDetail">
          <div class="bg-card rounded-xl shadow-2xl w-full max-w-sm border border-border max-h-[80vh] flex flex-col">
            <div class="flex items-center justify-between px-5 py-3 border-b border-border shrink-0">
              <h3 class="text-sm font-semibold">{{ (selectedSpec.display_name as string) || '—' }}</h3>
              <button type="button" class="p-1 rounded hover:bg-muted" @click="closeSpecDetail">
                <X class="w-4 h-4" />
              </button>
            </div>
            <div class="px-5 py-4 space-y-4 overflow-y-auto text-xs">
              <div class="space-y-1.5">
                <p class="font-medium text-muted-foreground">{{ t('workspaceSettings.geneList') }}</p>
                <ul v-if="specGeneSlugs(selectedSpec).length" class="space-y-0.5 text-foreground">
                  <li v-for="slug in specGeneSlugs(selectedSpec)" :key="slug" class="flex items-center gap-1.5">
                    <span class="w-1 h-1 rounded-full bg-primary shrink-0" />
                    {{ slug }}
                  </li>
                </ul>
                <p v-else class="text-muted-foreground">{{ t('workspaceSettings.noGenes') }}</p>
              </div>

              <div class="space-y-1.5">
                <p class="font-medium text-muted-foreground">{{ t('workspaceSettings.llmConfig') }}</p>
                <div v-if="specLlmProviders(selectedSpec).length" class="space-y-1">
                  <div v-for="p in specLlmProviders(selectedSpec)" :key="p.provider" class="text-foreground">
                    <span class="font-medium">{{ p.provider }}</span>
                    <span v-if="p.models.length" class="text-muted-foreground ml-1.5">{{ p.models.join(', ') }}</span>
                  </div>
                </div>
                <p v-else class="text-muted-foreground">{{ t('workspaceSettings.noLlmConfig') }}</p>
              </div>

              <div class="space-y-1.5">
                <p class="font-medium text-muted-foreground">{{ t('workspaceSettings.resourceConfig') }}</p>
                <div class="grid grid-cols-3 gap-x-4 gap-y-1 text-foreground">
                  <span>CPU: {{ (selectedSpec.resources as Record<string, string>)?.cpu_limit || '—' }}</span>
                  <span>Mem: {{ (selectedSpec.resources as Record<string, string>)?.mem_limit || '—' }}</span>
                  <span>{{ t('workspaceSettings.storageSizeLabel') }}: {{ (selectedSpec.resources as Record<string, string>)?.storage_size || '—' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- Add Member Dialog -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showAddDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="showAddDialog = false">
          <div class="bg-card rounded-xl shadow-2xl w-[420px] max-h-[80vh] flex flex-col border border-border">
            <div class="flex items-center justify-between px-5 py-4 border-b border-border">
              <h3 class="text-sm font-semibold">{{ t('workspaceSettings.addMemberTitle') }}</h3>
              <button class="p-1 rounded hover:bg-muted" @click="showAddDialog = false">
                <X class="w-4 h-4" />
              </button>
            </div>

            <!-- Preset + Permissions -->
            <div class="px-5 py-3 border-b border-border/50 space-y-3">
              <div class="flex items-center gap-2">
                <label class="text-xs text-muted-foreground shrink-0">{{ t('workspaceSettings.presetRole') }}</label>
                <CustomSelect
                  :model-value="addPreset"
                  :options="presetOptions"
                  size="xs"
                  trigger-class="flex-1"
                  @update:model-value="(v: string | null) => onPresetChange(v!)"
                />
              </div>
              <div class="grid grid-cols-2 gap-1.5">
                <label
                  v-for="perm in WORKSPACE_PERMISSIONS"
                  :key="perm"
                  class="flex items-center gap-1.5 text-xs cursor-pointer select-none"
                  :class="addIsAdmin ? 'opacity-50' : ''"
                >
                  <input
                    type="checkbox"
                    :checked="addPermissions.includes(perm)"
                    :disabled="addIsAdmin"
                    class="rounded border-border"
                    @change="onAddPermToggle(perm)"
                  />
                  {{ permLabel(perm) }}
                </label>
              </div>
            </div>

            <!-- Search -->
            <div class="px-5 py-3 border-b border-border/50">
              <div class="relative">
                <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <input
                  v-model="searchQuery"
                  :placeholder="t('workspaceSettings.searchPlaceholder')"
                  class="w-full pl-8 pr-3 py-1.5 text-sm rounded-lg bg-muted border border-border outline-none focus:ring-1 focus:ring-primary/50"
                  @input="onSearchInput"
                />
              </div>
            </div>

            <!-- Results -->
            <div class="flex-1 overflow-y-auto px-5 py-2 space-y-1 max-h-[300px]">
              <div v-if="searching" class="flex justify-center py-4">
                <Loader2 class="w-5 h-5 animate-spin text-muted-foreground" />
              </div>
              <div v-else-if="searchQuery && searchResults.length === 0" class="text-center text-xs text-muted-foreground py-4">
                {{ t('workspaceSettings.noResults') }}
              </div>
              <div
                v-for="u in searchResults"
                :key="u.user_id"
                class="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-muted transition-colors"
              >
                <div class="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center text-xs font-medium shrink-0">
                  {{ u.name?.[0] || '?' }}
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-sm font-medium truncate">{{ u.name }}</p>
                  <p class="text-xs text-muted-foreground truncate">{{ u.email }}</p>
                </div>
                <button
                  class="px-2.5 py-1 text-xs rounded bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
                  :disabled="addingUserId === u.user_id"
                  @click="handleAddMember(u.user_id)"
                >
                  <Loader2 v-if="addingUserId === u.user_id" class="w-3 h-3 animate-spin" />
                  <span v-else>{{ t('workspaceSettings.add') }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
