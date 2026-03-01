import * as THREE from 'three'

// ---- Shared Geometries (one per module, reused across all robots) ----

const headGeo = new THREE.BoxGeometry(0.38, 0.30, 0.28)
const screenGeo = new THREE.PlaneGeometry(0.32, 0.24)
const screenBorderGeo = new THREE.PlaneGeometry(0.34, 0.26)
const eyeGeo = new THREE.CircleGeometry(0.035, 16)
const mouthGeo = (() => {
  const curve = new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(-0.035, 0, 0),
    new THREE.Vector3(0, -0.015, 0),
    new THREE.Vector3(0.035, 0, 0),
  )
  return new THREE.BufferGeometry().setFromPoints(curve.getPoints(10))
})()
const sensorGeo = new THREE.BoxGeometry(0.04, 0.10, 0.06)
const antennaRodGeo = new THREE.CylinderGeometry(0.012, 0.015, 0.08, 8)
const antennaTipGeo = new THREE.SphereGeometry(0.025, 8, 8)

const torsoGeo = new THREE.SphereGeometry(0.22, 16, 16)
const chestPanelGeo = new THREE.PlaneGeometry(0.14, 0.10)
const chestLightGeo = new THREE.CircleGeometry(0.025, 16)
const glowLineGeo = new THREE.PlaneGeometry(0.008, 0.16)

const shoulderGeo = new THREE.SphereGeometry(0.04, 8, 8)
const armSegGeo = new THREE.CylinderGeometry(0.028, 0.032, 0.12, 8)
const handGeo = new THREE.SphereGeometry(0.038, 8, 8)

const hoverRingGeo = new THREE.RingGeometry(0.14, 0.18, 24)
const statusRingGeo = new THREE.RingGeometry(0.28, 0.32, 32)

const thoughtGeos = [
  new THREE.CircleGeometry(0.04, 6),
  new THREE.CircleGeometry(0.06, 6),
  new THREE.CircleGeometry(0.09, 6),
]

// ---- Mini Phone Geometries ----

const phoneBaseGeo = new THREE.CylinderGeometry(0.05, 0.05, 0.018, 12)
const phoneCradleGeo = new THREE.CylinderGeometry(0.015, 0.015, 0.012, 8)
const phoneHandsetBarGeo = new THREE.CylinderGeometry(0.01, 0.01, 0.055, 8)
const phoneEarpieceGeo = new THREE.SphereGeometry(0.02, 8, 6)

// ---- Shared Structural Materials (brighter silver-blue palette) ----

const bodyMainMat = new THREE.MeshStandardMaterial({
  color: 0x7a8a9a, metalness: 0.7, roughness: 0.3,
})
const bodySecMat = new THREE.MeshStandardMaterial({
  color: 0x8a9aaa, metalness: 0.6, roughness: 0.4,
})
const bodyTerMat = new THREE.MeshStandardMaterial({
  color: 0x9aaabb, metalness: 0.7, roughness: 0.3,
})
const screenBackMat = new THREE.MeshStandardMaterial({
  color: 0x1a2a3e, transparent: true, opacity: 0.95,
})
const chestPanelMat = new THREE.MeshStandardMaterial({
  color: 0x2a3a4e, transparent: true, opacity: 0.8,
})

// ---- Status -> Accent Color ----

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
  hoverRing: THREE.Mesh
  thoughtBubbles: THREE.Mesh[]
  screenMat: THREE.MeshBasicMaterial
  screenBorderMat: THREE.MeshBasicMaterial
  accentMat: THREE.MeshBasicMaterial
  antennaTipMat: THREE.MeshStandardMaterial
  statusRingMat: THREE.MeshBasicMaterial
  hoverRingMat: THREE.MeshBasicMaterial
  chestLightMat: THREE.MeshBasicMaterial
  mouthMat: THREE.LineBasicMaterial
  glowLineMats: THREE.MeshBasicMaterial[]
  thoughtMats: THREE.MeshBasicMaterial[]
}

// ---- Public API ----

export function createGrabby(themeColor: number = DEFAULT_ACCENT): THREE.Group {
  const robot = new THREE.Group()
  robot.name = 'grabby'

  const screenMat = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.15,
  })
  const screenBorderMat = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.3,
  })
  const accentMat = new THREE.MeshBasicMaterial({ color: themeColor })
  const antennaTipMat = new THREE.MeshStandardMaterial({
    color: themeColor,
    emissive: new THREE.Color(themeColor),
    emissiveIntensity: 0.8,
  })
  const statusRingMat = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.6, side: THREE.DoubleSide,
  })
  const hoverRingMat = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.3, side: THREE.DoubleSide,
  })
  const chestLightMat = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.8,
  })
  const glowLineMat1 = new THREE.MeshBasicMaterial({
    color: themeColor, transparent: true, opacity: 0.4, side: THREE.DoubleSide,
  })
  const glowLineMat2 = glowLineMat1.clone()
  const mouthMat = new THREE.LineBasicMaterial({ color: themeColor })

  const mainGroup = new THREE.Group()

  // ---- Head Group (rounded box monitor) ----
  const headGroup = new THREE.Group()
  headGroup.position.y = 0.62

  const headShell = new THREE.Mesh(headGeo, bodyMainMat)
  headGroup.add(headShell)

  const scrBorder = new THREE.Mesh(screenBorderGeo, screenBorderMat)
  scrBorder.position.set(0, 0, 0.141)
  headGroup.add(scrBorder)

  const screen = new THREE.Mesh(screenGeo, screenMat)
  screen.position.set(0, 0, 0.142)
  headGroup.add(screen)

  const eyeL = new THREE.Mesh(eyeGeo, accentMat)
  eyeL.position.set(-0.065, 0.03, 0.143)
  headGroup.add(eyeL)

  const eyeR = new THREE.Mesh(eyeGeo, accentMat)
  eyeR.position.set(0.065, 0.03, 0.143)
  headGroup.add(eyeR)

  const mouth = new THREE.Line(mouthGeo, mouthMat)
  mouth.position.set(0, -0.04, 0.143)
  headGroup.add(mouth)

  const sensorL = new THREE.Mesh(sensorGeo, bodySecMat)
  sensorL.position.set(-0.21, 0, 0)
  headGroup.add(sensorL)

  const sensorR = new THREE.Mesh(sensorGeo, bodySecMat)
  sensorR.position.set(0.21, 0, 0)
  headGroup.add(sensorR)

  const antRodL = new THREE.Mesh(antennaRodGeo, bodyTerMat)
  antRodL.position.set(-0.08, 0.19, 0)
  headGroup.add(antRodL)

  const antTipL = new THREE.Mesh(antennaTipGeo, antennaTipMat)
  antTipL.position.set(-0.08, 0.25, 0)
  headGroup.add(antTipL)

  const antRodR = new THREE.Mesh(antennaRodGeo, bodyTerMat)
  antRodR.position.set(0.08, 0.19, 0)
  headGroup.add(antRodR)

  const antTipR = new THREE.Mesh(antennaTipGeo, antennaTipMat)
  antTipR.position.set(0.08, 0.25, 0)
  headGroup.add(antTipR)

  mainGroup.add(headGroup)

  // ---- Torso (egg/capsule body) ----
  const torso = new THREE.Mesh(torsoGeo, bodyMainMat)
  torso.position.y = 0.36
  torso.scale.set(1, 1.3, 0.9)
  mainGroup.add(torso)

  const chestPanel = new THREE.Mesh(chestPanelGeo, chestPanelMat)
  chestPanel.position.set(0, 0.38, 0.195)
  mainGroup.add(chestPanel)

  const chestLight = new THREE.Mesh(chestLightGeo, chestLightMat)
  chestLight.position.set(0, 0.36, 0.198)
  mainGroup.add(chestLight)

  // ---- Glow Lines (side accents) ----
  const glowL = new THREE.Mesh(glowLineGeo, glowLineMat1)
  glowL.position.set(-0.20, 0.36, 0)
  glowL.rotation.y = Math.PI / 2
  mainGroup.add(glowL)

  const glowR = new THREE.Mesh(glowLineGeo, glowLineMat2)
  glowR.position.set(0.20, 0.36, 0)
  glowR.rotation.y = -Math.PI / 2
  mainGroup.add(glowR)

  // ---- Arms (shorter, proportional to egg body) ----
  const leftArmGroup = new THREE.Group()
  leftArmGroup.position.set(-0.24, 0.46, 0)
  leftArmGroup.add(new THREE.Mesh(shoulderGeo, bodyTerMat))
  const armL = new THREE.Mesh(armSegGeo, bodySecMat)
  armL.position.y = -0.08
  leftArmGroup.add(armL)
  const handL = new THREE.Mesh(handGeo, bodyTerMat)
  handL.position.y = -0.16
  handL.scale.set(1.1, 0.7, 1.1)
  leftArmGroup.add(handL)
  mainGroup.add(leftArmGroup)

  const rightArmGroup = new THREE.Group()
  rightArmGroup.position.set(0.24, 0.46, 0)
  rightArmGroup.add(new THREE.Mesh(shoulderGeo, bodyTerMat))
  const armR = new THREE.Mesh(armSegGeo, bodySecMat)
  armR.position.y = -0.08
  rightArmGroup.add(armR)
  const handR = new THREE.Mesh(handGeo, bodyTerMat)
  handR.position.y = -0.16
  handR.scale.set(1.1, 0.7, 1.1)
  rightArmGroup.add(handR)
  mainGroup.add(rightArmGroup)

  // ---- Hover Ring (thruster glow at bottom) ----
  const hoverRing = new THREE.Mesh(hoverRingGeo, hoverRingMat)
  hoverRing.rotation.x = -Math.PI / 2
  hoverRing.position.y = 0.10
  mainGroup.add(hoverRing)

  robot.add(mainGroup)

  // ---- Status Ring (stays on ground) ----
  const statusRing = new THREE.Mesh(statusRingGeo, statusRingMat)
  statusRing.rotation.x = -Math.PI / 2
  statusRing.position.y = 0.01
  robot.add(statusRing)

  // ---- Thought Bubbles (hexagonal, hidden by default) ----
  const thoughtBubbles: THREE.Mesh[] = []
  const thoughtMats: THREE.MeshBasicMaterial[] = []
  const bubblePositions = [
    { x: 0.15, y: 1.05, z: 0.1 },
    { x: 0.22, y: 1.15, z: 0.15 },
    { x: 0.12, y: 1.28, z: 0.1 },
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
    statusRing, hoverRing, thoughtBubbles,
    screenMat, screenBorderMat, accentMat, antennaTipMat,
    statusRingMat, hoverRingMat, chestLightMat,
    mouthMat, glowLineMats: [glowLineMat1, glowLineMat2], thoughtMats,
  } satisfies GrabbyParts

  robot.userData.lastAccentColor = themeColor
  robot.scale.setScalar(0.65)

  return robot
}

// ---- Mini Retro Phone ----

export function createMiniPhone(themeColor: number = DEFAULT_ACCENT): THREE.Group {
  const phone = new THREE.Group()
  phone.name = 'miniPhone'

  const phoneMat = new THREE.MeshStandardMaterial({
    color: themeColor, metalness: 0.5, roughness: 0.4,
  })
  const phoneBodyMat = new THREE.MeshStandardMaterial({
    color: 0x8a9aaa, metalness: 0.6, roughness: 0.3,
  })
  const phoneGlowMat = new THREE.MeshStandardMaterial({
    color: themeColor,
    emissive: new THREE.Color(themeColor),
    emissiveIntensity: 0.5,
  })

  const base = new THREE.Mesh(phoneBaseGeo, phoneBodyMat)
  phone.add(base)

  const cradleL = new THREE.Mesh(phoneCradleGeo, phoneBodyMat)
  cradleL.position.set(-0.02, 0.015, 0)
  phone.add(cradleL)

  const cradleR = new THREE.Mesh(phoneCradleGeo, phoneBodyMat)
  cradleR.position.set(0.02, 0.015, 0)
  phone.add(cradleR)

  const handsetBar = new THREE.Mesh(phoneHandsetBarGeo, phoneMat)
  handsetBar.position.set(0, 0.028, 0)
  handsetBar.rotation.z = Math.PI / 2
  phone.add(handsetBar)

  const earL = new THREE.Mesh(phoneEarpieceGeo, phoneGlowMat)
  earL.position.set(-0.032, 0.028, 0)
  earL.scale.set(1, 0.7, 1)
  phone.add(earL)

  const earR = new THREE.Mesh(phoneEarpieceGeo, phoneGlowMat)
  earR.position.set(0.032, 0.028, 0)
  earR.scale.set(1, 0.7, 1)
  phone.add(earR)

  phone.userData.phoneMat = phoneMat
  phone.userData.phoneGlowMat = phoneGlowMat

  return phone
}

export function disposeMiniPhone(phone: THREE.Group): void {
  const phoneMat = phone.userData.phoneMat as THREE.MeshStandardMaterial | undefined
  const phoneGlowMat = phone.userData.phoneGlowMat as THREE.MeshStandardMaterial | undefined
  phoneMat?.dispose()
  phoneGlowMat?.dispose()
}

// ---- Animation ----

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
    parts.antennaTipMat.emissiveIntensity = 0.5 + Math.sin(time * 3) * 0.3
    parts.chestLightMat.opacity = 0.6 + Math.sin(time * 2) * 0.3
    parts.hoverRingMat.opacity = 0.2 + Math.sin(time * 2.5) * 0.1
    parts.screenMat.opacity = 0.12 + Math.sin(time * 1.5) * 0.05
  } else {
    parts.antennaTipMat.emissiveIntensity = 0.1
    parts.chestLightMat.opacity = 0.2
    parts.statusRingMat.opacity = 0.2
    parts.hoverRingMat.opacity = 0.1
    parts.screenMat.opacity = 0.05
    parts.screenBorderMat.opacity = 0.1
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
      parts.screenMat.opacity = 0.1 + Math.abs(Math.sin(time * 4)) * 0.15
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
      parts.screenMat.opacity = Math.sin(time * 8) > 0 ? 0.2 : 0.05
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
  parts.screenMat.color.copy(c)
  parts.screenBorderMat.color.copy(c)
  parts.accentMat.color.copy(c)
  parts.antennaTipMat.color.copy(c)
  parts.antennaTipMat.emissive.copy(c)
  parts.statusRingMat.color.copy(c)
  parts.hoverRingMat.color.copy(c)
  parts.chestLightMat.color.copy(c)
  parts.mouthMat.color.copy(c)
  for (const m of parts.glowLineMats) m.color.copy(c)
  for (const m of parts.thoughtMats) m.color.copy(c)
}

export function disposeGrabby(robot: THREE.Group): void {
  const parts = robot.userData.parts as GrabbyParts | undefined
  if (!parts) return

  parts.screenMat.dispose()
  parts.screenBorderMat.dispose()
  parts.accentMat.dispose()
  parts.antennaTipMat.dispose()
  parts.statusRingMat.dispose()
  parts.hoverRingMat.dispose()
  parts.chestLightMat.dispose()
  parts.mouthMat.dispose()
  for (const m of parts.glowLineMats) m.dispose()
  for (const m of parts.thoughtMats) m.dispose()
  robot.userData.parts = null
}

const allSharedGeos: THREE.BufferGeometry[] = [
  headGeo, screenGeo, screenBorderGeo, eyeGeo, mouthGeo,
  sensorGeo, antennaRodGeo, antennaTipGeo,
  torsoGeo, chestPanelGeo, chestLightGeo, glowLineGeo,
  shoulderGeo, armSegGeo, handGeo,
  hoverRingGeo, statusRingGeo, ...thoughtGeos,
  phoneBaseGeo, phoneCradleGeo, phoneHandsetBarGeo, phoneEarpieceGeo,
]

const allSharedMats: THREE.Material[] = [
  bodyMainMat, bodySecMat, bodyTerMat, screenBackMat, chestPanelMat,
]

export function disposeGrabbyShared(): void {
  for (const g of allSharedGeos) g.dispose()
  for (const m of allSharedMats) m.dispose()
}
