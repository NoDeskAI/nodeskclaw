import * as THREE from 'three'
import { HEX_SIZE, FLOOR_SPACING } from '@/composables/useHexLayout'

const PLATFORM_RADIUS = HEX_SIZE * 5
const PLATFORM_THICKNESS = 0.15
const PILLAR_RADIUS = 0.08
const PILLAR_HEIGHT = FLOOR_SPACING * 0.9
const EDGE_TUBE_RADIUS = 0.04

const _sharedGeo = {
  platform: null as THREE.CylinderGeometry | null,
  pillar: null as THREE.CylinderGeometry | null,
}

function getSharedGeo() {
  if (!_sharedGeo.platform) {
    _sharedGeo.platform = new THREE.CylinderGeometry(
      PLATFORM_RADIUS, PLATFORM_RADIUS, PLATFORM_THICKNESS, 6,
    )
    _sharedGeo.pillar = new THREE.CylinderGeometry(
      PILLAR_RADIUS, PILLAR_RADIUS, PILLAR_HEIGHT, 8,
    )
  }
  return _sharedGeo as { platform: THREE.CylinderGeometry; pillar: THREE.CylinderGeometry }
}

function createHexEdgeRing(radius: number, y: number, color: number): THREE.Line {
  const pts: THREE.Vector3[] = []
  for (let i = 0; i <= 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 6
    pts.push(new THREE.Vector3(
      radius * Math.cos(angle), y, radius * Math.sin(angle),
    ))
  }
  const geo = new THREE.BufferGeometry().setFromPoints(pts)
  const mat = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.6,
  })
  return new THREE.Line(geo, mat)
}

export function createFloorPlatform(floor: number, accentColor: number): THREE.Group {
  const group = new THREE.Group()
  const baseY = floor * FLOOR_SPACING
  group.position.y = baseY
  group.name = `floor-${floor}`

  const geo = getSharedGeo()

  const platMat = new THREE.MeshPhysicalMaterial({
    color: 0x1a1a2e,
    metalness: 0.1,
    roughness: 0.3,
    transparent: true,
    opacity: 0.35,
    transmission: 0.4,
    thickness: 0.5,
    side: THREE.DoubleSide,
  })
  const platform = new THREE.Mesh(geo.platform, platMat)
  platform.receiveShadow = true
  group.add(platform)
  group.userData.platMat = platMat

  const topEdge = createHexEdgeRing(PLATFORM_RADIUS, PLATFORM_THICKNESS / 2 + 0.01, accentColor)
  group.add(topEdge)
  const bottomEdge = createHexEdgeRing(PLATFORM_RADIUS, -PLATFORM_THICKNESS / 2 - 0.01, accentColor)
  group.add(bottomEdge)

  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i - Math.PI / 6
    const x = PLATFORM_RADIUS * Math.cos(angle)
    const z = PLATFORM_RADIUS * Math.sin(angle)

    const pillarMat = new THREE.MeshStandardMaterial({
      color: accentColor,
      emissive: new THREE.Color(accentColor),
      emissiveIntensity: 0.3,
      transparent: true,
      opacity: 0.7,
    })
    const pillar = new THREE.Mesh(geo.pillar, pillarMat)
    pillar.position.set(x, PILLAR_HEIGHT / 2, z)
    group.add(pillar)
  }

  const hexGridLines = createFloorHexGrid(accentColor)
  hexGridLines.position.y = PLATFORM_THICKNESS / 2 + 0.005
  group.add(hexGridLines)

  return group
}

function createFloorHexGrid(color: number): THREE.LineSegments {
  const gridRange = 4
  const r = HEX_SIZE
  const vertices: number[] = []
  const angles: number[] = []
  for (let i = 0; i < 6; i++) {
    angles.push((Math.PI / 3) * i - Math.PI / 6)
  }

  for (let q = -gridRange; q <= gridRange; q++) {
    for (let row = -gridRange; row <= gridRange; row++) {
      if (Math.abs(q) + Math.abs(row) + Math.abs(-q - row) > gridRange * 2) continue
      const SQRT3 = Math.sqrt(3)
      const cx = HEX_SIZE * (SQRT3 * q + (SQRT3 / 2) * row)
      const cy = HEX_SIZE * (1.5 * row)
      for (let i = 0; i < 6; i++) {
        const a1 = angles[i]
        const a2 = angles[(i + 1) % 6]
        vertices.push(cx + r * Math.cos(a1), 0, cy + r * Math.sin(a1))
        vertices.push(cx + r * Math.cos(a2), 0, cy + r * Math.sin(a2))
      }
    }
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
  return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.12,
  }))
}

export function updateFloorTransparency(
  group: THREE.Group,
  cameraY: number,
  floor: number,
) {
  const floorY = floor * FLOOR_SPACING
  const dist = Math.abs(cameraY - floorY)
  const opacity = dist < FLOOR_SPACING ? 0.15 + 0.2 * (dist / FLOOR_SPACING) : 0.4
  const mat = group.userData.platMat as THREE.MeshPhysicalMaterial | undefined
  if (mat) mat.opacity = opacity
}

export function disposeFloorPlatformShared() {
  _sharedGeo.platform?.dispose()
  _sharedGeo.pillar?.dispose()
  _sharedGeo.platform = null
  _sharedGeo.pillar = null
}
