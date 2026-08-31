export interface SpecPreset {
  key: string
  label: string
  desc: string
  cpu: number
  memory: number
  storage: number
  cpu_request: string
  cpu_limit: string
  mem_request: string
  mem_limit: string
  quota_cpu: string
  quota_mem: string
}

export interface EngineInfo {
  name: string
  description: string
  poweredBy: string
  tags: string[]
}

export type Translator = (key: string, params?: Record<string, unknown>) => string

export const INSTANCE_STORAGE_ANCHORS = [20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200] as const

export interface StorageClassSelection {
  name: string
  enabled: boolean
}

export function storageValueToIndex(value: number): number {
  const index = INSTANCE_STORAGE_ANCHORS.indexOf(value as typeof INSTANCE_STORAGE_ANCHORS[number])
  return index >= 0 ? index : 0
}

export function storageIndexToValue(index: number): number {
  return INSTANCE_STORAGE_ANCHORS[index] ?? INSTANCE_STORAGE_ANCHORS[0]
}

export function hasUsableStorageClass(
  storageClasses: StorageClassSelection[],
  selectedStorageClass: string | null,
): boolean {
  return Boolean(
    selectedStorageClass
    && storageClasses.some(storageClass => storageClass.enabled && storageClass.name === selectedStorageClass),
  )
}

export const K8S_DEPLOY_BACKEND_STEP_NAMES = [
  '预检',
  '创建命名空间',
  '创建 ConfigMap',
  '创建 PVC',
  '创建 Deployment',
  '创建 Service',
  '创建 Ingress（自动路由）',
  '配置网络策略',
  '等待 Deployment 就绪',
]

const K8S_DEPLOY_BACKEND_STEP_COUNT = K8S_DEPLOY_BACKEND_STEP_NAMES.length

export interface DeployProgressStepMapping {
  stepNames: string[]
  directMapping: boolean
}

export function buildDefaultSpecPresets(t: Translator): SpecPreset[] {
  return [
    { key: 'small', label: t('createInstance.specSmallLabel'), desc: t('createInstance.specSmallDesc'), cpu: 2, memory: 4, storage: 20, cpu_request: '1000m', cpu_limit: '2000m', mem_request: '2Gi', mem_limit: '4Gi', quota_cpu: '2', quota_mem: '4Gi' },
    { key: 'medium', label: t('createInstance.specMediumLabel'), desc: t('createInstance.specMediumDesc'), cpu: 4, memory: 8, storage: 40, cpu_request: '2000m', cpu_limit: '4000m', mem_request: '4Gi', mem_limit: '8Gi', quota_cpu: '4', quota_mem: '8Gi' },
    { key: 'large', label: t('createInstance.specLargeLabel'), desc: t('createInstance.specLargeDesc'), cpu: 8, memory: 16, storage: 80, cpu_request: '4000m', cpu_limit: '8000m', mem_request: '8Gi', mem_limit: '16Gi', quota_cpu: '8', quota_mem: '16Gi' },
  ]
}

export function buildEngineInfoMap(t: Translator): Record<string, EngineInfo> {
  return {
    openclaw: {
      name: t('instanceDetail.engineOpenclawName'),
      description: t('instanceDetail.engineOpenclawDesc'),
      poweredBy: 'OpenClaw',
      tags: [t('engine.defaultTag')],
    },
    hermes: {
      name: t('instanceDetail.engineHermesName'),
      description: t('instanceDetail.engineHermesDesc'),
      poweredBy: 'Hermes Agent',
      tags: [],
    },
  }
}

export function getEngineInfo(engineMap: Record<string, EngineInfo>, runtime: string): EngineInfo {
  return engineMap[runtime] ?? { name: runtime, description: '', poweredBy: runtime, tags: [] }
}

export function buildPortalDeploySteps(t: Translator): string[] {
  return [
    t('deployProgress.stepPreflight'),
    t('deployProgress.stepProvision'),
    t('deployProgress.stepDeploy'),
    t('deployProgress.stepReady'),
  ]
}

export function buildDefaultBackendStepNames(t: Translator): string[] {
  return [
    t('deployProgress.backendPreflight'),
    t('deployProgress.backendNamespace'),
    t('deployProgress.backendConfigMap'),
    t('deployProgress.backendPvc'),
    t('deployProgress.backendDeployment'),
    t('deployProgress.backendService'),
    t('deployProgress.backendIngress'),
    t('deployProgress.backendNetworkPolicy'),
    t('deployProgress.backendWaitReady'),
  ]
}

function startsWithStepNames(stepNames: string[], expected: string[]): boolean {
  if (stepNames.length < expected.length) return false
  return expected.every((name, index) => stepNames[index] === name)
}

export function isK8sDeployBackendStepNames(stepNames: string[], t: Translator): boolean {
  return (
    startsWithStepNames(stepNames, K8S_DEPLOY_BACKEND_STEP_NAMES)
    || startsWithStepNames(stepNames, buildDefaultBackendStepNames(t))
  )
}

export function buildDeployProgressStepMapping(stepNames: string[], t: Translator): DeployProgressStepMapping {
  if (!isK8sDeployBackendStepNames(stepNames, t)) {
    return {
      stepNames: [...stepNames],
      directMapping: true,
    }
  }

  const portalStepNames = buildPortalDeploySteps(t)
  for (const name of stepNames.slice(K8S_DEPLOY_BACKEND_STEP_COUNT)) {
    portalStepNames.push(name)
  }

  return {
    stepNames: portalStepNames,
    directMapping: false,
  }
}

export function backendStepToPortalIndex(backendStep: number, directMapping: boolean): number {
  if (directMapping) return backendStep - 1
  if (backendStep <= 1) return 0
  if (backendStep <= 4) return 1
  if (backendStep <= 8) return 2
  if (backendStep === K8S_DEPLOY_BACKEND_STEP_COUNT) return 3
  return 3 + (backendStep - K8S_DEPLOY_BACKEND_STEP_COUNT)
}

export function sanitizeDeployLogs(lines: string[], t: Translator): string[] {
  const result: string[] = []
  for (const line of lines) {
    if (line.startsWith('开始等待') || line === '尚未发现 Pod（调度中）') {
      result.push(t('deployProgress.logWaitingStart'))
      continue
    }
    if (/^已等待\s/.test(line)) {
      result.push(line)
      continue
    }
    if (line.includes('phase=')) {
      const match = line.match(/phase=(\w+)/)
      const phase = match?.[1] || 'Unknown'
      const friendly = phase === 'Running'
        ? t('deployProgress.logPodRunning')
        : phase === 'Pending'
          ? t('deployProgress.logPodPending')
          : t('deployProgress.logPodAbnormal', { phase })
      if (!result.includes(friendly)) result.push(friendly)
      continue
    }
    if (line.startsWith('PVC ')) {
      const friendly = line.includes('Bound')
        ? t('deployProgress.logStorageReady')
        : t('deployProgress.logStoragePreparing')
      if (!result.includes(friendly)) result.push(friendly)
      continue
    }
    if (line === '无法获取 Pod 状态') {
      result.push(t('deployProgress.logStatusLoading'))
      continue
    }
  }
  return result
}
