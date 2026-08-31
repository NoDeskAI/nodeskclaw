import { describe, expect, it } from 'vitest'

import {
  K8S_DEPLOY_BACKEND_STEP_NAMES,
  hasUsableStorageClass,
  storageIndexToValue,
  storageValueToIndex,
  backendStepToPortalIndex,
  buildDeployProgressStepMapping,
  buildDefaultBackendStepNames,
  buildDefaultSpecPresets,
  buildEngineInfoMap,
  buildPortalDeploySteps,
  sanitizeDeployLogs,
} from './instanceFlow'

const REBUILD_STEPS = [
  '检查实例状态',
  '重建命名空间',
  '重建 ConfigMap',
  '重建 PVC',
  '重建 Deployment',
  '重建 Service',
  '重建 Ingress',
  '配置网络策略',
  '等待 Deployment 就绪',
]

const messages: Record<string, string> = {
  'createInstance.specSmallLabel': 'Small',
  'createInstance.specSmallDesc': 'Light work',
  'createInstance.specMediumLabel': 'Medium',
  'createInstance.specMediumDesc': 'Standard work',
  'createInstance.specLargeLabel': 'Large',
  'createInstance.specLargeDesc': 'Heavy work',
  'instanceDetail.engineOpenclawName': 'General Employee Engine',
  'instanceDetail.engineOpenclawDesc': 'Tool-heavy engine',
  'instanceDetail.engineHermesName': 'Self-Evolving Employee Engine',
  'instanceDetail.engineHermesDesc': 'Long-running agent engine',
  'engine.defaultTag': 'Default',
  'deployProgress.stepPreflight': 'Preflight',
  'deployProgress.stepProvision': 'Provision',
  'deployProgress.stepDeploy': 'Deploy',
  'deployProgress.stepReady': 'Ready',
  'deployProgress.backendPreflight': 'Check',
  'deployProgress.backendNamespace': 'Namespace',
  'deployProgress.backendConfigMap': 'ConfigMap',
  'deployProgress.backendPvc': 'PVC',
  'deployProgress.backendDeployment': 'Deployment',
  'deployProgress.backendService': 'Service',
  'deployProgress.backendIngress': 'Ingress',
  'deployProgress.backendNetworkPolicy': 'NetworkPolicy',
  'deployProgress.backendWaitReady': 'Wait Ready',
  'deployProgress.logWaitingStart': 'Waiting for AI employee startup...',
  'deployProgress.logPodRunning': 'Pod running',
  'deployProgress.logPodPending': 'Pod pending',
  'deployProgress.logPodAbnormal': 'Pod abnormal ({phase})',
  'deployProgress.logStorageReady': 'Storage ready',
  'deployProgress.logStoragePreparing': 'Storage preparing',
  'deployProgress.logStatusLoading': 'Loading AI employee status...',
}

function t(key: string, params?: Record<string, unknown>) {
  let text = messages[key] ?? key
  if (params) {
    for (const [name, value] of Object.entries(params)) {
      text = text.replace(`{${name}}`, String(value))
    }
  }
  return text
}

describe('instanceFlow', () => {
  it('keeps storage slider indexes aligned with displayed values', () => {
    expect(storageValueToIndex(20)).toBe(0)
    expect(storageValueToIndex(100)).toBe(8)
    expect(storageValueToIndex(200)).toBe(18)
    expect(storageIndexToValue(0)).toBe(20)
    expect(storageIndexToValue(8)).toBe(100)
    expect(storageIndexToValue(18)).toBe(200)
  })

  it('requires the selected StorageClass to be enabled', () => {
    const storageClasses = [
      { name: 'disabled-storage', enabled: false },
      { name: 'enabled-storage', enabled: true },
    ]

    expect(hasUsableStorageClass([], null)).toBe(false)
    expect(hasUsableStorageClass(storageClasses, null)).toBe(false)
    expect(hasUsableStorageClass(storageClasses, 'disabled-storage')).toBe(false)
    expect(hasUsableStorageClass(storageClasses, 'enabled-storage')).toBe(true)
  })

  it('builds localized default spec presets', () => {
    expect(buildDefaultSpecPresets(t)[0]).toMatchObject({
      key: 'small',
      label: 'Small',
      desc: 'Light work',
    })
  })

  it('builds localized engine info', () => {
    expect(buildEngineInfoMap(t).openclaw).toMatchObject({
      name: 'General Employee Engine',
      description: 'Tool-heavy engine',
      tags: ['Default'],
    })
    expect(buildEngineInfoMap(t).hermes).toMatchObject({
      name: 'Self-Evolving Employee Engine',
      description: 'Long-running agent engine',
      poweredBy: 'Hermes Agent',
      tags: [],
    })
  })

  it('builds localized deploy steps', () => {
    expect(buildPortalDeploySteps(t)).toEqual(['Preflight', 'Provision', 'Deploy', 'Ready'])
    expect(buildDefaultBackendStepNames(t)).toHaveLength(9)
  })

  it('maps standard k8s deploy backend steps to portal stages', () => {
    const mapping = buildDeployProgressStepMapping(K8S_DEPLOY_BACKEND_STEP_NAMES, t)

    expect(mapping.directMapping).toBe(false)
    expect(mapping.stepNames).toEqual(['Preflight', 'Provision', 'Deploy', 'Ready'])
    expect(backendStepToPortalIndex(9, mapping.directMapping)).toBe(3)
  })

  it('appends post-ready steps to standard k8s deploy stages', () => {
    const mapping = buildDeployProgressStepMapping([...K8S_DEPLOY_BACKEND_STEP_NAMES, '同步 LLM 配置'], t)

    expect(mapping.directMapping).toBe(false)
    expect(mapping.stepNames).toEqual(['Preflight', 'Provision', 'Deploy', 'Ready', '同步 LLM 配置'])
    expect(backendStepToPortalIndex(10, mapping.directMapping)).toBe(4)
  })

  it('keeps rebuild and restore steps as direct backend mapping', () => {
    const mapping = buildDeployProgressStepMapping(REBUILD_STEPS, t)

    expect(mapping.directMapping).toBe(true)
    expect(mapping.stepNames).toEqual(REBUILD_STEPS)
    expect(backendStepToPortalIndex(9, mapping.directMapping)).toBe(8)
  })

  it('maps localized fallback deploy steps to portal stages', () => {
    const mapping = buildDeployProgressStepMapping(buildDefaultBackendStepNames(t), t)

    expect(mapping.directMapping).toBe(false)
    expect(mapping.stepNames).toEqual(['Preflight', 'Provision', 'Deploy', 'Ready'])
  })

  it('sanitizes deployment logs with localized labels', () => {
    expect(sanitizeDeployLogs(['开始等待 Pod', 'phase=Running', 'PVC data Bound', '无法获取 Pod 状态'], t)).toEqual([
      'Waiting for AI employee startup...',
      'Pod running',
      'Storage ready',
      'Loading AI employee status...',
    ])
  })
})
