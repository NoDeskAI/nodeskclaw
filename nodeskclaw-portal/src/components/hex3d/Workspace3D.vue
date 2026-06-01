<script setup lang="ts">
import { ref, watch, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import * as THREE from 'three'
import { useThreeScene } from '@/composables/useThreeScene'
import { useOrbitControls } from '@/composables/useOrbitControls'
import { useHexRaycaster } from '@/composables/useHexRaycaster'
import { axialToWorld, HEX_SIZE } from '@/composables/useHexLayout'
import { useTopologyBFS } from '@/composables/useTopologyBFS'
import { createGrabby, animateGrabby, updateGrabbyTheme, disposeGrabby, disposeGrabbyShared, createPhoneStation, disposePhoneStation } from './Grabby'
import { createCorridorPath, disposeCorridorPath, disposeCorridorPathShared } from './CorridorPath'
import { heatColorRgb } from '@/composables/useHeatGradient'
import type { AgentBrief, TopologyNode, TopologyEdge, MessageFlowPair } from '@/stores/workspace'

const { t } = useI18n()

type HexType = 'empty' | 'agent' | 'blackboard' | 'human' | 'corridor' | 'device'

interface PerfSummary {
  totalTasks: number
  completedTasks: number
  totalTokenCost: number
  totalValueCreated: number
}

const props = defineProps<{
  agents: AgentBrief[]
  blackboardContent: string
  selectedAgentId: string | null
  selectedHex: { q: number, r: number } | null
  topologyNodes?: TopologyNode[]
  topologyEdges?: TopologyEdge[]
  messageFlowStats?: MessageFlowPair[]
  isMovingHex?: boolean
  movingHexSource?: { q: number, r: number } | null
  perfSummary?: PerfSummary | null
  perfLoading?: boolean
}>()

function formatK(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'k'
  return String(Math.round(n))
}

const emit = defineEmits<{
  (e: 'hex-click', payload: { q: number, r: number, type: HexType, agentId?: string, entityId?: string }): void
  (e: 'agent-dblclick', id: string): void
  (e: 'agent-hover', id: string | null): void
}>()

const containerRef = ref<HTMLElement | null>(null)

const { scene, camera, renderer, addToLoop } = useThreeScene(containerRef, {
  cameraPos: [0, 8, 10],
  fov: 50,
})

const orbitControls = useOrbitControls(camera, renderer)
addToLoop(() => orbitControls.update())

const { hoveredId, selectedId, dblclickId } = useHexRaycaster(scene, camera, containerRef, {
  meshFilter: (obj) => obj.userData?.isHex === true || obj.userData?.hexId != null,
})

watch(hoveredId, (id) => emit('agent-hover', id))
watch(selectedId, (id) => {
  if (!id) return
  if (id === '__blackboard__') {
    emit('hex-click', { q: 0, r: 0, type: 'blackboard' })
  } else if (id.startsWith('empty:')) {
    const [, qs, rs] = id.split(':')
    emit('hex-click', { q: Number(qs), r: Number(rs), type: 'empty' })
  } else if (id.startsWith('corridor:')) {
    const node = props.topologyNodes?.find(n => n.entity_id === id.slice(9))
    if (node) emit('hex-click', { q: node.hex_q, r: node.hex_r, type: 'corridor', entityId: node.entity_id ?? undefined })
  } else if (id.startsWith('human:')) {
    const node = props.topologyNodes?.find(n => n.node_type === 'human' && n.entity_id === id.slice(6))
    if (node) emit('hex-click', { q: node.hex_q, r: node.hex_r, type: 'human', entityId: node.entity_id ?? undefined })
  } else if (id.startsWith('device:')) {
    const node = props.topologyNodes?.find(n => n.node_type === 'device' && n.entity_id === id.slice(7))
    if (node) emit('hex-click', { q: node.hex_q, r: node.hex_r, type: 'device', entityId: node.entity_id ?? undefined })
  } else {
    const agent = props.agents.find((a) => a.instance_id === id)
    if (agent) emit('hex-click', { q: agent.hex_q, r: agent.hex_r, type: 'agent', agentId: id })
  }
})
watch(dblclickId, (id) => {
  if (id && props.agents.some(a => a.instance_id === id)) emit('agent-dblclick', id)
})

// Environment setup
const ambientLight = new THREE.AmbientLight(0x8888cc, 0.6)
scene.add(ambientLight)

const dirLight = new THREE.DirectionalLight(0xffffff, 0.8)
dirLight.position.set(5, 10, 5)
scene.add(dirLight)

// Honeycomb hex grid lines (vibecraft-style)
const hexGridGroup = createWorldHexGrid()
scene.add(hexGridGroup)

scene.fog = new THREE.FogExp2(0x0a0a1a, 0.04)
scene.background = new THREE.Color(0x0a0a1a)

// Hex meshes management
const hexMeshes = new Map<string, THREE.Group>()
const labelSprites = new Set<THREE.Sprite>()
const LABEL_REF_DISTANCE = 12
const _tmpWorldPos = new THREE.Vector3()

const HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.9, HEX_SIZE * 0.9, 0.3, 6)
const AGENT_BASE_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.9, HEX_SIZE * 0.9, 0.08, 6)
const AGENT_BASE_EDGE_GEO = new THREE.EdgesGeometry(AGENT_BASE_GEO)

const STATUS_COLORS_3D: Record<string, number> = {
  running: 0x4ade80, active: 0x4ade80, learning: 0x60a5fa,
  thinking: 0xfbbf24, pending: 0xfbbf24,
  idle: 0x8b8b9e,
  error: 0xf87171, failed: 0xf87171,
  restarting: 0xf97316, deploying: 0xf97316, updating: 0xf97316, creating: 0xf97316,
}
const DISCONNECTED_COLOR = 0x555566
const SHOW_AGENT_ROBOT = false
const SHOW_AGENT_PHONE = false

function getAgentBaseColor(agent: AgentBrief): number {
  return agent.theme_color
    ? parseInt(agent.theme_color.replace('#', ''), 16)
    : (STATUS_COLORS_3D[agent.status] ?? 0xa78bfa)
}

const HEAT_EDGE_RADIUS_3D = HEX_SIZE * 0.9 * 1.08

function createHexMesh(agent: AgentBrief): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(agent.hex_q, agent.hex_r)
  group.position.set(x, 0.04, y)
  group.userData = { hexId: agent.instance_id, isHex: true, sseConnected: agent.sse_connected, hexQ: agent.hex_q, hexR: agent.hex_r }

  const baseColor = getAgentBaseColor(agent)
  const color = agent.sse_connected ? baseColor : DISCONNECTED_COLOR
  const bodyTheme = baseColor

  const baseMat = new THREE.MeshStandardMaterial({
    color,
    emissive: new THREE.Color(color),
    emissiveIntensity: agent.sse_connected ? 0.15 : 0.05,
    metalness: 0.2,
    roughness: 0.6,
    transparent: true,
    opacity: agent.sse_connected ? 0.9 : 0.5,
  })
  const baseMesh = new THREE.Mesh(AGENT_BASE_GEO, baseMat)
  baseMesh.userData = { hexId: agent.instance_id, isHex: true }
  group.add(baseMesh)

  const edgeMat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.5 })
  group.add(new THREE.LineSegments(AGENT_BASE_EDGE_GEO, edgeMat))

  const heatEdgeMats: THREE.LineBasicMaterial[] = []
  const heatEdgeLines: THREE.Line[] = []
  for (let i = 0; i < 6; i++) {
    const a1 = (Math.PI / 3) * i
    const a2 = (Math.PI / 3) * ((i + 1) % 6)
    const x1 = Math.sin(a1) * HEAT_EDGE_RADIUS_3D
    const z1 = Math.cos(a1) * HEAT_EDGE_RADIUS_3D
    const x2 = Math.sin(a2) * HEAT_EDGE_RADIUS_3D
    const z2 = Math.cos(a2) * HEAT_EDGE_RADIUS_3D
    const geo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x1, 0.06, z1),
      new THREE.Vector3(x2, 0.06, z2),
    ])
    const mat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, linewidth: 2 })
    const line = new THREE.Line(geo, mat)
    line.visible = false
    group.add(line)
    heatEdgeMats.push(mat)
    heatEdgeLines.push(line)
  }
  group.userData.heatEdgeMats = heatEdgeMats
  group.userData.heatEdgeLines = heatEdgeLines

  if (SHOW_AGENT_ROBOT) {
    const robot = createGrabby(bodyTheme)
    robot.position.y = 0.04
    group.add(robot)
    group.userData.robot = robot
  }

  if (SHOW_AGENT_PHONE) {
    const phone = createPhoneStation(color)
    phone.position.set(0.45, 0.02, 0.35)
    phone.rotation.y = -Math.PI / 6
    phone.visible = agent.sse_connected
    group.add(phone)
    group.userData.phone = phone
  }

  return group
}

function createWorldHexGrid(): THREE.LineSegments {
  const gridRange = 8
  const r = HEX_SIZE
  const vertices: number[] = []
  const angles: number[] = []
  for (let i = 0; i < 6; i++) {
    angles.push((Math.PI / 3) * i - Math.PI / 6)
  }

  for (let q = -gridRange; q <= gridRange; q++) {
    for (let row = -gridRange; row <= gridRange; row++) {
      if (Math.abs(q) + Math.abs(row) + Math.abs(-q - row) > gridRange * 2) continue
      const { x, y } = axialToWorld(q, row)
      for (let i = 0; i < 6; i++) {
        const a1 = angles[i]
        const a2 = angles[(i + 1) % 6]
        vertices.push(x + r * Math.cos(a1), 0, y + r * Math.sin(a1))
        vertices.push(x + r * Math.cos(a2), 0, y + r * Math.sin(a2))
      }
    }
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
  const material = new THREE.LineBasicMaterial({
    color: 0x4ac8e8,
    transparent: true,
    opacity: 0.2,
  })
  const lines = new THREE.LineSegments(geometry, material)
  lines.position.y = 0.005
  return lines
}

function createBlackboardMesh(): THREE.Group {
  const group = new THREE.Group()
  group.position.set(0, 0.15, 0)
  group.userData = { hexId: '__blackboard__', isHex: true }

  const bbSize = HEX_SIZE * 0.95
  const bbGeo = new THREE.CylinderGeometry(bbSize, bbSize, 0.15, 6)
  const bbMat = new THREE.MeshStandardMaterial({
    color: 0x1a1a2e,
    emissive: new THREE.Color(0xa78bfa),
    emissiveIntensity: 0.15,
    metalness: 0.3,
    roughness: 0.5,
    transparent: true,
    opacity: 0.9,
  })
  const mesh = new THREE.Mesh(bbGeo, bbMat)
  mesh.raycast = () => {}
  group.add(mesh)

  const edgeGeo = new THREE.EdgesGeometry(bbGeo)
  const edgeMat = new THREE.LineBasicMaterial({
    color: 0xa78bfa,
    transparent: true,
    opacity: 0.5,
  })
  const edges = new THREE.LineSegments(edgeGeo, edgeMat)
  group.add(edges)

  const hitMat = new THREE.MeshBasicMaterial({ visible: false })
  const hitMesh = new THREE.Mesh(HEX_GEO, hitMat)
  hitMesh.userData = { hexId: '__blackboard__', isHex: true }
  group.add(hitMesh)

  const labelSprite = createBBLabelSprite()
  labelSprite.position.set(0, 0.25, 0)
  labelSprite.name = 'bb-stats-label'
  group.add(labelSprite)
  labelSprites.add(labelSprite)

  return group
}

let bbLabelSprite: THREE.Sprite | null = null

function drawBBLabelCanvas(canvas: HTMLCanvasElement) {
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, canvas.width, canvas.height)

  ctx.font = 'bold 20px sans-serif'
  ctx.fillStyle = '#a78bfa'
  ctx.textAlign = 'center'
  ctx.fillText(t('workspaceView.bbTitle'), 128, 22)

  const ps = props.perfSummary
  if (ps) {
    ctx.font = '14px sans-serif'
    ctx.fillStyle = '#9ca3af'
    ctx.fillText(
      t('workspaceView.bbInputLine', { done: ps.completedTasks, tasks: ps.totalTasks }),
      128, 44,
    )
    ctx.font = '12px sans-serif'
    ctx.fillStyle = '#6b7280'
    ctx.fillText(
      t('workspaceView.bbOutputLine', { value: formatK(ps.totalValueCreated) }),
      128, 62,
    )
  } else if (!props.perfLoading && props.blackboardContent) {
    ctx.font = '14px sans-serif'
    ctx.fillStyle = '#9ca3af'
    const text = props.blackboardContent.length > 20
      ? props.blackboardContent.slice(0, 20) + '...'
      : props.blackboardContent
    ctx.fillText(text, 128, 44)
  }
}

function createBBLabelSprite(): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 80
  drawBBLabelCanvas(canvas)
  const texture = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(1.2, 0.4, 1)
  sprite.userData.baseScale = { x: 1.2, y: 0.4 }
  sprite.userData.canvas = canvas
  bbLabelSprite = sprite
  return sprite
}

watch(() => props.perfSummary, () => {
  if (!bbLabelSprite) return
  const canvas = bbLabelSprite.userData.canvas as HTMLCanvasElement
  if (!canvas) return
  drawBBLabelCanvas(canvas)
  const tex = bbLabelSprite.material.map
  if (tex) tex.needsUpdate = true
}, { deep: true })

const HUMAN_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.7, HEX_SIZE * 0.7, 0.5, 6)
const DEVICE_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.68, HEX_SIZE * 0.68, 0.42, 6)

function createAgentLabelSprite(name: string, label?: string | null): THREE.Sprite {
  const canvas = document.createElement('canvas')
  const hasLabel = !!label
  canvas.width = 256
  canvas.height = hasLabel ? 56 : 36
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'transparent'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.font = 'bold 16px sans-serif'
  ctx.fillStyle = '#e2e8f0'
  ctx.textAlign = 'center'
  ctx.fillText(name.slice(0, 16), 128, 18)
  if (hasLabel) {
    ctx.font = '12px sans-serif'
    ctx.fillStyle = '#94a3b8'
    ctx.fillText(label!.slice(0, 20), 128, 40)
  }
  const texture = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true })
  const sprite = new THREE.Sprite(mat)
  const sy = hasLabel ? 0.28 : 0.18
  sprite.scale.set(1.2, sy, 1)
  sprite.userData.baseScale = { x: 1.2, y: sy }
  return sprite
}

function createCorridorLabelSprite(name: string): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 40
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'transparent'
  ctx.fillRect(0, 0, 256, 40)
  ctx.font = 'bold 18px sans-serif'
  ctx.fillStyle = '#38bdf8'
  ctx.textAlign = 'center'
  ctx.fillText(name.slice(0, 16), 128, 28)
  const texture = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(1.2, 0.2, 1)
  sprite.userData.baseScale = { x: 1.2, y: 0.2 }
  return sprite
}

function createDeviceLabelSprite(name: string): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 44
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'transparent'
  ctx.fillRect(0, 0, 256, 44)
  ctx.font = 'bold 17px sans-serif'
  ctx.fillStyle = '#5eead4'
  ctx.textAlign = 'center'
  ctx.fillText(name.slice(0, 16), 128, 28)
  const texture = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(1.2, 0.22, 1)
  sprite.userData.baseScale = { x: 1.2, y: 0.22 }
  return sprite
}

function createHumanHexMesh(node: TopologyNode): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(node.hex_q, node.hex_r)
  group.position.set(x, 0.25, y)
  const hexId = `human:${node.entity_id}`
  const colorHex = (node.extra?.display_color as string) || '#f59e0b'
  group.userData = { hexId, isHex: true, displayColor: colorHex }
  const color = new THREE.Color(colorHex)
  const mat = new THREE.MeshStandardMaterial({
    color,
    emissive: color.clone(),
    emissiveIntensity: 0.3,
    metalness: 0.2,
    roughness: 0.5,
    transparent: true,
    opacity: 0.9,
  })
  const mesh = new THREE.Mesh(HUMAN_HEX_GEO, mat)
  mesh.userData = { hexId, isHex: true }
  group.add(mesh)

  const edgeColor = color.clone().offsetHSL(0, 0.1, 0.1)
  const edgeGeo = new THREE.EdgesGeometry(HUMAN_HEX_GEO)
  const edgeMat = new THREE.LineBasicMaterial({ color: edgeColor, transparent: true, opacity: 0.7 })
  group.add(new THREE.LineSegments(edgeGeo, edgeMat))

  return group
}

function createDeviceHexMesh(node: TopologyNode): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(node.hex_q, node.hex_r)
  group.position.set(x, 0.22, y)
  const hexId = `device:${node.entity_id}`
  const status = (node.extra?.status as string) || ''
  const colorHex = status === 'provider_unconfigured' ? '#f59e0b' : '#14b8a6'
  group.userData = { hexId, isHex: true, displayColor: colorHex, hexQ: node.hex_q, hexR: node.hex_r }
  const color = new THREE.Color(colorHex)
  const mat = new THREE.MeshStandardMaterial({
    color,
    emissive: color.clone(),
    emissiveIntensity: 0.28,
    metalness: 0.25,
    roughness: 0.5,
    transparent: true,
    opacity: 0.9,
  })
  const mesh = new THREE.Mesh(DEVICE_HEX_GEO, mat)
  mesh.userData = { hexId, isHex: true }
  group.add(mesh)

  const edgeGeo = new THREE.EdgesGeometry(DEVICE_HEX_GEO)
  const edgeMat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.75 })
  group.add(new THREE.LineSegments(edgeGeo, edgeMat))

  return group
}


const GRID_RANGE = 8
const EMPTY_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.9, HEX_SIZE * 0.9, 0.05, 6)

function createEmptyHexMesh(q: number, r: number): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(q, r)
  group.position.set(x, 0.025, y)
  const hexId = `empty:${q}:${r}`
  group.userData = { hexId, isHex: true }

  const mat = new THREE.MeshStandardMaterial({
    color: 0x1a1a3e,
    transparent: true,
    opacity: 0.0,
  })
  const mesh = new THREE.Mesh(EMPTY_HEX_GEO, mat)
  mesh.userData = { hexId, isHex: true }
  group.add(mesh)
  return group
}

function syncScene() {
  for (const [id, group] of hexMeshes) {
    if (group.userData.robot) disposeGrabby(group.userData.robot as THREE.Group)
    if (group.userData.phone) disposePhoneStation(group.userData.phone as THREE.Group)
    if (id.startsWith('corridor:')) disposeCorridorPath(group)
    scene.remove(group)
  }
  hexMeshes.clear()
  labelSprites.clear()

  const corridorNodes = (props.topologyNodes || []).filter(n => n.node_type === 'corridor')
  const humanNodes = (props.topologyNodes || []).filter(n => n.node_type === 'human')
  const deviceNodes = (props.topologyNodes || []).filter(n => n.node_type === 'device')

  const occupied = new Set<string>()
  occupied.add('0:0')
  for (const agent of props.agents) {
    occupied.add(`${agent.hex_q}:${agent.hex_r}`)
  }
  for (const node of corridorNodes) {
    occupied.add(`${node.hex_q}:${node.hex_r}`)
  }
  for (const node of humanNodes) {
    occupied.add(`${node.hex_q}:${node.hex_r}`)
  }
  for (const node of deviceNodes) {
    occupied.add(`${node.hex_q}:${node.hex_r}`)
  }

  for (const agent of props.agents) {
    const group = createHexMesh(agent)
    const agentName = agent.display_name || agent.global_effective_name || agent.name
    const agentLabel = createAgentLabelSprite(agentName, agent.label)
    agentLabel.position.set(0, 0.65, 0)
    group.add(agentLabel)
    labelSprites.add(agentLabel)
    scene.add(group)
    hexMeshes.set(agent.instance_id, group)
  }

  const bbGroup = createBlackboardMesh()
  scene.add(bbGroup)
  hexMeshes.set('__blackboard__', bbGroup)

  for (const node of corridorNodes) {
    const hexId = `corridor:${node.entity_id}`
    const group = createCorridorPath(node.hex_q, node.hex_r, occupied, hexId)
    if (node.display_name) {
      const label = createCorridorLabelSprite(node.display_name)
      label.position.set(0, 0.2, 0)
      group.add(label)
      labelSprites.add(label)
    }
    scene.add(group)
    hexMeshes.set(hexId, group)
  }

  for (const node of humanNodes) {
    const group = createHumanHexMesh(node)
    scene.add(group)
    hexMeshes.set(`human:${node.entity_id}`, group)
  }

  for (const node of deviceNodes) {
    const group = createDeviceHexMesh(node)
    if (node.display_name) {
      const label = createDeviceLabelSprite(node.display_name)
      label.position.set(0, 0.42, 0)
      group.add(label)
      labelSprites.add(label)
    }
    scene.add(group)
    hexMeshes.set(`device:${node.entity_id}`, group)
  }

  for (let q = -GRID_RANGE; q <= GRID_RANGE; q++) {
    for (let r = -GRID_RANGE; r <= GRID_RANGE; r++) {
      if (Math.abs(q) + Math.abs(r) + Math.abs(-q - r) > GRID_RANGE * 2) continue
      if (occupied.has(`${q}:${r}`)) continue
      const group = createEmptyHexMesh(q, r)
      scene.add(group)
      hexMeshes.set(`empty:${q}:${r}`, group)
    }
  }
}

watch([() => props.agents, () => props.topologyNodes], syncScene, { deep: true, immediate: true })

// ── Heat visualization (corridor + agent directional) ──
const AXIAL_DIRS_3D: [number, number][] = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]

function axialDirIndex3d(dq: number, dr: number): number {
  return AXIAL_DIRS_3D.findIndex(([aq, ar]) => aq === dq && ar === dr)
}

const edgeHeatMap3d = computed(() => {
  const stats = props.messageFlowStats
  if (!stats?.length) return new Map<string, number>()
  const raw = new Map<string, number>()
  for (const s of stats) {
    const [sq, sr] = s.sender_hex_key.split(',').map(Number)
    const [rq, rr] = s.receiver_hex_key.split(',').map(Number)
    const path = findPath3d(sq, sr, rq, rr)
    if (!path || path.length < 2) continue
    for (let i = 0; i < path.length - 1; i++) {
      const a = path[i], b = path[i + 1]
      const fwd = `${a.q},${a.r}>${b.q},${b.r}`
      const bwd = `${b.q},${b.r}>${a.q},${a.r}`
      raw.set(fwd, (raw.get(fwd) || 0) + s.count)
      raw.set(bwd, (raw.get(bwd) || 0) + s.count)
    }
  }
  const maxVal = Math.max(...raw.values(), 1)
  const normalized = new Map<string, number>()
  for (const [k, v] of raw) normalized.set(k, v / maxVal)
  return normalized
})

const agentDirHeat3d = computed(() => {
  const stats = props.messageFlowStats
  if (!stats?.length) return new Map<string, number[]>()
  const raw = new Map<string, number[]>()
  for (const s of stats) {
    const [sq, sr] = s.sender_hex_key.split(',').map(Number)
    const [rq, rr] = s.receiver_hex_key.split(',').map(Number)
    const path = findPath3d(sq, sr, rq, rr)
    if (!path || path.length < 2) continue
    const senderKey = `${sq},${sr}`
    if (!raw.has(senderKey)) raw.set(senderKey, [0, 0, 0, 0, 0, 0])
    const sDir = axialDirIndex3d(path[1].q - path[0].q, path[1].r - path[0].r)
    if (sDir >= 0) raw.get(senderKey)![sDir] += s.count

    const receiverKey = `${rq},${rr}`
    if (!raw.has(receiverKey)) raw.set(receiverKey, [0, 0, 0, 0, 0, 0])
    const last = path.length - 1
    const rDir = axialDirIndex3d(path[last - 1].q - path[last].q, path[last - 1].r - path[last].r)
    if (rDir >= 0) raw.get(receiverKey)![rDir] += s.count
  }
  const allMax = Math.max(...[...raw.values()].flatMap(v => v), 1)
  const normalized = new Map<string, number[]>()
  for (const [k, arr] of raw) normalized.set(k, arr.map(v => v / allMax))
  return normalized
})

function heatToThreeColor(heat: number): THREE.Color {
  const [r, g, b] = heatColorRgb(heat)
  return new THREE.Color(r / 255, g / 255, b / 255)
}

function syncCorridorHeat() {
  const heatMap = edgeHeatMap3d.value
  for (const [id, group] of hexMeshes) {
    if (!id.startsWith('corridor:')) continue
    const armMats = group.userData.armMaterials as THREE.MeshStandardMaterial[] | undefined
    const armKeys = group.userData.armNeighborKeys as string[] | undefined
    if (!armMats || !armKeys) continue
    const cq = group.userData.hexQ as number
    const cr = group.userData.hexR as number
    let maxHeat = 0
    for (let i = 0; i < armMats.length; i++) {
      const heat = heatMap.get(`${cq},${cr}>${armKeys[i]}`) || 0
      if (heat > maxHeat) maxHeat = heat
      if (heat > 0) {
        const col = heatToThreeColor(heat)
        armMats[i].color.copy(col)
        armMats[i].emissive.copy(col)
        armMats[i].emissiveIntensity = 0.15 + 0.35 * heat
      } else {
        armMats[i].color.set(0x1a2d4a)
        armMats[i].emissive.set(0x38bdf8)
        armMats[i].emissiveIntensity = 0.15
      }
    }
    const jMat = group.userData.junctionMat as THREE.MeshStandardMaterial | undefined
    if (jMat) {
      if (maxHeat > 0) {
        const col = heatToThreeColor(maxHeat)
        jMat.color.copy(col)
        jMat.emissive.copy(col)
      } else {
        jMat.color.set(0x1a2d4a)
        jMat.emissive.set(0x38bdf8)
      }
    }
  }
}

function syncAgentHeat() {
  const dirHeatMap = agentDirHeat3d.value
  for (const [id, group] of hexMeshes) {
    const heatEdgeLines = group.userData.heatEdgeLines as THREE.Line[] | undefined
    const heatEdgeMats = group.userData.heatEdgeMats as THREE.LineBasicMaterial[] | undefined
    if (!heatEdgeLines || !heatEdgeMats) continue
    const hq = group.userData.hexQ as number
    const hr = group.userData.hexR as number
    const dirHeats = dirHeatMap.get(`${hq},${hr}`)
    for (let i = 0; i < 6; i++) {
      const edgeIdx = (1 - i + 6) % 6
      const heat = dirHeats ? dirHeats[i] : 0
      if (heat > 0) {
        const col = heatToThreeColor(heat)
        heatEdgeMats[edgeIdx].color.copy(col)
        heatEdgeMats[edgeIdx].opacity = 0.4 + 0.6 * heat
        heatEdgeLines[edgeIdx].visible = true
      } else {
        heatEdgeLines[edgeIdx].visible = false
      }
    }
  }
}

watch(() => props.messageFlowStats, () => {
  syncCorridorHeat()
  syncAgentHeat()
}, { deep: true })

// ── Flow animation (3D particles) ──────────────────────
const storeNodes3d = computed(() => (props.topologyNodes || []) as TopologyNode[])
const storeEdges3d = computed(() => props.topologyEdges || [] as TopologyEdge[])
const { findPath: findPath3d, findReachableEndpoints: findEndpoints3d } = useTopologyBFS(storeNodes3d, storeEdges3d)

const flowGroup = new THREE.Group()
flowGroup.name = 'flowParticles'
scene.add(flowGroup)
const FLOW_SPHERE_GEO = new THREE.SphereGeometry(0.05, 8, 8)
const FLOW_DURATION_MS = 700
const MAX_FLOW = 10

interface Flow3D {
  mesh: THREE.Mesh
  material: THREE.MeshStandardMaterial
  path: THREE.Vector3[]
  startTime: number
  targetHexKey: string
}

const activeFlows: Flow3D[] = []

function triggerMessageFlow(sourceInstanceId: string, target: string) {
  const nodes = props.topologyNodes || []
  const sourceNode = nodes.find(n => n.entity_id === sourceInstanceId)
  if (!sourceNode) return

  if (target.startsWith('agent:')) {
    const targetName = target.slice(6)
    const targetNode = nodes.find(n => n.node_type === 'agent' && n.display_name?.toLowerCase() === targetName.toLowerCase())
    if (targetNode) spawnFlowParticle(sourceNode, targetNode)
  } else if (target.startsWith('human:')) {
    const targetId = target.slice(6)
    const targetNode = nodes.find(n => n.node_type === 'human' && n.entity_id === targetId)
    if (targetNode) spawnFlowParticle(sourceNode, targetNode)
  } else if (target === 'broadcast') {
    const endpoints = findEndpoints3d(sourceNode.hex_q, sourceNode.hex_r)
    for (const ep of endpoints) {
      const targetNode = nodes.find(n => n.hex_q === ep.q && n.hex_r === ep.r)
      if (targetNode) spawnFlowParticle(sourceNode, targetNode)
    }
  }
}

function spawnFlowParticle(source: TopologyNode, target: TopologyNode) {
  if (activeFlows.length >= MAX_FLOW) return
  const hexPath = findPath3d(source.hex_q, source.hex_r, target.hex_q, target.hex_r)
  if (!hexPath || hexPath.length < 2) return

  const path3d = hexPath.map(h => {
    const w = axialToWorld(h.q, h.r)
    return new THREE.Vector3(w.x, 0.15, w.y)
  })

  const material = new THREE.MeshStandardMaterial({
    color: 0xa78bfa,
    emissive: 0xa78bfa,
    emissiveIntensity: 0.8,
    transparent: true,
    opacity: 1,
  })
  const mesh = new THREE.Mesh(FLOW_SPHERE_GEO, material)
  mesh.position.copy(path3d[0])
  flowGroup.add(mesh)

  activeFlows.push({
    mesh, material, path: path3d,
    startTime: performance.now(),
    targetHexKey: `${target.hex_q},${target.hex_r}`,
  })
}

// Hover + selection animation
const clock = new THREE.Clock()
addToLoop(() => {
  const t = clock.getElapsedTime()
  for (const [id, group] of hexMeshes) {
    if (id === '__blackboard__') {
      const isHovered = hoveredId.value === '__blackboard__'
      const isSelectedHex = props.selectedHex?.q === 0 && props.selectedHex?.r === 0
      const targetY = isHovered ? 0.4 : isSelectedHex ? 0.3 : 0.15
      group.position.y += (targetY - group.position.y) * 0.1

      const mesh = group.children[0] as THREE.Mesh
      if (mesh?.material && 'emissiveIntensity' in mesh.material) {
        const mat = mesh.material as THREE.MeshStandardMaterial
        mat.emissiveIntensity = isSelectedHex ? 0.7 + Math.sin(t * 3) * 0.15 : isHovered ? 0.5 : 0.2
      }
      continue
    }

    if (id.startsWith('empty:')) {
      const mesh = group.children[0] as THREE.Mesh
      if (!mesh?.material) continue
      const mat = mesh.material as THREE.MeshStandardMaterial
      const isHovered = hoveredId.value === id
      const [, qs, rs] = id.split(':')
      const isSelectedHex = props.selectedHex?.q === Number(qs) && props.selectedHex?.r === Number(rs)
      if (props.isMovingHex) {
        mat.opacity = isHovered ? 0.45 : 0.15
        mat.emissive = new THREE.Color(0x4ade80)
        mat.emissiveIntensity = isHovered ? 0.6 : 0.15 + Math.sin(t * 2) * 0.05
      } else {
        mat.opacity = isSelectedHex ? 0.35 : isHovered ? 0.15 : 0.0
        mat.emissive = isSelectedHex ? new THREE.Color(0x60a5fa) : new THREE.Color(0x4ac8e8)
        mat.emissiveIntensity = isSelectedHex ? 0.6 + Math.sin(t * 3) * 0.15 : isHovered ? 0.3 : 0
      }
      continue
    }

    if (id.startsWith('corridor:')) {
      const armMats = group.userData.armMaterials as THREE.MeshStandardMaterial[] | undefined
      const junctionMat = group.userData.junctionMat as THREE.MeshStandardMaterial | undefined
      if (!armMats) continue
      const isHovered = hoveredId.value === id
      const isSelectedHex = props.selectedHex?.q === group.userData.hexQ && props.selectedHex?.r === group.userData.hexR
      const targetY = isHovered ? 0.04 : isSelectedHex ? 0.03 : 0.02
      group.position.y += (targetY - group.position.y) * 0.1
      const extraIntensity = isSelectedHex ? 0.2 + Math.sin(t * 3) * 0.1 : isHovered ? 0.1 : 0
      for (const am of armMats) {
        am.emissiveIntensity += extraIntensity
        am.opacity = isSelectedHex ? 0.9 : isHovered ? 0.85 : 0.7
      }
      if (junctionMat) {
        junctionMat.emissiveIntensity = isSelectedHex ? 0.4 + Math.sin(t * 3) * 0.1 : isHovered ? 0.3 : 0.2
        junctionMat.opacity = isSelectedHex ? 0.95 : isHovered ? 0.9 : 0.8
      }
      continue
    }

    if (id.startsWith('human:')) {
      const mesh = group.children[0] as THREE.Mesh
      if (!mesh?.material) continue
      const mat = mesh.material as THREE.MeshStandardMaterial
      mat.emissive.set(group.userData.displayColor || '#f59e0b')
      continue
    }

    if (id.startsWith('device:')) {
      const mesh = group.children[0] as THREE.Mesh
      if (!mesh?.material) continue
      const mat = mesh.material as THREE.MeshStandardMaterial
      const isHovered = hoveredId.value === id
      const isSelectedHex = props.selectedHex?.q === group.userData.hexQ && props.selectedHex?.r === group.userData.hexR
      const targetY = isHovered ? 0.34 : isSelectedHex ? 0.3 : 0.22
      group.position.y += (targetY - group.position.y) * 0.1
      mat.emissive.set(group.userData.displayColor || '#14b8a6')
      mat.emissiveIntensity = isSelectedHex ? 0.55 + Math.sin(t * 3) * 0.15 : isHovered ? 0.45 : 0.28
      continue
    }

    const isHovered = hoveredId.value === id
    const isSelected = props.selectedAgentId === id
    const isSelectedHex = props.selectedHex?.q !== undefined &&
      props.agents.some((a) => a.instance_id === id && a.hex_q === props.selectedHex!.q && a.hex_r === props.selectedHex!.r)

    const isMoveSource = props.isMovingHex && props.movingHexSource &&
      props.agents.some((a) => a.instance_id === id && a.hex_q === props.movingHexSource!.q && a.hex_r === props.movingHexSource!.r)

    const targetY = isHovered ? 0.20 : (isSelected || isSelectedHex || isMoveSource) ? 0.14 : 0.04
    group.position.y += (targetY - group.position.y) * 0.1

    const mesh = group.children[0] as THREE.Mesh
    if (mesh?.material && 'emissiveIntensity' in mesh.material) {
      const mat = mesh.material as THREE.MeshStandardMaterial
      const pulse = Math.sin(t * 2) * 0.1 + 0.15
      if (isMoveSource) {
        mat.emissive.set(0xf59e0b)
        mat.emissiveIntensity = 0.5 + Math.sin(t * 4) * 0.25
      } else {
        const agent = props.agents.find(a => a.instance_id === id)
        if (agent) {
          const baseColor = getAgentBaseColor(agent)
          mat.color.set(agent.sse_connected ? baseColor : DISCONNECTED_COLOR)
          mat.emissive.set(agent.sse_connected ? baseColor : DISCONNECTED_COLOR)
          mat.opacity = agent.sse_connected ? 0.9 : 0.5
        }
        mat.emissiveIntensity = (isSelected || isSelectedHex) ? 0.5 + Math.sin(t * 3) * 0.15 : isHovered ? 0.4 : pulse
      }
    }

    const robot = group.userData.robot as THREE.Group | undefined
    const phone = group.userData.phone as THREE.Group | undefined
    if (robot || phone) {
      const agent = props.agents.find(a => a.instance_id === id)
      if (agent) {
        if (robot) {
          animateGrabby(robot, agent.status, agent.sse_connected, t)
          const newTheme = agent.theme_color ?? null
          if (robot.userData.lastBodyTheme !== newTheme) {
            if (newTheme) updateGrabbyTheme(robot, parseInt(newTheme.replace('#', ''), 16))
            robot.userData.lastBodyTheme = newTheme
          }
        }
        if (phone) phone.visible = agent.sse_connected
      }
    }
  }

  if (props.isMovingHex && props.movingHexSource) {
    const src = props.movingHexSource
    for (const [id, group] of hexMeshes) {
      if (!id.startsWith('corridor:') && !id.startsWith('human:') && !id.startsWith('device:')) continue
      const hq = group.userData.hexQ ?? (group.userData as Record<string, unknown>).hexQ
      const hr = group.userData.hexR ?? (group.userData as Record<string, unknown>).hexR
      if (hq === src.q && hr === src.r) {
        const mesh = group.children[0] as THREE.Mesh
        if (mesh?.material && 'emissiveIntensity' in mesh.material) {
          const mat = mesh.material as THREE.MeshStandardMaterial
          mat.emissive = new THREE.Color(group.userData.displayColor || '#f59e0b')
          mat.emissiveIntensity = 0.5 + Math.sin(t * 4) * 0.25
        }
      }
    }
  }

  for (const sprite of labelSprites) {
    sprite.getWorldPosition(_tmpWorldPos)
    const dist = camera.position.distanceTo(_tmpWorldPos)
    const scaleFactor = Math.max(1, dist / LABEL_REF_DISTANCE)
    const base = sprite.userData.baseScale as { x: number; y: number }
    sprite.scale.set(base.x * scaleFactor, base.y * scaleFactor, 1)
  }

  const now = performance.now()
  for (let i = activeFlows.length - 1; i >= 0; i--) {
    const flow = activeFlows[i]
    const elapsed = now - flow.startTime
    const progress = Math.min(1, elapsed / FLOW_DURATION_MS)

    if (progress >= 1) {
      flowGroup.remove(flow.mesh)
      flow.material.dispose()
      activeFlows.splice(i, 1)
      continue
    }

    const totalSegs = flow.path.length - 1
    const segProgress = progress * totalSegs
    const segIdx = Math.min(Math.floor(segProgress), totalSegs - 1)
    const segT = segProgress - segIdx
    flow.mesh.position.lerpVectors(flow.path[segIdx], flow.path[segIdx + 1], segT)
    flow.material.opacity = 1 - progress * 0.5
  }
})

onUnmounted(() => {
  HEX_GEO.dispose()
  AGENT_BASE_GEO.dispose()
  AGENT_BASE_EDGE_GEO.dispose()
  EMPTY_HEX_GEO.dispose()
  HUMAN_HEX_GEO.dispose()
  DEVICE_HEX_GEO.dispose()
  FLOW_SPHERE_GEO.dispose()
  for (const flow of activeFlows) {
    flowGroup.remove(flow.mesh)
    flow.material.dispose()
  }
  activeFlows.length = 0
  disposeGrabbyShared()
  disposeCorridorPathShared()
})

defineExpose({
  zoomIn: () => orbitControls.zoomIn(),
  zoomOut: () => orbitControls.zoomOut(),
  resetView: () => orbitControls.resetView(),
  panBy: (dx: number, dy: number) => orbitControls.panBy(dx, dy),
  focusOnPosition: (x: number, z: number) => orbitControls.focusOnPosition(x, z),
  getCameraXZDirections: () => orbitControls.getCameraXZDirections(),
  triggerMessageFlow,
})
</script>

<template>
  <div ref="containerRef" class="w-full h-full" />
</template>
