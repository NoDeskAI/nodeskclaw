<script setup lang="ts">
import { ref, watch, onUnmounted, computed } from 'vue'
import * as THREE from 'three'
import { useThreeScene } from '@/composables/useThreeScene'
import { useOrbitControls } from '@/composables/useOrbitControls'
import { useHexRaycaster } from '@/composables/useHexRaycaster'
import { axialToWorld, HEX_SIZE } from '@/composables/useHexLayout'
import AgentHex3D from './AgentHex3D.vue'
import Blackboard3D from './Blackboard3D.vue'
import type { AgentBrief } from '@/stores/workspace'

const props = defineProps<{
  agents: AgentBrief[]
  autoSummary: string
  manualNotes: string
}>()

const emit = defineEmits<{
  (e: 'agent-click', id: string): void
  (e: 'agent-hover', id: string | null): void
  (e: 'blackboard-click'): void
  (e: 'add-agent-click'): void
}>()

const containerRef = ref<HTMLElement | null>(null)

const { scene, camera, renderer, addToLoop } = useThreeScene(containerRef, {
  cameraPos: [0, 8, 10],
  fov: 50,
})

const orbitControls = useOrbitControls(camera, renderer)
addToLoop(() => orbitControls.update())

const { hoveredId, selectedId } = useHexRaycaster(scene, camera, containerRef, {
  meshFilter: (obj) => obj.userData?.isHex === true || obj.userData?.hexId != null,
})

watch(hoveredId, (id) => emit('agent-hover', id))
watch(selectedId, (id) => {
  if (id === '__blackboard__') emit('blackboard-click')
  else if (id === '__add_agent__') emit('add-agent-click')
  else if (id) emit('agent-click', id)
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

function createHexMesh(agent: AgentBrief): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(agent.hex_q, agent.hex_r)
  group.position.set(x, 0.15, y)
  group.userData = { hexId: agent.instance_id, isHex: true }

  const statusColors: Record<string, number> = {
    running: 0x4ade80, active: 0x4ade80,
    thinking: 0xfbbf24, pending: 0xfbbf24,
    idle: 0x8b8b9e,
    error: 0xf87171, failed: 0xf87171,
  }
  const color = statusColors[agent.status] ?? 0xa78bfa

  const mat = new THREE.MeshStandardMaterial({
    color,
    emissive: new THREE.Color(color),
    emissiveIntensity: 0.15,
    metalness: 0.2,
    roughness: 0.6,
    transparent: true,
    opacity: 0.9,
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

  const bbSize = HEX_SIZE * 1.1
  const bbGeo = new THREE.CylinderGeometry(bbSize, bbSize, 0.35, 6)
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
  mesh.userData = { hexId: '__blackboard__', isHex: true }
  group.add(mesh)

  const edgeGeo = new THREE.EdgesGeometry(bbGeo)
  const edgeMat = new THREE.LineBasicMaterial({
    color: 0xa78bfa,
    transparent: true,
    opacity: 0.5,
  })
  const edges = new THREE.LineSegments(edgeGeo, edgeMat)
  edges.userData = { hexId: '__blackboard__', isHex: true }
  group.add(edges)

  return group
}

function createAddAgentMesh(q: number, r: number): THREE.Group {
  const group = new THREE.Group()
  const { x, y } = axialToWorld(q, r)
  group.position.set(x, 0.15, y)
  group.userData = { hexId: '__add_agent__', isHex: true }

  const mat = new THREE.MeshStandardMaterial({
    color: 0x333355,
    emissive: new THREE.Color(0x555577),
    emissiveIntensity: 0.1,
    transparent: true,
    opacity: 0.4,
    wireframe: true,
  })
  const mesh = new THREE.Mesh(HEX_GEO, mat)
  mesh.userData = { hexId: '__add_agent__', isHex: true }
  group.add(mesh)

  return group
}

function syncScene() {
  // Clear existing hex meshes
  for (const [id, group] of hexMeshes) {
    scene.remove(group)
  }
  hexMeshes.clear()

  // Add agent hexes
  for (const agent of props.agents) {
    const group = createHexMesh(agent)
    scene.add(group)
    hexMeshes.set(agent.instance_id, group)
  }

  // Add blackboard at center
  const bbGroup = createBlackboardMesh()
  scene.add(bbGroup)
  hexMeshes.set('__blackboard__', bbGroup)

  // Add agent placeholder
  const nextIdx = props.agents.length
  const directions: [number, number][] = [[0, -1], [-1, 0], [-1, 1], [0, 1], [1, 0], [1, -1]]
  let pq = 1, pr = 0, ring = 1
  const allPositions: [number, number][] = []
  while (allPositions.length <= nextIdx) {
    for (const [dq, dr] of directions) {
      for (let s = 0; s < ring && allPositions.length <= nextIdx; s++) {
        allPositions.push([pq, pr])
        pq += dq; pr += dr
      }
    }
    ring++; pq++
  }
  if (allPositions.length > nextIdx) {
    const [aq, ar] = allPositions[nextIdx]
    const addGroup = createAddAgentMesh(aq, ar)
    scene.add(addGroup)
    hexMeshes.set('__add_agent__', addGroup)
  }
}

watch(() => props.agents, syncScene, { deep: true, immediate: true })

// Hover animation
const clock = new THREE.Clock()
addToLoop(() => {
  const t = clock.getElapsedTime()
  for (const [id, group] of hexMeshes) {
    if (id.startsWith('__')) continue
    const isHovered = hoveredId.value === id
    const targetY = isHovered ? 0.4 : 0.15
    group.position.y += (targetY - group.position.y) * 0.1

    const mesh = group.children[0] as THREE.Mesh
    if (mesh?.material && 'emissiveIntensity' in mesh.material) {
      const mat = mesh.material as THREE.MeshStandardMaterial
      const pulse = Math.sin(t * 2) * 0.1 + 0.15
      mat.emissiveIntensity = isHovered ? 0.4 : pulse
    }
  }
})

onUnmounted(() => {
  HEX_GEO.dispose()
})

defineExpose({
  zoomIn: () => orbitControls.zoomIn(),
  zoomOut: () => orbitControls.zoomOut(),
  resetView: () => orbitControls.resetView(),
})
</script>

<template>
  <div ref="containerRef" class="w-full h-full" />
</template>
