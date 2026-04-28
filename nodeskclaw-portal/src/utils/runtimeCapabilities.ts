export interface RuntimeCapabilities {
  genes: boolean
  evolutionLog: boolean
  llmConfig: boolean
  dataRoot: string
}

const CAPS: Record<string, RuntimeCapabilities> = {
  openclaw: { genes: true, evolutionLog: true, llmConfig: true, dataRoot: '.openclaw' },
  nanobot: { genes: false, evolutionLog: false, llmConfig: false, dataRoot: '.nanobot' },
  hermes: { genes: false, evolutionLog: false, llmConfig: true, dataRoot: '.hermes' },
}

export function getRuntimeCaps(runtime: string): RuntimeCapabilities {
  return CAPS[runtime] ?? CAPS.openclaw
}
