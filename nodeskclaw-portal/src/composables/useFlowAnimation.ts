import { ref } from 'vue'
import type { HexPath } from './useTopologyBFS'
import { axialToWorld } from './useHexLayout'

const MAX_ACTIVE = 10
const ANIM_DURATION_MS = 700

export interface FlowParticle {
  id: string
  points: { x: number; y: number }[]
  progress: number
  color: string
  startTime: number
}

export interface HexPulse {
  key: string
  startTime: number
}

export function useFlowAnimation2D(scale: number) {
  const particles = ref<FlowParticle[]>([])
  const pulses = ref<HexPulse[]>([])
  const activeKeys = new Set<string>()
  let animFrameId = 0

  function triggerFlow(path: HexPath[], color: string = '#a78bfa') {
    if (path.length < 2) return
    const flowKey = path.map(p => `${p.q},${p.r}`).join('>')
    if (activeKeys.has(flowKey)) return
    if (particles.value.length >= MAX_ACTIVE) return

    activeKeys.add(flowKey)
    const points = path.map(p => {
      const w = axialToWorld(p.q, p.r)
      return { x: w.x * scale, y: w.y * scale }
    })

    const particle: FlowParticle = {
      id: `flow-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      points,
      progress: 0,
      color,
      startTime: performance.now(),
    }
    particles.value.push(particle)

    if (!animFrameId) startLoop()

    const targetHex = path[path.length - 1]
    setTimeout(() => {
      pulses.value.push({
        key: `${targetHex.q},${targetHex.r}`,
        startTime: performance.now(),
      })
      setTimeout(() => {
        pulses.value = pulses.value.filter(p => p.key !== `${targetHex.q},${targetHex.r}`)
      }, 500)
    }, ANIM_DURATION_MS)
  }

  function startLoop() {
    function tick() {
      const now = performance.now()
      let hasActive = false

      for (const p of particles.value) {
        p.progress = Math.min(1, (now - p.startTime) / ANIM_DURATION_MS)
        if (p.progress < 1) hasActive = true
      }

      const expired = particles.value.filter(p => p.progress >= 1)
      if (expired.length > 0) {
        particles.value = particles.value.filter(p => p.progress < 1)
        for (const p of expired) {
          const flowKey = p.points.map(pt => `${pt.x},${pt.y}`).join('>')
          activeKeys.delete(flowKey)
        }
      }

      if (hasActive || particles.value.length > 0) {
        animFrameId = requestAnimationFrame(tick)
      } else {
        animFrameId = 0
      }
    }
    animFrameId = requestAnimationFrame(tick)
  }

  function getParticlePosition(particle: FlowParticle): { x: number; y: number } {
    const { points, progress } = particle
    if (points.length < 2) return points[0]
    const totalSegments = points.length - 1
    const segProgress = progress * totalSegments
    const segIndex = Math.min(Math.floor(segProgress), totalSegments - 1)
    const t = segProgress - segIndex
    const a = points[segIndex]
    const b = points[segIndex + 1]
    return {
      x: a.x + (b.x - a.x) * t,
      y: a.y + (b.y - a.y) * t,
    }
  }

  function dispose() {
    if (animFrameId) cancelAnimationFrame(animFrameId)
    animFrameId = 0
    particles.value = []
    pulses.value = []
    activeKeys.clear()
  }

  return { particles, pulses, triggerFlow, getParticlePosition, dispose }
}
