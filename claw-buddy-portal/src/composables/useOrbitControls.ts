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

  const initialCameraPos = { x: camera.position.x, y: camera.position.y, z: camera.position.z }

  function update() {
    controls?.update()
  }

  function zoomIn(factor = 0.8) {
    if (!controls) return
    const dir = camera.position.clone().sub(controls.target)
    const newLen = Math.max(dir.length() * factor, controls.minDistance)
    camera.position.copy(controls.target).add(dir.normalize().multiplyScalar(newLen))
  }

  function zoomOut(factor = 1.25) {
    if (!controls) return
    const dir = camera.position.clone().sub(controls.target)
    const newLen = Math.min(dir.length() * factor, controls.maxDistance)
    camera.position.copy(controls.target).add(dir.normalize().multiplyScalar(newLen))
  }

  function resetView() {
    if (!controls) return
    camera.position.set(initialCameraPos.x, initialCameraPos.y, initialCameraPos.z)
    controls.target.set(0, 0, 0)
    controls.update()
  }

  onUnmounted(() => {
    stop()
    controls?.dispose()
    controls = null
  })

  return { update, zoomIn, zoomOut, resetView, get controls() { return controls } }
}
