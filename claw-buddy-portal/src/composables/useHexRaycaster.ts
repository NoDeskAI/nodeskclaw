import { ref, onMounted, onUnmounted, type Ref, type ShallowRef } from 'vue'
import * as THREE from 'three'

export function useHexRaycaster(
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
  containerRef: Ref<HTMLElement | null>,
  options?: { meshFilter?: (obj: THREE.Object3D) => boolean },
) {
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  const hoveredId = ref<string | null>(null)
  const selectedId = ref<string | null>(null)

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

  function onPointerMove(e: MouseEvent) {
    const hits = cast(e)
    hoveredId.value = hits.length > 0 ? getHexId(hits[0].object) : null
  }

  function onClick(e: MouseEvent) {
    const hits = cast(e)
    const id = hits.length > 0 ? getHexId(hits[0].object) : null
    if (id) selectedId.value = id
  }

  onMounted(() => {
    const el = containerRef.value
    if (!el) return
    el.addEventListener('pointermove', onPointerMove)
    el.addEventListener('click', onClick)
  })

  onUnmounted(() => {
    const el = containerRef.value
    if (!el) return
    el.removeEventListener('pointermove', onPointerMove)
    el.removeEventListener('click', onClick)
  })

  return { hoveredId, selectedId }
}
