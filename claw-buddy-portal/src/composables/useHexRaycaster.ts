import { ref, shallowRef, triggerRef, onMounted, onUnmounted, type Ref } from 'vue'
import * as THREE from 'three'

const DRAG_THRESHOLD = 5

export function useHexRaycaster(
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
  containerRef: Ref<HTMLElement | null>,
  options?: { meshFilter?: (obj: THREE.Object3D) => boolean },
) {
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  const hoveredId = ref<string | null>(null)
  const selectedId = shallowRef<string | null>(null)
  const dblclickId = shallowRef<string | null>(null)

  let downX = 0
  let downY = 0

  function getHexId(obj: THREE.Object3D): string | null {
    let current: THREE.Object3D | null = obj
    while (current) {
      if (current.userData?.hexId) return current.userData.hexId as string
      current = current.parent
    }
    return null
  }

  function cast(e: MouseEvent): THREE.Intersection[] {
    const el = containerRef.value
    if (!el) return []
    const rect = el.getBoundingClientRect()
    pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointer, camera)

    const targets = options?.meshFilter
      ? scene.children.filter(options.meshFilter)
      : scene.children
    return raycaster.intersectObjects(targets, true)
  }

  const _proj = new THREE.Vector3()

  /**
   * When a ray hits multiple hex meshes (overlap zone due to cylinder side
   * faces at oblique camera angles), pick the hex whose ground-plane center
   * projects closest to the cursor in screen space (NDC).
   */
  function pickBestHexId(hits: THREE.Intersection[]): string | null {
    if (hits.length === 0) return null

    const seen = new Set<string>()
    const candidates: { hexId: string; sx: number; sy: number }[] = []

    for (const hit of hits) {
      const hexId = getHexId(hit.object)
      if (!hexId || seen.has(hexId)) continue
      seen.add(hexId)

      let obj: THREE.Object3D | null = hit.object
      while (obj?.parent && obj.parent !== scene) obj = obj.parent
      if (!obj) continue

      _proj.set(obj.position.x, 0, obj.position.z)
      _proj.project(camera)
      candidates.push({ hexId, sx: _proj.x, sy: _proj.y })
    }

    if (candidates.length <= 1) return candidates[0]?.hexId ?? null

    let bestId: string | null = null
    let bestDist = Infinity
    for (const c of candidates) {
      const dx = c.sx - pointer.x
      const dy = c.sy - pointer.y
      const dist = dx * dx + dy * dy
      if (dist < bestDist) {
        bestDist = dist
        bestId = c.hexId
      }
    }
    return bestId
  }

  function onPointerMove(e: MouseEvent) {
    const hits = cast(e)
    hoveredId.value = pickBestHexId(hits)
  }

  function onPointerDown(e: MouseEvent) {
    downX = e.clientX
    downY = e.clientY
  }

  function onClick(e: MouseEvent) {
    const dx = e.clientX - downX
    const dy = e.clientY - downY
    if (dx * dx + dy * dy > DRAG_THRESHOLD * DRAG_THRESHOLD) return

    const hits = cast(e)
    const id = pickBestHexId(hits)
    if (id) {
      selectedId.value = id
      triggerRef(selectedId)
    }
  }

  function onDblClick(e: MouseEvent) {
    const hits = cast(e)
    const id = pickBestHexId(hits)
    if (id) {
      dblclickId.value = id
      triggerRef(dblclickId)
    }
  }

  onMounted(() => {
    const el = containerRef.value
    if (!el) return
    el.addEventListener('pointermove', onPointerMove)
    el.addEventListener('pointerdown', onPointerDown)
    el.addEventListener('click', onClick)
    el.addEventListener('dblclick', onDblClick)
  })

  onUnmounted(() => {
    const el = containerRef.value
    if (!el) return
    el.removeEventListener('pointermove', onPointerMove)
    el.removeEventListener('pointerdown', onPointerDown)
    el.removeEventListener('click', onClick)
    el.removeEventListener('dblclick', onDblClick)
  })

  return { hoveredId, selectedId, dblclickId }
}
