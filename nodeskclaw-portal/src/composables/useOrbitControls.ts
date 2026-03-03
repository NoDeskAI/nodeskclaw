import { onUnmounted, watch, type ShallowRef } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

const LERP_FACTOR = 0.12
const CONVERGE_THRESHOLD = 0.01

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
  const abortController = new AbortController()

  let _animCamPos: THREE.Vector3 | null = null
  let _animTarget: THREE.Vector3 | null = null

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
    controls.mouseButtons = {
      LEFT: THREE.MOUSE.ROTATE,
      MIDDLE: THREE.MOUSE.DOLLY,
    }
    controls.touches = {
      ONE: THREE.TOUCH.ROTATE,
      TWO: THREE.TOUCH.DOLLY_PAN,
    }

    const el = renderer.domElement
    const signal = abortController.signal
    let rightDragging = false
    let lastX = 0
    let lastY = 0

    el.addEventListener('pointerdown', (e) => {
      if (e.button !== 2) return
      rightDragging = true
      lastX = e.clientX
      lastY = e.clientY
      el.setPointerCapture(e.pointerId)
    }, { signal })

    el.addEventListener('pointermove', (e) => {
      if (!rightDragging || !controls) return
      const dx = e.clientX - lastX
      const dy = e.clientY - lastY
      lastX = e.clientX
      lastY = e.clientY

      const forward = new THREE.Vector3()
      camera.getWorldDirection(forward)
      forward.y = 0
      forward.normalize()

      const right = new THREE.Vector3()
        .crossVectors(forward, new THREE.Vector3(0, 1, 0))
        .normalize()

      const dist = camera.position.distanceTo(controls.target)
      const sensitivity = dist * 0.0016

      const offset = new THREE.Vector3()
        .addScaledVector(right, -dx * sensitivity)
        .addScaledVector(forward, dy * sensitivity)

      controls.target.add(offset)
      camera.position.add(offset)
    }, { signal })

    el.addEventListener('pointerup', (e) => {
      if (e.button !== 2) return
      rightDragging = false
    }, { signal })

    el.addEventListener('lostpointercapture', () => {
      rightDragging = false
    }, { signal })
  }

  const stop = watch(rendererRef, (renderer) => {
    if (renderer && !controls) createControls(renderer)
  }, { immediate: true })

  const initialCameraPos = { x: camera.position.x, y: camera.position.y, z: camera.position.z }

  function _animateTo(camPos: THREE.Vector3, target?: THREE.Vector3) {
    _animCamPos = camPos
    _animTarget = target ?? controls?.target.clone() ?? new THREE.Vector3()
  }

  function update() {
    if (_animCamPos && _animTarget && controls) {
      camera.position.lerp(_animCamPos, LERP_FACTOR)
      controls.target.lerp(_animTarget, LERP_FACTOR)

      const camDist = camera.position.distanceTo(_animCamPos)
      const tgtDist = controls.target.distanceTo(_animTarget)
      if (camDist < CONVERGE_THRESHOLD && tgtDist < CONVERGE_THRESHOLD) {
        camera.position.copy(_animCamPos)
        controls.target.copy(_animTarget)
        _animCamPos = null
        _animTarget = null
      }
    }
    controls?.update()
  }

  function zoomIn(factor = 0.8) {
    if (!controls) return
    const dir = camera.position.clone().sub(controls.target)
    const newLen = Math.max(dir.length() * factor, controls.minDistance)
    const newPos = controls.target.clone().add(dir.normalize().multiplyScalar(newLen))
    _animateTo(newPos)
  }

  function zoomOut(factor = 1.25) {
    if (!controls) return
    const dir = camera.position.clone().sub(controls.target)
    const newLen = Math.min(dir.length() * factor, controls.maxDistance)
    const newPos = controls.target.clone().add(dir.normalize().multiplyScalar(newLen))
    _animateTo(newPos)
  }

  function resetView() {
    if (!controls) return
    const newPos = new THREE.Vector3(initialCameraPos.x, initialCameraPos.y, initialCameraPos.z)
    const newTarget = new THREE.Vector3(0, 0, 0)
    _animateTo(newPos, newTarget)
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

    const newTarget = controls.target.clone().add(offset)
    const newCamPos = camera.position.clone().add(offset)
    _animateTo(newCamPos, newTarget)
  }

  function focusOnPosition(worldX: number, worldZ: number) {
    if (!controls) return
    const newTarget = new THREE.Vector3(worldX, 0, worldZ)
    const offset = camera.position.clone().sub(controls.target)
    const newCamPos = newTarget.clone().add(offset)
    _animateTo(newCamPos, newTarget)
  }

  function getCameraXZDirections(): { right: { x: number; z: number }; forward: { x: number; z: number } } {
    if (!controls) return { right: { x: 1, z: 0 }, forward: { x: 0, z: -1 } }

    const fwd = new THREE.Vector3()
    camera.getWorldDirection(fwd)
    fwd.y = 0
    fwd.normalize()

    const rt = new THREE.Vector3().crossVectors(fwd, new THREE.Vector3(0, 1, 0)).normalize()

    return {
      right: { x: rt.x, z: rt.z },
      forward: { x: fwd.x, z: fwd.z },
    }
  }

  onUnmounted(() => {
    abortController.abort()
    stop()
    controls?.dispose()
    controls = null
  })

  return { update, zoomIn, zoomOut, resetView, panBy, focusOnPosition, getCameraXZDirections, get controls() { return controls } }
}
