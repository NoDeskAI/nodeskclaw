import * as THREE from 'three'

// ---- Shared Geometries (one per module, reused across all robots) ----

const headShellGeo = new THREE.SphereGeometry(0.28, 16, 16)
const faceMaskGeo = new THREE.PlaneGeometry(0.32, 0.18)
const maskBorderGeo = new THREE.RingGeometry(0.17, 0.19, 32)

const ledEyeGeo = (() => {
  const w = 0.032, h = 0.045, r = 0.012
  const s = new THREE.Shape()
  s.moveTo(-w / 2 + r, -h / 2)
  s.lineTo(w / 2 - r, -h / 2)
  s.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r)
  s.lineTo(w / 2, h / 2 - r)
  s.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2)
  s.lineTo(-w / 2 + r, h / 2)
  s.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r)
  s.lineTo(-w / 2, -h / 2 + r)
  s.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2)
  return new THREE.ShapeGeometry(s)
})()

const mouthGeo = (() => {
  const curve = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(-0.04, 0, 0),
    new THREE.Vector3(0, -0.02, 0),
    new THREE.Vector3(0.04, 0, 0),
  )
  return new THREE.BufferGeometry().setFromPoints(curve.getPoints(10))
})()

const panelLineGeo = new THREE.RingGeometry(0.27, 0.275, 32, 1, 0, Math.PI)
const earGeo = new THREE.CylinderGeometry(0.06, 0.06, 0.04, 12)
const torsoGeo = new THREE.CylinderGeometry(0.18, 0.22, 0.3, 12)
const chestPanelGeo = new THREE.PlaneGeometry(0.16, 0.12)
const chestLightGeo = new THREE.CircleGeometry(0.03, 16)
const beltGeo = new THREE.TorusGeometry(0.2, 0.02, 8, 24)
const legGeo = new THREE.CylinderGeometry(0.06, 0.07, 0.15, 8)
const footGeo = new THREE.SphereGeometry(0.07, 12, 8)
const shoulderGeo = new THREE.SphereGeometry(0.05, 8, 8)
const armSegGeo = new THREE.CylinderGeometry(0.035, 0.04, 0.15, 8)
const handGeo = new THREE.SphereGeometry(0.045, 8, 8)
const antennaBaseGeo = new THREE.CylinderGeometry(0.03, 0.04, 0.04, 8)
const antennaRodGeo = new THREE.CylinderGeometry(0.015, 0.02, 0.12, 8)
const antennaLightGeo = new THREE.SphereGeometry(0.035, 12, 8)
const glowLineGeo = new THREE.PlaneGeometry(0.01, 0.2)
const statusRingGeo = new THREE.RingGeometry(0.28, 0.32, 32)
const thoughtGeos = [
  new THREE.CircleGeometry(0.04, 6),
  new THREE.CircleGeometry(0.06, 6),
  new THREE.CircleGeometry(0.09, 6),
]

// ---- Shared Structural Materials (opaque, same for all robots) ----

const bodyMainMat = new THREE.MeshStandardMaterial({
  color: 0x2a3a4a, metalness: 0.7, roughness: 0.3,
})
const bodySecMat = new THREE.MeshStandardMaterial({
  color: 0x3a4a5a, metalness: 0.6, roughness: 0.4,
})
const bodyTerMat = new THREE.MeshStandardMaterial({
  color: 0x4a5a6a, metalness: 0.7, roughness: 0.3,
})
const faceMaskMat = new THREE.MeshStandardMaterial({
  color: 0x1a1a2e, transparent: true, opacity: 0.9,
})
const chestPanelMat = new THREE.MeshStandardMaterial({
  color: 0x1a1a2e, transparent: true, opacity: 0.8,
})
const panelLineMat = new THREE.MeshBasicMaterial({
  color: 0x1a2a3a, side: THREE.DoubleSide,
})

// ---- Status → Accent Color ----

const STATUS_ACCENT: Record<string, number> = {
  running: 0x4ade80, active: 0x4ade80,
  learning: 0x60a5fa,
  thinking: 0xa78bfa,
  pending: 0xfbbf24,
  idle: 0x8b8b9e,
  error: 0xf87171, failed: 0xf87171,
  restarting: 0xf97316, deploying: 0xf97316,
  updating: 0xf97316, creating: 0xf97316,
}

const DISCONNECTED_ACCENT = 0x555566
const DEFAULT_ACCENT = 0x67e8f9

type AnimState = 'idle' | 'working' | 'thinking' | 'error' | 'disconnected'

function resolveAnimState(status: string, sseConnected: boolean): AnimState {
  if (!sseConnected) return 'disconnected'
  switch (status) {
    case 'running': case 'active': case 'learning':
    case 'restarting': case 'deploying': case 'updating': case 'creating':
      return 'working'
    case 'thinking':
      return 'thinking'
    case 'error': case 'failed':
      return 'error'
    default:
      return 'idle'
  }
}

// ---- Per-Robot Animatable Parts ----

interface GrabbyParts {
  mainGroup: THREE.Group
  headGroup: THREE.Group
  leftArmGroup: THREE.Group
  rightArmGroup: THREE.Group
  statusRing: THREE.Mesh
  antennaLight: THREE.Mesh
  chestLight: THREE.Mesh
  thoughtBubbles: THREE.Mesh[]
  accentMat: THREE.MeshBasicMaterial
  antennaLightMat: THREE.MeshStandardMaterial
  statusRingMat: THREE.MeshBasicMaterial
  chestLightMat: THREE.MeshBasicMaterial
  mouthMat: THREE.LineBasicMaterial
  glowLineMats: THREE.MeshBasicMaterial[]
  thoughtMats: THREE.MeshBasicMaterial[]
}

// ---- Public API ----

export function createGrabby(themeColor: number = DEFAULT_ACCENT): THREE.Group {
  const robot = new THREE.Group()
  robot.name = 'grabby'

  const accentMat = new THREE.MeshBasicMaterial({ color: themeColor })
  const antennaLightMat = new THREE.MeshStandardMaterial({
    color: themeColor,
    emissive: new THREE.Color(themeColor),
    emissiveIntensity: 0.8,
  })
  const statusRingMat = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.6, side: THREE.DoubleSide,
  })
  const chestLightMat = new THREE.MeshBasicMaterial({
    color: 0xa78bfa, transparent: true, opacity: 0.8,
  })
  const glowLineMat1 = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.4, side: THREE.DoubleSide,
  })
  const glowLineMat2 = glowLineMat1.clone()
  const mouthMat = new THREE.LineBasicMaterial({ color: themeColor })

  const mainGroup = new THREE.Group()

  // ---- Head Group ----
  const headGroup = new THREE.Group()
  headGroup.position.y = 0.68

  const headShell = new THREE.Mesh(headShellGeo, bodyMainMat)
  headShell.scale.set(1, 0.9, 0.85)
  headGroup.add(headShell)

  const faceMask = new THREE.Mesh(faceMaskGeo, faceMaskMat)
  faceMask.position.set(0, 0, 0.24)
  headGroup.add(faceMask)

  const maskBorder = new THREE.Mesh(maskBorderGeo, accentMat)
  maskBorder.position.set(0, 0, 0.241)
  maskBorder.scale.set(1, 0.6, 1)
  headGroup.add(maskBorder)

  const eyeL = new THREE.Mesh(ledEyeGeo, accentMat)
  eyeL.position.set(-0.06, 0.01, 0.242)
  headGroup.add(eyeL)

  const eyeR = new THREE.Mesh(ledEyeGeo, accentMat)
  eyeR.position.set(0.06, 0.01, 0.242)
  headGroup.add(eyeR)

  const mouth = new THREE.Line(mouthGeo, mouthMat)
  mouth.position.set(0, -0.05, 0.242)
  headGroup.add(mouth)

  const pLine = new THREE.Mesh(panelLineGeo, panelLineMat)
  pLine.rotation.x = Math.PI / 2
  headGroup.add(pLine)

  const earL = new THREE.Mesh(earGeo, bodySecMat)
  earL.position.set(-0.28, 0, 0)
  earL.rotation.z = Math.PI / 2
  headGroup.add(earL)

  const earR = new THREE.Mesh(earGeo, bodySecMat)
  earR.position.set(0.28, 0, 0)
  earR.rotation.z = Math.PI / 2
  headGroup.add(earR)

  const antBase = new THREE.Mesh(antennaBaseGeo, bodySecMat)
  antBase.position.y = 0.28
  headGroup.add(antBase)

  const antRod = new THREE.Mesh(antennaRodGeo, bodyTerMat)
  antRod.position.y = 0.36
  headGroup.add(antRod)

  const antLight = new THREE.Mesh(antennaLightGeo, antennaLightMat)
  antLight.position.y = 0.44
  headGroup.add(antLight)

  mainGroup.add(headGroup)

  // ---- Torso ----
  const torso = new THREE.Mesh(torsoGeo, bodyMainMat)
  torso.position.y = 0.40
  mainGroup.add(torso)

  const chestPanel = new THREE.Mesh(chestPanelGeo, chestPanelMat)
  chestPanel.position.set(0, 0.43, 0.19)
  mainGroup.add(chestPanel)

  const chestLight = new THREE.Mesh(chestLightGeo, chestLightMat)
  chestLight.position.set(0, 0.40, 0.20)
  mainGroup.add(chestLight)

  const belt = new THREE.Mesh(beltGeo, bodyTerMat)
  belt.position.y = 0.25
  belt.rotation.x = Math.PI / 2
  mainGroup.add(belt)

  // ---- Legs & Feet ----
  const legL = new THREE.Mesh(legGeo, bodySecMat)
  legL.position.set(-0.10, 0.14, 0)
  mainGroup.add(legL)

  const legR = new THREE.Mesh(legGeo, bodySecMat)
  legR.position.set(0.10, 0.14, 0)
  mainGroup.add(legR)

  const footL = new THREE.Mesh(footGeo, bodyMainMat)
  footL.position.set(-0.10, 0.04, 0)
  footL.scale.set(1.2, 0.5, 1.3)
  mainGroup.add(footL)

  const footR = new THREE.Mesh(footGeo, bodyMainMat)
  footR.position.set(0.10, 0.04, 0)
  footR.scale.set(1.2, 0.5, 1.3)
  mainGroup.add(footR)

  // ---- Glow Lines ----
  const glowL = new THREE.Mesh(glowLineGeo, glowLineMat1)
  glowL.position.set(-0.21, 0.40, 0)
  glowL.rotation.y = Math.PI / 2
  mainGroup.add(glowL)

  const glowR = new THREE.Mesh(glowLineGeo, glowLineMat2)
  glowR.position.set(0.21, 0.40, 0)
  glowR.rotation.y = -Math.PI / 2
  mainGroup.add(glowR)

  // ---- Arms ----
  const leftArmGroup = new THREE.Group()
  leftArmGroup.position.set(-0.25, 0.52, 0)
  leftArmGroup.add(new THREE.Mesh(shoulderGeo, bodyTerMat))
  const armL = new THREE.Mesh(armSegGeo, bodySecMat)
  armL.position.y = -0.10
  leftArmGroup.add(armL)
  const handL = new THREE.Mesh(handGeo, bodyTerMat)
  handL.position.y = -0.20
  leftArmGroup.add(handL)
  mainGroup.add(leftArmGroup)

  const rightArmGroup = new THREE.Group()
  rightArmGroup.position.set(0.25, 0.52, 0)
  rightArmGroup.add(new THREE.Mesh(shoulderGeo, bodyTerMat))
  const armR = new THREE.Mesh(armSegGeo, bodySecMat)
  armR.position.y = -0.10
  rightArmGroup.add(armR)
  const handR = new THREE.Mesh(handGeo, bodyTerMat)
  handR.position.y = -0.20
  rightArmGroup.add(handR)
  mainGroup.add(rightArmGroup)

  robot.add(mainGroup)

  // ---- Status Ring (stays on ground, not inside mainGroup) ----
  const statusRing = new THREE.Mesh(statusRingGeo, statusRingMat)
  statusRing.rotation.x = -Math.PI / 2
  statusRing.position.y = 0.01
  robot.add(statusRing)

  // ---- Thought Bubbles (hexagonal, hidden by default) ----
  const thoughtBubbles: THREE.Mesh[] = []
  const thoughtMats: THREE.MeshBasicMaterial[] = []
  const bubblePositions = [
    { x: 0.15, y: 1.15, z: 0.1 },
    { x: 0.22, y: 1.25, z: 0.15 },
    { x: 0.12, y: 1.38, z: 0.1 },
  ]
  for (let i = 0; i < 3; i++) {
    const mat = new THREE.MeshBasicMaterial({
      color: themeColor, transparent: true, opacity: 0, side: THREE.DoubleSide,
    })
    const bubble = new THREE.Mesh(thoughtGeos[i], mat)
    bubble.position.set(bubblePositions[i].x, bubblePositions[i].y, bubblePositions[i].z)
    bubble.userData.baseY = bubblePositions[i].y
    bubble.visible = false
    robot.add(bubble)
    thoughtBubbles.push(bubble)
    thoughtMats.push(mat)
  }

  robot.userData.parts = {
    mainGroup, headGroup, leftArmGroup, rightArmGroup,
    statusRing, antennaLight: antLight, chestLight, thoughtBubbles,
    accentMat, antennaLightMat, statusRingMat, chestLightMat,
    mouthMat, glowLineMats: [glowLineMat1, glowLineMat2], thoughtMats,
  } satisfies GrabbyParts

  robot.userData.lastAccentColor = themeColor
  robot.scale.setScalar(0.65)

  return robot
}

export function animateGrabby(
  robot: THREE.Group,
  status: string,
  sseConnected: boolean,
  time: number,
): void {
  const parts = robot.userData.parts as GrabbyParts | undefined
  if (!parts) return

  const animState = resolveAnimState(status, sseConnected)

  const targetColor = sseConnected
    ? (STATUS_ACCENT[status] ?? DEFAULT_ACCENT)
    : DISCONNECTED_ACCENT
  if (robot.userData.lastAccentColor !== targetColor) {
    updateGrabbyColor(robot, targetColor)
    robot.userData.lastAccentColor = targetColor
  }

  if (animState !== 'disconnected') {
    parts.statusRing.rotation.z += animState === 'working' ? 0.03 : 0.015
    parts.antennaLightMat.emissiveIntensity = 0.5 + Math.sin(time * 3) * 0.3
    parts.chestLightMat.opacity = 0.6 + Math.sin(time * 2) * 0.3
  } else {
    parts.antennaLightMat.emissiveIntensity = 0.1
    parts.chestLightMat.opacity = 0.2
    parts.statusRingMat.opacity = 0.2
  }

  switch (animState) {
    case 'idle':
      parts.mainGroup.position.y = Math.sin(time * 1.5) * 0.02
      parts.mainGroup.position.x *= 0.92
      parts.leftArmGroup.rotation.x = Math.sin(time * 1.2) * 0.1
      parts.rightArmGroup.rotation.x = Math.sin(time * 1.2 + Math.PI) * 0.1
      parts.rightArmGroup.rotation.z *= 0.92
      parts.headGroup.rotation.z *= 0.92
      fadeThoughtBubbles(parts, false, time)
      break

    case 'working':
      parts.mainGroup.position.y = Math.abs(Math.sin(time * 4)) * 0.015
      parts.mainGroup.position.x *= 0.92
      parts.rightArmGroup.rotation.x = Math.sin(time * 6) * 0.4
      parts.rightArmGroup.rotation.z *= 0.92
      parts.leftArmGroup.rotation.x = Math.sin(time * 2) * 0.08
      parts.headGroup.rotation.z *= 0.92
      fadeThoughtBubbles(parts, false, time)
      break

    case 'thinking':
      parts.mainGroup.position.y = Math.sin(time) * 0.01
      parts.mainGroup.position.x *= 0.92
      parts.headGroup.rotation.z = Math.sin(time * 0.8) * 0.1 + 0.15
      parts.rightArmGroup.rotation.x = -0.8
      parts.rightArmGroup.rotation.z = 0.3
      parts.leftArmGroup.rotation.x = 0.1
      fadeThoughtBubbles(parts, true, time)
      break

    case 'error':
      parts.mainGroup.position.x = Math.sin(time * 20) * 0.02
      parts.mainGroup.position.y = 0
      parts.leftArmGroup.rotation.x *= 0.9
      parts.rightArmGroup.rotation.x *= 0.9
      parts.rightArmGroup.rotation.z *= 0.9
      parts.headGroup.rotation.z *= 0.9
      parts.statusRingMat.opacity = 0.3 + Math.sin(time * 8) * 0.3
      fadeThoughtBubbles(parts, false, time)
      break

    case 'disconnected':
      parts.mainGroup.position.y *= 0.92
      parts.mainGroup.position.x *= 0.92
      parts.leftArmGroup.rotation.x *= 0.92
      parts.rightArmGroup.rotation.x *= 0.92
      parts.rightArmGroup.rotation.z *= 0.92
      parts.headGroup.rotation.z *= 0.92
      fadeThoughtBubbles(parts, false, time)
      break
  }
}

function fadeThoughtBubbles(parts: GrabbyParts, show: boolean, time: number): void {
  for (let i = 0; i < parts.thoughtBubbles.length; i++) {
    const bubble = parts.thoughtBubbles[i]
    const mat = parts.thoughtMats[i]
    if (show) {
      bubble.visible = true
      mat.opacity = Math.min(mat.opacity + 0.03, 0.85)
      bubble.position.y = (bubble.userData.baseY as number) + Math.sin(time * 2 + i) * 0.05
    } else {
      mat.opacity = Math.max(mat.opacity - 0.05, 0)
      if (mat.opacity <= 0) bubble.visible = false
    }
  }
}

export function updateGrabbyColor(robot: THREE.Group, color: number): void {
  const parts = robot.userData.parts as GrabbyParts | undefined
  if (!parts) return

  const c = new THREE.Color(color)
  parts.accentMat.color.copy(c)
  parts.antennaLightMat.color.copy(c)
  parts.antennaLightMat.emissive.copy(c)
  parts.statusRingMat.color.copy(c)
  parts.mouthMat.color.copy(c)
  for (const m of parts.glowLineMats) m.color.copy(c)
  for (const m of parts.thoughtMats) m.color.copy(c)
}

export function disposeGrabby(robot: THREE.Group): void {
  const parts = robot.userData.parts as GrabbyParts | undefined
  if (!parts) return

  parts.accentMat.dispose()
  parts.antennaLightMat.dispose()
  parts.statusRingMat.dispose()
  parts.chestLightMat.dispose()
  parts.mouthMat.dispose()
  for (const m of parts.glowLineMats) m.dispose()
  for (const m of parts.thoughtMats) m.dispose()
  robot.userData.parts = null
}

const allSharedGeos: THREE.BufferGeometry[] = [
  headShellGeo, faceMaskGeo, maskBorderGeo, ledEyeGeo, mouthGeo,
  panelLineGeo, earGeo, torsoGeo, chestPanelGeo, chestLightGeo,
  beltGeo, legGeo, footGeo, shoulderGeo, armSegGeo, handGeo,
  antennaBaseGeo, antennaRodGeo, antennaLightGeo, glowLineGeo,
  statusRingGeo, ...thoughtGeos,
]

const allSharedMats: THREE.Material[] = [
  bodyMainMat, bodySecMat, bodyTerMat, faceMaskMat, chestPanelMat, panelLineMat,
]

export function disposeGrabbyShared(): void {
  for (const g of allSharedGeos) g.dispose()
  for (const m of allSharedMats) m.dispose()
}
