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
    controls.enablePan = true
    controls.screenSpacePanning = true
    controls.touches = {
      ONE: THREE.TOUCH.ROTATE,
      TWO: THREE.TOUCH.DOLLY_PAN,
    }
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

  function panBy(dx: number, dy: number) {
    if (!controls) return
    const amount = 1

    const forward = new THREE.Vector3()
    camera.getWorldDirection(forward)
    forward.y = 0
    forward.normalize()

    const right = new THREE.Vector3()
      .crossVectors(forward, new THREE.Vector3(0, 1, 0))
      .normalize()

    const offset = new THREE.Vector3()
      .addScaledVector(right, dx * amount)
      .addScaledVector(forward, -dy * amount)

    controls.target.add(offset)
    camera.position.add(offset)
  }

  onUnmounted(() => {
    stop()
    controls?.dispose()
    controls = null
  })

  return { update, zoomIn, zoomOut, resetView, panBy, get controls() { return controls } }
}
