import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import { zoom, zoomIdentity, type ZoomBehavior } from 'd3-zoom'
import { select } from 'd3-selection'

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

  const transformStr = ref('translate(0,0) scale(1)')

  function init() {
    const svg = svgRef.value
    if (!svg) return

    zoomBehavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([options?.minZoom ?? 0.3, options?.maxZoom ?? 3])
      .on('zoom', (event) => {
        const t = event.transform
        transform.value = { x: t.x, y: t.y, k: t.k }
        transformStr.value = `translate(${t.x},${t.y}) scale(${t.k})`
      })

    select(svg).call(zoomBehavior)
  }

  function zoomIn(factor = 1.3) {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
    select(svg).transition().duration(200).call(zoomBehavior.scaleBy, factor)
  }

  function zoomOut(factor = 1.3) {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
    select(svg).transition().duration(200).call(zoomBehavior.scaleBy, 1 / factor)
  }

  function resetView() {
    const svg = svgRef.value
    if (!svg || !zoomBehavior) return
    select(svg).transition().duration(300).call(zoomBehavior.transform, zoomIdentity)
  }

  onMounted(init)
  onUnmounted(() => {
    if (svgRef.value) {
      select(svgRef.value).on('.zoom', null)
    }
  })

  return { transform, transformStr, zoomIn, zoomOut, resetView }
}
