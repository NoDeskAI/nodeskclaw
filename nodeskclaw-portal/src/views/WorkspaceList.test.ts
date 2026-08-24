import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import WorkspaceList from './WorkspaceList.vue'
import { useClusterStore, type ClusterInfo } from '@/stores/cluster'
import { useWorkspaceStore } from '@/stores/workspace'

const routerPush = vi.fn()
const authStoreState = vi.hoisted(() => ({
  systemInfo: { edition: 'ee' },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: routerPush }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => authStoreState,
}))

vi.mock('@/stores/workspace', async () => {
  const { defineStore } = await import('pinia')
  return {
    useWorkspaceStore: defineStore('workspace', {
      state: () => ({
        workspaces: [],
        loading: false,
        activeTemplateDeploys: [],
      }),
      actions: {
        async fetchWorkspaces() {},
        async refreshActiveTemplateDeploys() {
          return []
        },
      },
    }),
  }
})

vi.mock('@/stores/cluster', async () => {
  const { defineStore } = await import('pinia')
  return {
    useClusterStore: defineStore('cluster', {
      state: () => ({
        clusters: [],
      }),
      actions: {
        async fetchClusters() {},
      },
    }),
  }
})

vi.mock('@/components/workspace/WorkspaceCard.vue', () => ({
  default: {
    template: '<div />',
  },
}))

vi.mock('@/components/workspace/DeployFromTemplateDialog.vue', () => ({
  default: {
    template: '<div />',
  },
}))

const tooltipStubs = {
  TooltipProvider: {
    template: '<div><slot /></div>',
  },
  Tooltip: {
    props: ['disabled'],
    template: '<div class="tooltip-stub" :data-disabled="disabled"><slot /></div>',
  },
  TooltipTrigger: {
    template: '<div><slot /></div>',
  },
  TooltipContent: {
    template: '<div data-testid="tooltip-content"><slot /></div>',
  },
  WorkspaceCard: true,
  DeployFromTemplateDialog: true,
}

async function mountWorkspaceList(cluster: ClusterInfo | null) {
  const pinia = createPinia()
  setActivePinia(pinia)

  const workspaceStore = useWorkspaceStore()
  vi.spyOn(workspaceStore, 'fetchWorkspaces').mockResolvedValue()
  vi.spyOn(workspaceStore, 'refreshActiveTemplateDeploys').mockResolvedValue([])

  const clusterStore = useClusterStore()
  clusterStore.clusters = cluster ? [cluster] : []
  vi.spyOn(clusterStore, 'fetchClusters').mockResolvedValue()

  const wrapper = mount(WorkspaceList, {
    global: {
      plugins: [pinia],
      stubs: tooltipStubs,
    },
  })
  await flushPromises()
  return wrapper
}

describe('WorkspaceList', () => {
  beforeEach(() => {
    routerPush.mockReset()
    authStoreState.systemInfo.edition = 'ee'
  })

  it('uses the Admin Console tooltip in EE when no cluster exists', async () => {
    const wrapper = await mountWorkspaceList(null)
    const headerButton = wrapper.get('[data-testid="create-workspace-header-trigger"] button')
    const emptyButton = wrapper.get('[data-testid="create-workspace-empty-trigger"] button')

    expect(headerButton.attributes('disabled')).toBeDefined()
    expect(emptyButton.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('[data-testid="tooltip-content"]')).toHaveLength(2)
    expect(wrapper.text()).toContain('workspaceList.createRequiresClusterEe')

    await headerButton.trigger('click')
    await emptyButton.trigger('click')
    expect(routerPush).not.toHaveBeenCalled()
  })

  it('uses the Organization Settings tooltip in CE when no cluster exists', async () => {
    authStoreState.systemInfo.edition = 'ce'
    const wrapper = await mountWorkspaceList(null)

    expect(wrapper.text()).toContain('workspaceList.createRequiresCluster')
    expect(wrapper.text()).not.toContain('workspaceList.createRequiresClusterEe')
  })

  it('enables both create entries when a cluster exists', async () => {
    const wrapper = await mountWorkspaceList({ id: 'cluster-1' } as ClusterInfo)
    const headerButton = wrapper.get('[data-testid="create-workspace-header-trigger"] button')
    const emptyButton = wrapper.get('[data-testid="create-workspace-empty-trigger"] button')

    expect(headerButton.attributes('disabled')).toBeUndefined()
    expect(emptyButton.attributes('disabled')).toBeUndefined()

    await headerButton.trigger('click')
    expect(routerPush).toHaveBeenCalledWith('/workspace/create')
  })
})
