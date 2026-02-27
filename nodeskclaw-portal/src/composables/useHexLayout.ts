import { computed, type Ref } from 'vue'

export const HEX_SIZE = 1.2
const SQRT3 = Math.sqrt(3)

export interface HexCoord {
  q: number
  r: number
}

export interface PixelCoord {
  x: number
  y: number
}

export function axialToWorld(q: number, r: number): PixelCoord {
  return {
    x: HEX_SIZE * (SQRT3 * q + (SQRT3 / 2) * r),
    y: HEX_SIZE * (1.5 * r),
  }
}

export function hexVertices(cx: number, cy: number, size: number): [number, number][] {
  return Array.from({ length: 6 }, (_, i) => {
    const angle = (Math.PI / 180) * (60 * i - 30)
    return [cx + size * Math.cos(angle), cy + size * Math.sin(angle)] as [number, number]
  })
}

export function hexPolygonPoints(cx: number, cy: number, size: number): string {
  return hexVertices(cx, cy, size).map(([x, y]) => `${x},${y}`).join(' ')
}

export function spiralLayout(count: number): HexCoord[] {
  const positions: HexCoord[] = []
  if (count === 0) return positions

  let q = 1, r = 0, ring = 1
  const directions: [number, number][] = [[0, -1], [-1, 0], [-1, 1], [0, 1], [1, 0], [1, -1]]

  while (positions.length < count) {
    for (const [dq, dr] of directions) {
      for (let step = 0; step < ring && positions.length < count; step++) {
        positions.push({ q, r })
        q += dq
        r += dr
      }
    }
    ring++
    q++
  }
  return positions
}

export function useHexPositions(agentCount: Ref<number>) {
  const positions = computed(() => spiralLayout(agentCount.value))
  const worldPositions = computed(() =>
    positions.value.map(({ q, r }) => axialToWorld(q, r)),
  )
  return { positions, worldPositions }
}
