import { ref } from 'vue'

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2
}

function animateWithRAF(durationMs: number, tick: (progress: number) => void): Promise<void> {
  return new Promise((resolve) => {
    const start = performance.now()
    function frame(now: number) {
      const elapsed = now - start
      const raw = Math.min(elapsed / durationMs, 1)
      tick(easeInOutCubic(raw))
      if (raw < 1) {
        requestAnimationFrame(frame)
      } else {
        resolve()
      }
    }
    requestAnimationFrame(frame)
  })
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

export type ViewMode = '3d' | '2d'

export function useViewTransition() {
  const isTransitioning = ref(false)
  const activeMode = ref<ViewMode>(
    (localStorage.getItem('clawbuddy_view_mode') as ViewMode) || '3d',
  )

  function persistMode(mode: ViewMode) {
    localStorage.setItem('clawbuddy_view_mode', mode)
    activeMode.value = mode
  }

  async function transitionTo2D(
    threeCanvas: HTMLCanvasElement | null,
    svgEl: HTMLElement | null,
    onMidpoint?: () => void,
  ) {
    if (!threeCanvas || !svgEl) {
      persistMode('2d')
      return
    }
    isTransitioning.value = true

    threeCanvas.animate(
      [{ opacity: '1' }, { opacity: '0' }],
      { duration: 400, fill: 'forwards', easing: 'ease-in-out' },
    )
    await sleep(200)
    onMidpoint?.()
    svgEl.animate(
      [{ opacity: '0' }, { opacity: '1' }],
      { duration: 400, fill: 'forwards', easing: 'ease-in-out' },
    )
    await sleep(400)

    persistMode('2d')
    isTransitioning.value = false
  }

  async function transitionTo3D(
    threeCanvas: HTMLCanvasElement | null,
    svgEl: HTMLElement | null,
    onMidpoint?: () => void,
  ) {
    if (!threeCanvas || !svgEl) {
      persistMode('3d')
      return
    }
    isTransitioning.value = true

    svgEl.animate(
      [{ opacity: '1' }, { opacity: '0' }],
      { duration: 400, fill: 'forwards', easing: 'ease-in-out' },
    )
    await sleep(200)
    onMidpoint?.()
    threeCanvas.animate(
      [{ opacity: '0' }, { opacity: '1' }],
      { duration: 400, fill: 'forwards', easing: 'ease-in-out' },
    )
    await sleep(400)

    persistMode('3d')
    isTransitioning.value = false
  }

  return { isTransitioning, activeMode, transitionTo2D, transitionTo3D }
}
