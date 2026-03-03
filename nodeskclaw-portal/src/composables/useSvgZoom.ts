import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import { zoom, zoomIdentity, type ZoomBehavior } from 'd3-zoom'
import { select } from 'd3-selection'
import 'd3-transition'

export interface SvgTransform {
  x: number
  y: number
  k: number
}

export function useSvgZoom(
  svgRef: Ref<SVGSVGElement | null>,
  options?: { minZoom?: number; maxZoom?: number },
) {
  const transform = ref<SvgTransform>({ x: 0, y: 0, k: 1 })
  let zoomBehavior: ZoomBehavior<SVGSVGElement, unknown> | null = null
  const abortController = new AbortController()

  const transformStr = ref('translate(0,0) scale(1)')

  function init() {
    const svg = svgRef.value
    if (!svg) return

    zoomBehavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([options?.minZoom ?? 0.3, options?.maxZoom ?? 3])
      .filter((event) => event.type !== 'dblclick' && event.button !== 2)
      .wheelDelta((event) =>
        -event.deltaY * (event.deltaMode === 1 ? 0.05 : event.deltaMode ? 1 : 0.002),
      )
      .on('zoom', (event) => {
        const t = event.transform
        transform.value = { x: t.x, y: t.y, k: t.k }
        transformStr.value = `translate(${t.x},${t.y}) scale(${t.k})`
      })

    select(svg).call(zoomBehavior)

    let rightDragging = false
    let lastX = 0
    let lastY = 0
    const signal = abortController.signal

    svg.addEventListener('pointerdown', (e) => {
      if (e.button !== 2) return
      rightDragging = true
      lastX = e.clientX
      lastY = e.clientY
      svg.setPointerCapture(e.pointerId)
    }, { signal })

    svg.addEventListener('pointermove', (e) => {
      if (!rightDragging || !zoomBehavior) return
      const dx = e.clientX - lastX
      const dy = e.clientY - lastY
      lastX = e.clientX
      lastY = e.clientY
      select(svg).call(zoomBehavior.translateBy, dx * 0.8, dy * 0.8)
    }, { signal })

    svg.addEventListener('pointerup', (e) => {
      if (e.button !== 2) return
      rightDragging = false
    }, { signal })

    svg.addEventListener('lostpointercapture', () => {
      rightDragging = false
    }, { signal })
  }

  function zoomIn(factor = 1.3) {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
  select(svg).call(zoomBehavior.scaleBy, factor)
  }

  function zoomOut(factor = 1.3) {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
  select(svg).call(zoomBehavior.scaleBy, 1 / factor)
  }

  function resetView() {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
  select(svg).call(zoomBehavior.transform, zoomIdentity)
  }

  function panBy(dx: number, dy: number) {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
  select(svg).call(zoomBehavior.translateBy, -dx * 80, -dy * 80)
  }

  function focusOnPosition(svgX: number, svgY: number) {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
    select(svg).transition().duration(600).call(zoomBehavior.translateTo, svgX, svgY)
  }

  onMounted(init)
  onUnmounted(() => {
    abortController.abort()
    if (svgRef.value) {
      select(svgRef.value).on('.zoom', null)
    }
  })

  return { transform, transformStr, zoomIn, zoomOut, resetView, panBy, focusOnPosition }
}
