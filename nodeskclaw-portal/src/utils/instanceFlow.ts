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

type Translator = (key: string, params?: Record<string, unknown>) => string

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
    nanobot: {
      name: t('instanceDetail.engineNanobotName'),
      description: t('instanceDetail.engineNanobotDesc'),
      poweredBy: 'Nanobot',
      tags: [],
    },
    hermes: {
      name: t('instanceDetail.engineHermesName'),
      description: t('instanceDetail.engineHermesDesc'),
      poweredBy: 'Hermes Agent',
      tags: [],
    },
  }
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
