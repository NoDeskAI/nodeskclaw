import { onMounted, onUnmounted, shallowRef, type Ref } from 'vue'
import * as THREE from 'three'

export interface ThreeSceneState {
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  renderer: THREE.WebGLRenderer | null
  addToLoop: (fn: (delta: number) => void) => void
  removeFromLoop: (fn: (delta: number) => void) => void
  dispose: () => void
}

export function useThreeScene(
  containerRef: Ref<HTMLElement | null>,
  options?: { cameraPos?: [number, number, number]; fov?: number },
) {
  const scene = new THREE.Scene()
  const fov = options?.fov ?? 50
  const camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 1000)
  const cameraPos = options?.cameraPos ?? [0, 8, 10]
  camera.position.set(...cameraPos)
  camera.lookAt(0, 0, 0)

  const rendererRef = shallowRef<THREE.WebGLRenderer | null>(null)
  const clock = new THREE.Clock()
  let animationId = 0
  let disposed = false

  const loopCallbacks = new Set<(delta: number) => void>()

  function addToLoop(fn: (delta: number) => void) {
    loopCallbacks.add(fn)
  }
  function removeFromLoop(fn: (delta: number) => void) {
    loopCallbacks.delete(fn)
  }

  function loop() {
    if (disposed) return
    animationId = requestAnimationFrame(loop)
    const delta = clock.getDelta()
    for (const cb of loopCallbacks) cb(delta)
    rendererRef.value?.render(scene, camera)
  }

  function resize() {
    const el = containerRef.value
    if (!el || !rendererRef.value) return
    const w = el.clientWidth
    const h = el.clientHeight
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    rendererRef.value.setSize(w, h)
  }

  function init() {
    const el = containerRef.value
    if (!el) return

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setSize(el.clientWidth, el.clientHeight)
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.2
    el.appendChild(renderer.domElement)
    rendererRef.value = renderer

    camera.aspect = el.clientWidth / el.clientHeight
    camera.updateProjectionMatrix()

    window.addEventListener('resize', resize)
    loop()
  }

  function dispose() {
    disposed = true
    cancelAnimationFrame(animationId)
    window.removeEventListener('resize', resize)
    loopCallbacks.clear()

    if (rendererRef.value) {
      rendererRef.value.dispose()
      rendererRef.value.domElement.remove()
      rendererRef.value = null
    }

    scene.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry?.dispose()
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose())
        } else {
          obj.material?.dispose()
        }
      }
    })
    scene.clear()
  }

  onMounted(init)
  onUnmounted(dispose)

  return {
    scene,
    camera,
    renderer: rendererRef,
    addToLoop,
    removeFromLoop,
    dispose,
  } satisfies ThreeSceneState
}
