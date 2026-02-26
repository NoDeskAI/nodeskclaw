<script setup lang="ts">
import { ref, watch, onUnmounted, computed } from 'vue'
import * as THREE from 'three'
import { useThreeScene } from '@/composables/useThreeScene'
import { useOrbitControls } from '@/composables/useOrbitControls'
import { useHexRaycaster } from '@/composables/useHexRaycaster'
import { axialToWorld, HEX_SIZE } from '@/composables/useHexLayout'
import AgentHex3D from './AgentHex3D.vue'
import Blackboard3D from './Blackboard3D.vue'
import type { AgentBrief, CorridorHexInfo, HexConnectionInfo, HexType } from '@/stores/workspace'

const props = defineProps<{
  agents: AgentBrief[]
  autoSummary: string
  manualNotes: string
  selectedAgentId: string | null
  selectedHex: { q: number, r: number } | null
  corridorHexes?: CorridorHexInfo[]
  connections?: HexConnectionInfo[]
  humanHexes?: Array<{ user_id: string; hex_q: number; hex_r: number; display_name: string; display_color?: string | null }>
}>()

const emit = defineEmits<{
  (e: 'hex-click', payload: { q: number, r: number, type: HexType, agentId?: string; humanUserId?: string; corridorHexId?: string }): void
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
    const ch = props.corridorHexes?.find(c => `corridor:${c.id}` === id)
    if (ch) emit('hex-click', { q: ch.hex_q, r: ch.hex_r, type: 'corridor', corridorHexId: ch.id })
  } else if (id.startsWith('human:')) {
    const userId = id.slice(6)
    const hh = props.humanHexes?.find(h => h.user_id === userId)
    if (hh) emit('hex-click', { q: hh.hex_q, r: hh.hex_r, type: 'human', humanUserId: userId })
  } else {
    const agent = props.agents.find((a) => a.instance_id === id)
    if (agent) emit('hex-click', { q: agent.hex_q, r: agent.hex_r, type: 'agent', agentId: id })
  }
})
watch(dblclickId, (id) => {
  if (id && !id.startsWith('__') && !id.startsWith('empty:') && !id.startsWith('corridor:') && !id.startsWith('human:')) emit('agent-dblclick', id)
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

  return group
}

const CORRIDOR_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.85, HEX_SIZE * 0.85, 0.2, 6)
const HUMAN_HEX_GEO = new THREE.CylinderGeometry(HEX_SIZE * 0.7, HEX_SIZE * 0.7, 0.5, 6)
const HUMAN_DEFAULT_COLOR = 0xf59e0b

function createCorridorHexMesh(ch: CorridorHexInfo): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(ch.hex_q, ch.hex_r)
  group.position.set(x, 0.1, y)
  const hexId = `corridor:${ch.id}`
  group.userData = { hexId, isHex: true }

  const mat = new THREE.MeshStandardMaterial({
    color: 0x38bdf8,
    emissive: new THREE.Color(0x38bdf8),
    emissiveIntensity: 0.1,
    metalness: 0.1,
    roughness: 0.7,
    transparent: true,
    opacity: 0.4,
  })
  const mesh = new THREE.Mesh(CORRIDOR_HEX_GEO, mat)
  mesh.userData = { hexId, isHex: true }
  group.add(mesh)

  return group
}

function createHumanHexMesh(hh: { user_id: string; hex_q: number; hex_r: number; display_color?: string | null }): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(hh.hex_q, hh.hex_r)
  group.position.set(x, 0.25, y)
  const hexId = `human:${hh.user_id}`
  group.userData = { hexId, isHex: true }

  const color = hh.display_color ? parseInt(hh.display_color.replace('#', ''), 16) : HUMAN_DEFAULT_COLOR

  const mat = new THREE.MeshStandardMaterial({
    color,
    emissive: new THREE.Color(color),
    emissiveIntensity: 0.2,
    metalness: 0.2,
    roughness: 0.5,
    transparent: true,
    opacity: 0.9,
  })
  const mesh = new THREE.Mesh(HUMAN_HEX_GEO, mat)
  mesh.userData = { hexId, isHex: true }
  group.add(mesh)

  return group
}

const connectionLines = new THREE.Group()
scene.add(connectionLines)

function syncConnectionLines() {
  while (connectionLines.children.length > 0) {
    const child = connectionLines.children[0]
    connectionLines.remove(child)
    if (child instanceof THREE.Line) {
      child.geometry.dispose()
      if (child.material instanceof THREE.Material) child.material.dispose()
    }
  }

  for (const conn of (props.connections || [])) {
    const from = axialToWorld(conn.hex_a_q, conn.hex_a_r)
    const to = axialToWorld(conn.hex_b_q, conn.hex_b_r)

    const points = [
      new THREE.Vector3(from.x, 0.3, from.y),
      new THREE.Vector3(to.x, 0.3, to.y),
    ]
    const geo = new THREE.BufferGeometry().setFromPoints(points)
    const mat = new THREE.LineBasicMaterial({
      color: conn.direction === 'both' ? 0x60a5fa : 0xfbbf24,
      transparent: true,
      opacity: 0.6,
    })
    const line = new THREE.Line(geo, mat)
    connectionLines.add(line)
  }
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

  for (const agent of props.agents) {
    const group = createHexMesh(agent)
    scene.add(group)
    hexMeshes.set(agent.instance_id, group)
  }

  const bbGroup = createBlackboardMesh()
  scene.add(bbGroup)
  hexMeshes.set('__blackboard__', bbGroup)

  for (const ch of (props.corridorHexes || [])) {
    const group = createCorridorHexMesh(ch)
    scene.add(group)
    hexMeshes.set(`corridor:${ch.id}`, group)
  }

  for (const hh of (props.humanHexes || [])) {
    const group = createHumanHexMesh(hh)
    scene.add(group)
    hexMeshes.set(`human:${hh.user_id}`, group)
  }

  const occupied = new Set<string>()
  occupied.add('0:0')
  for (const agent of props.agents) {
    occupied.add(`${agent.hex_q}:${agent.hex_r}`)
  }
  for (const ch of (props.corridorHexes || [])) {
    occupied.add(`${ch.hex_q}:${ch.hex_r}`)
  }
  for (const hh of (props.humanHexes || [])) {
    occupied.add(`${hh.hex_q}:${hh.hex_r}`)
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

  syncConnectionLines()
}

watch(
  () => [props.agents, props.corridorHexes, props.humanHexes, props.connections],
  syncScene,
  { deep: true, immediate: true },
)

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
      mat.opacity = isSelectedHex ? 0.35 : isHovered ? 0.15 : 0.0
      mat.emissive = isSelectedHex ? new THREE.Color(0x60a5fa) : new THREE.Color(0x4ac8e8)
      mat.emissiveIntensity = isSelectedHex ? 0.6 + Math.sin(t * 3) * 0.15 : isHovered ? 0.3 : 0
      continue
    }

    if (id.startsWith('corridor:') || id.startsWith('human:')) {
      const isHovered = hoveredId.value === id
      const targetY = id.startsWith('corridor:') ? (isHovered ? 0.25 : 0.1) : (isHovered ? 0.45 : 0.25)
      group.position.y += (targetY - group.position.y) * 0.1

      const mesh = group.children[0] as THREE.Mesh
      if (mesh?.material && 'emissiveIntensity' in mesh.material) {
        const mat = mesh.material as THREE.MeshStandardMaterial
        mat.emissiveIntensity = isHovered ? 0.4 : 0.2
      }
      continue
    }

    const isHovered = hoveredId.value === id
    const isSelected = props.selectedAgentId === id
    const isSelectedHex = props.selectedHex?.q !== undefined &&
      props.agents.some((a) => a.instance_id === id && a.hex_q === props.selectedHex!.q && a.hex_r === props.selectedHex!.r)
    const targetY = isHovered ? 0.4 : (isSelected || isSelectedHex) ? 0.3 : 0.15
    group.position.y += (targetY - group.position.y) * 0.1

    const mesh = group.children[0] as THREE.Mesh
    if (mesh?.material && 'emissiveIntensity' in mesh.material) {
      const mat = mesh.material as THREE.MeshStandardMaterial
      const pulse = Math.sin(t * 2) * 0.1 + 0.15
      mat.emissiveIntensity = (isSelected || isSelectedHex) ? 0.5 + Math.sin(t * 3) * 0.15 : isHovered ? 0.4 : pulse
    }
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
