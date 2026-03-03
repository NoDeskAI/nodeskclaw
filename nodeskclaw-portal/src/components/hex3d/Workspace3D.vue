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
import type { AgentBrief, TopologyNode, TopologyEdge, MessageFlowPair } from '@/stores/workspace'

const { t } = useI18n()

type HexType = 'empty' | 'agent' | 'blackboard' | 'human' | 'corridor'

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
}>()

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
  } else {
    const agent = props.agents.find((a) => a.instance_id === id)
    if (agent) emit('hex-click', { q: agent.hex_q, r: agent.hex_r, type: 'agent', agentId: id })
  }
})
watch(dblclickId, (id) => {
  if (id && !id.startsWith('__') && !id.startsWith('empty:')) emit('agent-dblclick', id)
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

const heatmapGroup = new THREE.Group()
heatmapGroup.name = 'heatmapLines'
scene.add(heatmapGroup)

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

function createHexMesh(agent: AgentBrief): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(agent.hex_q, agent.hex_r)
  group.position.set(x, 0.04, y)
  group.userData = { hexId: agent.instance_id, isHex: true, sseConnected: agent.sse_connected }

  const baseColor = STATUS_COLORS_3D[agent.status] ?? 0xa78bfa
  const color = agent.sse_connected ? baseColor : DISCONNECTED_COLOR
  const bodyTheme = agent.theme_color
    ? parseInt(agent.theme_color.replace('#', ''), 16)
    : undefined

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

  const robot = createGrabby(bodyTheme)
  robot.position.y = 0.04
  group.add(robot)
  group.userData.robot = robot

  const phone = createPhoneStation(color)
  phone.position.set(0.45, 0.02, 0.35)
  phone.rotation.y = -Math.PI / 6
  phone.visible = agent.sse_connected
  group.add(phone)
  group.userData.phone = phone

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

function createBBLabelSprite(): THREE.Sprite {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 40
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = 'transparent'
  ctx.fillRect(0, 0, 256, 40)
  ctx.font = 'bold 20px sans-serif'
  ctx.fillStyle = '#a78bfa'
  ctx.textAlign = 'center'
  ctx.fillText(t('workspaceView.bbTitle'), 128, 28)
  const texture = new THREE.CanvasTexture(canvas)
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true })
  const sprite = new THREE.Sprite(mat)
  sprite.scale.set(1.2, 0.2, 1)
  sprite.userData.baseScale = { x: 1.2, y: 0.2 }
  return sprite
}

const HUMAN_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.7, HEX_SIZE * 0.7, 0.5, 6)

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

  for (const agent of props.agents) {
    const group = createHexMesh(agent)
    const agentName = agent.display_name || agent.name
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

const heatmapMaterials: THREE.LineBasicMaterial[] = []

function syncHeatmap() {
  for (const child of [...heatmapGroup.children]) {
    heatmapGroup.remove(child)
    if ((child as THREE.Line).geometry) (child as THREE.Line).geometry.dispose()
  }
  for (const mat of heatmapMaterials) mat.dispose()
  heatmapMaterials.length = 0

  const stats = props.messageFlowStats
  if (!stats || stats.length === 0) return
  const maxCount = Math.max(...stats.map(s => s.count))
  if (maxCount === 0) return

  for (const s of stats) {
    const [sq, sr] = s.sender_hex_key.split(',').map(Number)
    const [rq, rr] = s.receiver_hex_key.split(',').map(Number)
    const from = axialToWorld(sq, sr)
    const to = axialToWorld(rq, rr)
    const ratio = s.count / maxCount
    const geo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(from.x, 0.01, from.y),
      new THREE.Vector3(to.x, 0.01, to.y),
    ])
    const mat = new THREE.LineBasicMaterial({
      color: 0xa78bfa,
      transparent: true,
      opacity: 0.15 + 0.45 * ratio,
    })
    heatmapMaterials.push(mat)
    heatmapGroup.add(new THREE.Line(geo, mat))
  }
}

watch(() => props.messageFlowStats, syncHeatmap, { deep: true })

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
      const railMat = group.userData.railMat as THREE.MeshStandardMaterial | undefined
      const junctionMat = group.userData.junctionMat as THREE.MeshStandardMaterial | undefined
      if (!railMat) continue
      const isHovered = hoveredId.value === id
      const isSelectedHex = props.selectedHex?.q === group.userData.hexQ && props.selectedHex?.r === group.userData.hexR
      const targetY = isHovered ? 0.04 : isSelectedHex ? 0.03 : 0.02
      group.position.y += (targetY - group.position.y) * 0.1
      railMat.emissiveIntensity = isSelectedHex ? 0.35 + Math.sin(t * 3) * 0.1 : isHovered ? 0.25 : 0.15
      railMat.opacity = isSelectedHex ? 0.9 : isHovered ? 0.85 : 0.7
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
          const baseColor = STATUS_COLORS_3D[agent.status] ?? 0xa78bfa
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
      if (!id.startsWith('corridor:') && !id.startsWith('human:')) continue
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
  FLOW_SPHERE_GEO.dispose()
  for (const flow of activeFlows) {
    flowGroup.remove(flow.mesh)
    flow.material.dispose()
  }
  activeFlows.length = 0
  for (const mat of heatmapMaterials) mat.dispose()
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
