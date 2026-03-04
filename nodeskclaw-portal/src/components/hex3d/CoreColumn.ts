import * as THREE from 'three'
import { FLOOR_SPACING } from '@/composables/useHexLayout'

const CORE_RADIUS = 0.25
const SHELL_RADIUS = 0.45
const RING_RADIUS = 0.6
const RING_TUBE = 0.03
const BEACON_RADIUS = 0.2

export interface CoreColumnState {
  group: THREE.Group
  particles: THREE.Points
  rings: THREE.Mesh[]
  beacon: THREE.Mesh
  animate: (time: number) => void
  dispose: () => void
}

export function createCoreColumn(floorCount: number): CoreColumnState {
  const group = new THREE.Group()
  group.name = 'coreColumn'

  const totalHeight = Math.max(floorCount, 2) * FLOOR_SPACING + 2
  const baseY = -1

  const coreGeo = new THREE.CylinderGeometry(CORE_RADIUS, CORE_RADIUS, totalHeight, 16)
  const coreMat = new THREE.MeshStandardMaterial({
    color: 0x7c3aed,
    emissive: new THREE.Color(0x7c3aed),
    emissiveIntensity: 0.6,
    transparent: true,
    opacity: 0.5,
  })
  const core = new THREE.Mesh(coreGeo, coreMat)
  core.position.y = baseY + totalHeight / 2
  group.add(core)

  const shellGeo = new THREE.CylinderGeometry(SHELL_RADIUS, SHELL_RADIUS, totalHeight, 16, 1, true)
  const shellMat = new THREE.MeshPhysicalMaterial({
    color: 0x4c1d95,
    transparent: true,
    opacity: 0.15,
    transmission: 0.6,
    thickness: 0.3,
    metalness: 0.0,
    roughness: 0.1,
    side: THREE.DoubleSide,
  })
  const shell = new THREE.Mesh(shellGeo, shellMat)
  shell.position.y = baseY + totalHeight / 2
  group.add(shell)

  const rings: THREE.Mesh[] = []
  const ringGeo = new THREE.TorusGeometry(RING_RADIUS, RING_TUBE, 8, 32)
  for (let i = 0; i < floorCount; i++) {
    const ringMat = new THREE.MeshStandardMaterial({
      color: 0xa78bfa,
      emissive: new THREE.Color(0xa78bfa),
      emissiveIntensity: 0.5,
      transparent: true,
      opacity: 0.8,
    })
    const ring = new THREE.Mesh(ringGeo, ringMat)
    ring.position.y = i * FLOOR_SPACING
    ring.rotation.x = Math.PI / 2
    group.add(ring)
    rings.push(ring)
  }

  const topY = baseY + totalHeight
  const beaconGeo = new THREE.SphereGeometry(BEACON_RADIUS, 16, 16)
  const beaconMat = new THREE.MeshStandardMaterial({
    color: 0xc084fc,
    emissive: new THREE.Color(0xc084fc),
    emissiveIntensity: 1.0,
    transparent: true,
    opacity: 0.9,
  })
  const beacon = new THREE.Mesh(beaconGeo, beaconMat)
  beacon.position.y = topY
  group.add(beacon)

  const beaconLight = new THREE.PointLight(0xc084fc, 2, 8)
  beaconLight.position.y = topY
  group.add(beaconLight)

  const particles = createCoreParticles(totalHeight, baseY)
  group.add(particles)

  const disposables = [coreGeo, coreMat, shellGeo, shellMat, ringGeo, beaconGeo, beaconMat]

  function animate(time: number) {
    coreMat.emissiveIntensity = 0.4 + Math.sin(time * 2) * 0.2
    beaconMat.emissiveIntensity = 0.8 + Math.sin(time * 3) * 0.3
    beacon.scale.setScalar(1 + Math.sin(time * 2) * 0.1)

    for (let i = 0; i < rings.length; i++) {
      const ring = rings[i]
      ring.rotation.z = time * (0.3 + i * 0.1)
      const mat = ring.material as THREE.MeshStandardMaterial
      mat.emissiveIntensity = 0.3 + Math.sin(time * 2 + i) * 0.2
    }

    const positions = particles.geometry.attributes.position as THREE.BufferAttribute
    for (let i = 0; i < positions.count; i++) {
      let y = positions.getY(i)
      y += 0.02
      if (y > baseY + totalHeight) y = baseY
      positions.setY(i, y)
    }
    positions.needsUpdate = true
  }

  function dispose() {
    for (const d of disposables) d.dispose()
    for (const ring of rings) {
      (ring.material as THREE.Material).dispose()
    }
    const pMat = particles.material as THREE.Material
    pMat.dispose()
    particles.geometry.dispose()
  }

  return { group, particles, rings, beacon, animate, dispose }
}

function createCoreParticles(height: number, baseY: number): THREE.Points {
  const count = 120
  const positions = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    const angle = Math.random() * Math.PI * 2
    const r = 0.15 + Math.random() * 0.35
    positions[i * 3] = Math.cos(angle) * r
    positions[i * 3 + 1] = baseY + Math.random() * height
    positions[i * 3 + 2] = Math.sin(angle) * r
  }
  const geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3))

  const mat = new THREE.PointsMaterial({
    color: 0xc084fc,
    size: 0.06,
    transparent: true,
    opacity: 0.7,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  })
  return new THREE.Points(geo, mat)
}
