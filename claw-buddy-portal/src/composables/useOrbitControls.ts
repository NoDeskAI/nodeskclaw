import { onUnmounted, watch, type ShallowRef } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

export function useOrbitControls(
  camera: THREE.PerspectiveCamera,
  rendererRef: ShallowRef<THREE.WebGLRenderer | null>,
  options?: {
    enableDamping?: boolean
    dampingFactor?: number
    minDistance?: number
    maxDistance?: number
    maxPolarAngle?: number
  },
) {
  let controls: OrbitControls | null = null

  function createControls(renderer: THREE.WebGLRenderer) {
    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = options?.enableDamping ?? true
    controls.dampingFactor = options?.dampingFactor ?? 0.08
    controls.minDistance = options?.minDistance ?? 4
    controls.maxDistance = options?.maxDistance ?? 30
    controls.maxPolarAngle = options?.maxPolarAngle ?? Math.PI / 2.2
    controls.target.set(0, 0, 0)
  }

  const stop = watch(rendererRef, (renderer) => {
    if (renderer && !controls) createControls(renderer)
  }, { immediate: true })

  function update() {
    controls?.update()
  }

  onUnmounted(() => {
    stop()
    controls?.dispose()
    controls = null
  })

  return { update, get controls() { return controls } }
}
