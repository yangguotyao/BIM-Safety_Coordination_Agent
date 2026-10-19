<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import type { MeshData } from '../types'

const props = withDefaults(
  defineProps<{
    meshes: MeshData[]
    targetGuid?: string
    riskGuids?: string[]
    selectedGuid?: string
    evidencePoint?: number[] | null
    evidenceLabel?: string
  }>(),
  {
    targetGuid: '',
    riskGuids: () => [],
    selectedGuid: '',
    evidencePoint: null,
    evidenceLabel: '',
  },
)

const emit = defineEmits<{ select: [guid: string] }>()

const host = ref<HTMLDivElement | null>(null)
const failed = ref('')
const ready = ref(false)

let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let controls: OrbitControls | null = null
let modelGroup: THREE.Group | null = null
let meshMap = new Map<string, THREE.Mesh>()
let raycaster: THREE.Raycaster | null = null
let pointer = new THREE.Vector2()
let downX = 0
let downY = 0
let frame = 0
let resizeObserver: ResizeObserver | null = null
let selectionBox: THREE.Box3Helper | null = null
let evidenceGroup: THREE.Group | null = null
let centerIfc = new THREE.Vector3()
let sceneRadius = 10
let disposed = false
let hovered: THREE.Mesh | null = null

function toThree(point: number[]): THREE.Vector3 {
  return new THREE.Vector3(point[0] - centerIfc.x, point[2] - centerIfc.z, -(point[1] - centerIfc.y))
}

function materialFor(mesh: MeshData): THREE.MeshStandardMaterial {
  const isTarget = mesh.guid === props.targetGuid
  const isSlab = mesh.ifc_class === 'IfcSlab'
  const base = isTarget ? 0x0e7490 : isSlab ? 0x1e5f7a : 0x2b4058
  const emissive = isTarget ? 0x0f766e : 0x06121f
  return new THREE.MeshStandardMaterial({
    color: base,
    emissive,
    emissiveIntensity: isTarget ? 0.4 : 0.08,
    metalness: 0.16,
    roughness: isSlab ? 0.54 : 0.76,
    side: THREE.DoubleSide,
    transparent: false,
  })
}

function makeObject(mesh: MeshData): THREE.Mesh {
  const geometry = new THREE.BufferGeometry()
  const positions = new Float32Array(mesh.vertices.length * 3)
  mesh.vertices.forEach((vertex, index) => {
    const point = toThree(vertex)
    positions[index * 3] = point.x
    positions[index * 3 + 1] = point.y
    positions[index * 3 + 2] = point.z
  })
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  const indices = mesh.triangles.flat()
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  const object = new THREE.Mesh(geometry, materialFor(mesh))
  object.userData.guid = mesh.guid
  object.userData.ifcClass = mesh.ifc_class
  object.userData.name = mesh.name
  object.castShadow = false
  object.receiveShadow = true
  if (mesh.guid === props.targetGuid) {
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry, 28),
      new THREE.LineBasicMaterial({ color: 0x67e8f9, transparent: true, opacity: 0.55 }),
    )
    edges.userData.isTargetEdge = true
    object.add(edges)
  }
  return object
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    if (child instanceof THREE.Mesh || child instanceof THREE.LineSegments) {
      child.geometry.dispose()
      const material = child.material
      if (Array.isArray(material)) material.forEach((item) => item.dispose())
      else material.dispose()
    }
  })
}

function clearModel() {
  if (!scene || !modelGroup) return
  scene.remove(modelGroup)
  disposeObject(modelGroup)
  meshMap.clear()
  modelGroup = new THREE.Group()
  scene.add(modelGroup)
}

function rebuild() {
  if (!scene || !modelGroup) return
  clearModel()
  const all = props.meshes
  if (!all.length) {
    ready.value = false
    return
  }
  const min = new THREE.Vector3(Infinity, Infinity, Infinity)
  const max = new THREE.Vector3(-Infinity, -Infinity, -Infinity)
  all.forEach((mesh) => {
    mesh.vertices.forEach((vertex) => {
      min.x = Math.min(min.x, vertex[0])
      min.y = Math.min(min.y, vertex[1])
      min.z = Math.min(min.z, vertex[2])
      max.x = Math.max(max.x, vertex[0])
      max.y = Math.max(max.y, vertex[1])
      max.z = Math.max(max.z, vertex[2])
    })
  })
  centerIfc = new THREE.Vector3((min.x + max.x) / 2, (min.y + max.y) / 2, (min.z + max.z) / 2)
  all.forEach((mesh) => {
    const object = makeObject(mesh)
    modelGroup!.add(object)
    meshMap.set(mesh.guid, object)
  })
  const box = new THREE.Box3().setFromObject(modelGroup)
  const size = box.getSize(new THREE.Vector3())
  sceneRadius = Math.max(size.length(), 8)
  applyRiskState()
  resetView()
  ready.value = true
  if (props.selectedGuid) updateSelection(props.selectedGuid)
  if (props.evidencePoint) updateEvidence(props.evidencePoint)
}

function resetView() {
  if (!scene || !camera || !controls) return
  const radius = sceneRadius * 0.72
  camera.position.set(radius * 0.52, radius * 1.05, radius * 0.72)
  controls.target.set(0, 0.4, 0)
  controls.maxDistance = sceneRadius * 5
  controls.minDistance = 1.2
  controls.update()
}

function focusGuid(guid: string) {
  if (!camera || !controls) return
  const object = meshMap.get(guid)
  if (!object) return
  const box = new THREE.Box3().setFromObject(object)
  const center = box.getCenter(new THREE.Vector3())
  const size = box.getSize(new THREE.Vector3())
  const distance = Math.max(size.length() * 1.7, 4.5)
  const direction = camera.position.clone().sub(controls.target).normalize()
  if (direction.lengthSq() < 0.01) direction.set(0.7, 0.5, 0.8).normalize()
  controls.target.copy(center)
  camera.position.copy(center.clone().add(direction.multiplyScalar(distance)))
  controls.update()
}

function updateSelection(guid: string) {
  if (!scene) return
  if (selectionBox) {
    scene.remove(selectionBox)
    selectionBox.geometry.dispose()
    ;(selectionBox.material as THREE.Material).dispose()
    selectionBox = null
  }
  const object = meshMap.get(guid)
  if (!object) return
  const box = new THREE.Box3().setFromObject(object)
  selectionBox = new THREE.Box3Helper(box, new THREE.Color(0x7dd3fc))
  ;(selectionBox.material as THREE.LineBasicMaterial).transparent = true
  ;(selectionBox.material as THREE.LineBasicMaterial).opacity = 0.85
  scene.add(selectionBox)
}

function clearEvidence() {
  if (evidenceGroup && scene) {
    scene.remove(evidenceGroup)
    disposeObject(evidenceGroup)
    evidenceGroup = null
  }
}

function updateEvidence(point: number[] | null) {
  clearEvidence()
  if (!scene || !point) return
  const position = toThree(point)
  const group = new THREE.Group()
  const sphere = new THREE.Mesh(
    new THREE.SphereGeometry(0.18, 20, 16),
    new THREE.MeshBasicMaterial({ color: 0xfbbf24 }),
  )
  sphere.position.copy(position)
  group.add(sphere)
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.28, 0.38, 32),
    new THREE.MeshBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.7, side: THREE.DoubleSide }),
  )
  ring.position.copy(position)
  ring.rotation.x = -Math.PI / 2
  group.add(ring)
  const lineGeometry = new THREE.BufferGeometry().setFromPoints([
    position.clone(),
    position.clone().add(new THREE.Vector3(0, 1.8, 0)),
  ])
  group.add(new THREE.Line(lineGeometry, new THREE.LineBasicMaterial({ color: 0xfbbf24, transparent: true, opacity: 0.5 })))
  const canvas = document.createElement('canvas')
  canvas.width = 384
  canvas.height = 96
  const context = canvas.getContext('2d')
  if (context) {
    context.fillStyle = 'rgba(8, 18, 31, 0.86)'
    context.roundRect(2, 2, 380, 92, 16)
    context.fill()
    context.strokeStyle = 'rgba(251, 191, 36, 0.75)'
    context.lineWidth = 3
    context.stroke()
    context.fillStyle = '#fbbf24'
    context.font = '600 36px "PingFang SC", sans-serif'
    context.textAlign = 'center'
    context.textBaseline = 'middle'
    context.fillText(props.evidenceLabel || '模拟人员位置', 192, 50)
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: false }))
  sprite.scale.set(2.2, 0.55, 1)
  sprite.position.copy(position).add(new THREE.Vector3(0, 2.15, 0))
  group.add(sprite)
  group.userData.isEvidence = true
  evidenceGroup = group
  scene.add(group)
}

function applyRiskState() {
  const target = props.targetGuid ? meshMap.get(props.targetGuid) : null
  if (!target) return
  const material = target.material as THREE.MeshStandardMaterial
  const atRisk = props.riskGuids.includes(props.targetGuid)
  if (atRisk) {
    material.color.setHex(0x7c2d12)
    material.emissive.setHex(0xea580c)
    material.emissiveIntensity = 0.5
    target.traverse((child) => {
      if (child instanceof THREE.LineSegments && child.userData.isTargetEdge) {
        ;(child.material as THREE.LineBasicMaterial).color.setHex(0xfbbf24)
      }
    })
  } else {
    material.color.setHex(0x0e7490)
    material.emissive.setHex(0x0f766e)
    material.emissiveIntensity = 0.4
    target.traverse((child) => {
      if (child instanceof THREE.LineSegments && child.userData.isTargetEdge) {
        ;(child.material as THREE.LineBasicMaterial).color.setHex(0x67e8f9)
      }
    })
  }
}

function addMesh(mesh: MeshData) {
  if (!modelGroup) return
  const existing = meshMap.get(mesh.guid)
  if (existing) {
    focusGuid(mesh.guid)
    return
  }
  const object = makeObject(mesh)
  modelGroup.add(object)
  meshMap.set(mesh.guid, object)
  if (mesh.guid === props.targetGuid) applyRiskState()
}

function pick(event: PointerEvent) {
  if (!renderer || !camera || !raycaster || !modelGroup) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const hits = raycaster.intersectObjects(modelGroup.children, true)
  for (const hit of hits) {
    let current: THREE.Object3D | null = hit.object
    while (current && !current.userData.guid) current = current.parent
    if (current?.userData.guid) {
      emit('select', current.userData.guid)
      return
    }
  }
}

function onPointerDown(event: PointerEvent) {
  downX = event.clientX
  downY = event.clientY
}

function onPointerUp(event: PointerEvent) {
  if (Math.abs(event.clientX - downX) < 5 && Math.abs(event.clientY - downY) < 5) pick(event)
}

function onPointerMove(event: PointerEvent) {
  if (!renderer || !camera || !raycaster || !modelGroup) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const hits = raycaster.intersectObjects(modelGroup.children, true)
  let nextHover: THREE.Mesh | null = null
  for (const hit of hits) {
    let current: THREE.Object3D | null = hit.object
    while (current && !current.userData.guid) current = current.parent
    if (current instanceof THREE.Mesh) {
      nextHover = current
      break
    }
  }
  if (hovered !== nextHover) {
    hovered = nextHover
    renderer.domElement.style.cursor = hovered ? 'pointer' : 'grab'
  }
}

function init() {
  if (!host.value) return
  try {
    scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0x060d17, 0.009)
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 800)
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.28
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.cursor = 'grab'
    host.value.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xa5d8ff, 0x08111f, 1.15))
    const key = new THREE.DirectionalLight(0xffffff, 2.3)
    key.position.set(18, 30, 16)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0x38bdf8, 1.1)
    rim.position.set(-20, 12, -24)
    scene.add(rim)
    const warm = new THREE.PointLight(0xf59e0b, 35, 60, 2)
    warm.position.set(0, 5, 0)
    scene.add(warm)

    const grid = new THREE.GridHelper(80, 80, 0x1c4663, 0x102334)
    grid.position.y = -0.8
    ;(grid.material as THREE.Material).transparent = true
    ;(grid.material as THREE.Material).opacity = 0.38
    scene.add(grid)

    modelGroup = new THREE.Group()
    scene.add(modelGroup)
    raycaster = new THREE.Raycaster()
    controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.07
    controls.screenSpacePanning = true
    controls.maxPolarAngle = Math.PI * 0.495
    controls.minPolarAngle = Math.PI * 0.08

    renderer.domElement.addEventListener('pointerdown', onPointerDown)
    renderer.domElement.addEventListener('pointerup', onPointerUp)
    renderer.domElement.addEventListener('pointermove', onPointerMove)

    resizeObserver = new ResizeObserver(() => {
      if (!host.value || !renderer || !camera) return
      const width = host.value.clientWidth
      const height = host.value.clientHeight
      if (!width || !height) return
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    })
    resizeObserver.observe(host.value)

    const animate = () => {
      if (disposed) return
      frame = requestAnimationFrame(animate)
      controls?.update()
      if (scene && camera && renderer) renderer.render(scene, camera)
    }
    animate()
    rebuild()
    setTimeout(() => rebuild(), 30)
  } catch (error: any) {
    failed.value = error?.message || 'WebGL 初始化失败'
  }
}

function dispose() {
  disposed = true
  cancelAnimationFrame(frame)
  resizeObserver?.disconnect()
  if (renderer) {
    renderer.domElement.removeEventListener('pointerdown', onPointerDown)
    renderer.domElement.removeEventListener('pointerup', onPointerUp)
    renderer.domElement.removeEventListener('pointermove', onPointerMove)
    renderer.dispose()
    renderer.domElement.remove()
    renderer = null
  }
  if (scene) {
    disposeObject(scene)
    scene = null
  }
  controls?.dispose()
  controls = null
  camera = null
  meshMap.clear()
}

onMounted(init)
onBeforeUnmount(dispose)
watch(() => props.meshes, () => rebuild(), { deep: false })
watch(() => props.selectedGuid, (guid) => updateSelection(guid))
watch(() => props.riskGuids, () => applyRiskState(), { deep: true })
watch(() => [props.evidencePoint, props.evidenceLabel], () => updateEvidence(props.evidencePoint), { deep: true })
watch(
  () => props.targetGuid,
  () => {
    applyRiskState()
    updateSelection(props.selectedGuid)
  },
)

defineExpose({ focusGuid, resetView, addMesh })
</script>

<template>
  <div class="viewer-shell">
    <div ref="host" class="viewer-canvas" />
    <div v-if="failed" class="viewer-error">
      <strong>三维视图不可用</strong>
      <span>{{ failed }}</span>
    </div>
    <div v-else-if="!ready" class="viewer-loading">
      <span class="loader" />
      <span>加载 {{ meshes.length || 35 }} 个真实 IFC 网格…</span>
    </div>
    <div class="viewer-hint">拖拽旋转 · 滚轮缩放 · 右键平移 · 点击构件</div>
    <div class="viewer-compass">
      <span>N</span>
      <i />
    </div>
  </div>
</template>

<style scoped>
.viewer-shell {
  --text: #e0ebfa;
  --muted: #9bb3ce;
  --line: rgba(180, 207, 235, .18);
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
  overflow: hidden;
  background:
    radial-gradient(70% 70% at 50% 20%, rgba(56, 189, 248, 0.07), transparent 70%),
    linear-gradient(180deg, #10243b, #0a192b);
}
.viewer-canvas {
  position: absolute;
  inset: 0;
}
.viewer-hint {
  position: absolute;
  left: 14px;
  bottom: 12px;
  font-size: 9.5px;
  color: rgba(145, 166, 189, 0.7);
  letter-spacing: 0.03em;
  pointer-events: none;
  background: rgba(5, 13, 24, 0.55);
  padding: 3px 7px;
  border-radius: 4px;
  border: 1px solid var(--line);
}
.viewer-compass {
  position: absolute;
  right: 16px;
  bottom: 14px;
  width: 34px;
  height: 34px;
  border: 1px solid var(--line);
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--muted);
  font-size: 8px;
  font-family: var(--mono);
  background: rgba(5, 13, 24, 0.5);
}
.viewer-compass i {
  position: absolute;
  width: 1px;
  height: 10px;
  top: 4px;
  background: var(--teal);
}
.viewer-compass i::after {
  content: "";
  position: absolute;
  left: -2px;
  bottom: -1px;
  border-left: 2.5px solid transparent;
  border-right: 2.5px solid transparent;
  border-top: 4px solid var(--teal);
}
.viewer-loading,
.viewer-error {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 11px;
  color: var(--muted);
  background: rgba(5, 13, 24, 0.4);
  pointer-events: none;
}
.viewer-error {
  color: var(--red);
}
.viewer-error strong {
  color: var(--text);
  font-size: 13px;
}
.loader {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 2px solid rgba(45, 212, 191, 0.16);
  border-top-color: var(--teal);
  animation: spin 0.9s linear infinite;
}
</style>
