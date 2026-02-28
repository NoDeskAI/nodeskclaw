<script setup lang="ts">
import { ref, watch, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import * as THREE from 'three'
import { useThreeScene } from '@/composables/useThreeScene'
import { useOrbitControls } from '@/composables/useOrbitControls'
import { useHexRaycaster } from '@/composables/useHexRaycaster'
import { axialToWorld, HEX_SIZE } from '@/composables/useHexLayout'
import AgentHex3D from './AgentHex3D.vue'
import Blackboard3D from './Blackboard3D.vue'
import type { AgentBrief, TopologyNode } from '@/stores/workspace'

const { t } = useI18n()

type HexType = 'empty' | 'agent' | 'blackboard' | 'human' | 'corridor'

const props = defineProps<{
  agents: AgentBrief[]
  blackboardContent: string
  selectedAgentId: string | null
  selectedHex: { q: number, r: number } | null
  topologyNodes?: TopologyNode[]
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

scene.fog = new THREE.FogExp2(0x0a0a1a, 0.04)
scene.background = new THREE.Color(0x0a0a1a)

// Hex meshes management
const hexMeshes = new Map<string, THREE.Group>()
const labelSprites = new Set<THREE.Sprite>()
const LABEL_REF_DISTANCE = 12
const _tmpWorldPos = new THREE.Vector3()

const HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.9, HEX_SIZE * 0.9, 0.3, 6)

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
  group.position.set(x, 0.15, y)
  group.userData = { hexId: agent.instance_id, isHex: true, sseConnected: agent.sse_connected }

  const baseColor = STATUS_COLORS_3D[agent.status] ?? 0xa78bfa
  const color = agent.sse_connected ? baseColor : DISCONNECTED_COLOR

  const mat = new THREE.MeshStandardMaterial({
    color,
    emissive: new THREE.Color(color),
    emissiveIntensity: agent.sse_connected ? 0.15 : 0.05,
    metalness: 0.2,
    roughness: 0.6,
    transparent: true,
    opacity: agent.sse_connected ? 0.9 : 0.5,
  })

  const mesh = new THREE.Mesh(HEX_GEO, mat)
  mesh.userData = { hexId: agent.instance_id, isHex: true }
  group.add(mesh)

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

const CORRIDOR_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.88, HEX_SIZE * 0.88, 0.03, 6)
const HUMAN_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.7, HEX_SIZE * 0.7, 0.5, 6)

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

function createCorridorHexMesh(node: TopologyNode): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(node.hex_q, node.hex_r)
  group.position.set(x, 0.02, y)
  const hexId = `corridor:${node.entity_id}`
  group.userData = { hexId, isHex: true, hexQ: node.hex_q, hexR: node.hex_r }

  const mat = new THREE.MeshStandardMaterial({
    color: 0x1a2d4a,
    emissive: new THREE.Color(0x38bdf8),
    emissiveIntensity: 0.08,
    metalness: 0.3,
    roughness: 0.7,
    transparent: true,
    opacity: 0.6,
  })
  const tile = new THREE.Mesh(CORRIDOR_HEX_GEO, mat)
  tile.userData = { hexId, isHex: true }
  group.add(tile)

  const edgeGeo = new THREE.EdgesGeometry(CORRIDOR_HEX_GEO)
  const edgeMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.35 })
  group.add(new THREE.LineSegments(edgeGeo, edgeMat))

  if (node.display_name) {
    const label = createCorridorLabelSprite(node.display_name)
    label.position.set(0, 0.2, 0)
    group.add(label)
    labelSprites.add(label)
  }

  return group
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
  for (const [, group] of hexMeshes) {
    scene.remove(group)
  }
  hexMeshes.clear()
  labelSprites.clear()

  for (const agent of props.agents) {
    const group = createHexMesh(agent)
    scene.add(group)
    hexMeshes.set(agent.instance_id, group)
  }

  const bbGroup = createBlackboardMesh()
  scene.add(bbGroup)
  hexMeshes.set('__blackboard__', bbGroup)

  const corridorNodes = (props.topologyNodes || []).filter(n => n.node_type === 'corridor')
  for (const node of corridorNodes) {
    const group = createCorridorHexMesh(node)
    scene.add(group)
    hexMeshes.set(`corridor:${node.entity_id}`, group)
  }

  const humanNodes = (props.topologyNodes || []).filter(n => n.node_type === 'human')
  for (const node of humanNodes) {
    const group = createHumanHexMesh(node)
    scene.add(group)
    hexMeshes.set(`human:${node.entity_id}`, group)
  }

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
      const mesh = group.children[0] as THREE.Mesh
      if (!mesh?.material) continue
      const mat = mesh.material as THREE.MeshStandardMaterial
      const isHovered = hoveredId.value === id
      const isSelectedHex = props.selectedHex?.q === group.userData.hexQ && props.selectedHex?.r === group.userData.hexR
      const targetY = isHovered ? 0.04 : isSelectedHex ? 0.03 : 0.02
      group.position.y += (targetY - group.position.y) * 0.1
      mat.emissive.set(0x38bdf8)
      mat.emissiveIntensity = isSelectedHex ? 0.25 + Math.sin(t * 3) * 0.1 : isHovered ? 0.2 : 0.08
      mat.opacity = isSelectedHex ? 0.8 : isHovered ? 0.75 : 0.6
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

    const targetY = isHovered ? 0.4 : (isSelected || isSelectedHex || isMoveSource) ? 0.3 : 0.15
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
})

onUnmounted(() => {
  HEX_GEO.dispose()
  EMPTY_HEX_GEO.dispose()
  CORRIDOR_HEX_GEO.dispose()
  HUMAN_HEX_GEO.dispose()
})

defineExpose({
  zoomIn: () => orbitControls.zoomIn(),
  zoomOut: () => orbitControls.zoomOut(),
  resetView: () => orbitControls.resetView(),
  panBy: (dx: number, dy: number) => orbitControls.panBy(dx, dy),
  focusOnPosition: (x: number, z: number) => orbitControls.focusOnPosition(x, z),
  getCameraXZDirections: () => orbitControls.getCameraXZDirections(),
})
</script>

<template>
  <div ref="containerRef" class="w-full h-full" />
</template>
