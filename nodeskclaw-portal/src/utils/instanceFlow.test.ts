import { describe, expect, it } from 'vitest'

import {
  buildDefaultBackendStepNames,
  buildDefaultSpecPresets,
  buildEngineInfoMap,
  buildPortalDeploySteps,
  sanitizeDeployLogs,
} from './instanceFlow'

const messages: Record<string, string> = {
  'createInstance.specSmallLabel': 'Small',
  'createInstance.specSmallDesc': 'Light work',
  'createInstance.specMediumLabel': 'Medium',
  'createInstance.specMediumDesc': 'Standard work',
  'createInstance.specLargeLabel': 'Large',
  'createInstance.specLargeDesc': 'Heavy work',
  'instanceDetail.engineOpenclawName': 'General Engine',
  'instanceDetail.engineOpenclawDesc': 'Tool-heavy engine',
  'instanceDetail.engineNanobotName': 'Light Engine',
  'instanceDetail.engineNanobotDesc': 'Fast lightweight engine',
  'instanceDetail.engineHermesName': 'Hermes Runtime',
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
  it('builds localized default spec presets', () => {
    expect(buildDefaultSpecPresets(t)[0]).toMatchObject({
      key: 'small',
      label: 'Small',
      desc: 'Light work',
    })
  })

  it('builds localized engine info', () => {
    expect(buildEngineInfoMap(t).openclaw).toMatchObject({
      name: 'General Engine',
      description: 'Tool-heavy engine',
      tags: ['Default'],
    })
    expect(buildEngineInfoMap(t).hermes).toMatchObject({
      name: 'Hermes Runtime',
      description: 'Long-running agent engine',
      poweredBy: 'Hermes Agent',
      tags: [],
    })
  })

  it('builds localized deploy steps', () => {
    expect(buildPortalDeploySteps(t)).toEqual(['Preflight', 'Provision', 'Deploy', 'Ready'])
    expect(buildDefaultBackendStepNames(t)).toHaveLength(9)
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
