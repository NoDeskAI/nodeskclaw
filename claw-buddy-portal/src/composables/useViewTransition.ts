import { ref, nextTick } from 'vue'

export type ViewMode = '3d' | '2d'

export function useViewTransition() {
  const isTransitioning = ref(false)
  const activeMode = ref<ViewMode>(
    (localStorage.getItem('clawbuddy_view_mode') as ViewMode) || '3d',
  )

  let currentAnimations: Animation[] = []

  function persistMode(mode: ViewMode) {
    localStorage.setItem('clawbuddy_view_mode', mode)
    activeMode.value = mode
  }

  function cancelRunning() {
    for (const a of currentAnimations) a.cancel()
    currentAnimations = []
  }

  async function crossFade(outEl: HTMLElement, inEl: HTMLElement, targetMode: ViewMode) {
    if (isTransitioning.value) return
    isTransitioning.value = true
    cancelRunning()

    await nextTick()
    await new Promise<void>((r) => requestAnimationFrame(() => r()))

    const duration = 350

    const fadeOut = outEl.animate(
      [{ opacity: 1 }, { opacity: 0 }],
      { duration, easing: 'ease-in-out', fill: 'forwards' },
    )
    const fadeIn = inEl.animate(
      [{ opacity: 0 }, { opacity: 1 }],
      { duration, easing: 'ease-in-out', fill: 'forwards' },
    )
    currentAnimations = [fadeOut, fadeIn]

    await fadeOut.finished.catch(() => {})

    cancelRunning()
    persistMode(targetMode)
    isTransitioning.value = false
  }

  function transitionTo2D(threeEl: HTMLElement | null, svgEl: HTMLElement | null) {
    if (!threeEl || !svgEl) { persistMode('2d'); return }
    return crossFade(threeEl, svgEl, '2d')
  }

  function transitionTo3D(threeEl: HTMLElement | null, svgEl: HTMLElement | null) {
    if (!threeEl || !svgEl) { persistMode('3d'); return }
    return crossFade(svgEl, threeEl, '3d')
  }

  return { isTransitioning, activeMode, transitionTo2D, transitionTo3D }
}
