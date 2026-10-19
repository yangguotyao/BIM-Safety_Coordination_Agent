<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import type { MeshData } from '../types'

const props = withDefaults(
  defineProps<{
    meshes: MeshData[]
    overviewUrl?: string
    overviewStorey?: string
    targetGuid?: string
    riskGuids?: string[]
    selectedGuid?: string
    evidencePoint?: number[] | null
    evidenceLabel?: string
    edgeSegments?: number[][][]
    selectedEdgeIndex?: number
    pointPlacement?: boolean
    activityVolumes?: {task_id:string;workspace:{min:number[];max:number[]};conflict?:boolean}[]
  }>(),
  {
    targetGuid: '',overviewStorey:'',
    riskGuids: () => [],
    selectedGuid: '',
    evidencePoint: null,
    evidenceLabel: '',
    edgeSegments:()=>[],selectedEdgeIndex:0,pointPlacement:false,activityVolumes:()=>[],
  },
)

const emit = defineEmits<{ select: [guid: string]; selectStorey: [guid: string];selectEdge:[index:number];placePoint:[point:number[]];selectActivity:[id:string] }>()

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
let grid: THREE.GridHelper | null = null
let annotationGroup: THREE.Group | null = null
let placing = false

function updateAnnotations() {
  if (!scene || !modelGroup) return
  if (annotationGroup) { scene.remove(annotationGroup); disposeObject(annotationGroup) }
  annotationGroup = new THREE.Group()
  props.edgeSegments.forEach((edge,index)=>{
    const points=edge.map(point=>toThree([point[0],point[1],point[2]+.04]))
    const line=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({
      color:index===props.selectedEdgeIndex ? 0xea7c25 : 0x3b82b6,depthTest:false,transparent:true,opacity:index===props.selectedEdgeIndex ? 1 : .55,
    }))
    line.userData.edgeIndex=index;line.renderOrder=5;annotationGroup!.add(line)
  })
  props.activityVolumes.forEach(item=>{
    const low=item.workspace.min,high=item.workspace.max
    const size=new THREE.Vector3(high[0]-low[0],high[2]-low[2],high[1]-low[1])
    const box=new THREE.Mesh(new THREE.BoxGeometry(size.x,size.y,size.z),new THREE.MeshBasicMaterial({
      color:item.conflict ? 0xe15c3d : 0x3b8bbd,transparent:true,opacity:item.conflict ? .23 : .10,depthWrite:false,
    }))
    box.position.copy(toThree(low.map((v,i)=>(v+high[i])/2)))
    box.userData.activityId=item.task_id
    box.add(new THREE.LineSegments(new THREE.EdgesGeometry(box.geometry),new THREE.LineBasicMaterial({color:item.conflict ? 0xc64f31 : 0x3683b5})))
    annotationGroup!.add(box)
  })
  scene.add(annotationGroup)
}

function placeOnFloor(event:PointerEvent) {
  if (!camera || !renderer || !raycaster || !props.edgeSegments.length) return
  const rect=renderer.domElement.getBoundingClientRect()
  pointer.set((event.clientX-rect.left)/rect.width*2-1,-((event.clientY-rect.top)/rect.height)*2+1)
  raycaster.setFromCamera(pointer,camera)
  const z=props.edgeSegments[props.selectedEdgeIndex]?.[0]?.[2]
  if (z==null) return
  const hit=raycaster.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),-(z-centerIfc.z)),new THREE.Vector3())
  if (hit) emit('placePoint',[hit.x+centerIfc.x,centerIfc.y-hit.z,z].map(v=>Math.round(v*1000)/1000))
}

async function loadOverview() {
  try {
    const gltf = await new GLTFLoader().loadAsync(props.overviewUrl!)
    if (disposed || !scene || !modelGroup) { disposeObject(gltf.scene); return }
    clearModel()
    gltf.scene.traverse(object => {
      if (object instanceof THREE.Mesh && !object.geometry.getAttribute('normal')) object.geometry.computeVertexNormals()
    })
    modelGroup!.add(gltf.scene)
    const box = new THREE.Box3().setFromObject(modelGroup!)
    sceneRadius = Math.max(box.getSize(new THREE.Vector3()).length(), 8)
    if (grid) {
      grid.position.y = box.min.y - .3
      grid.scale.setScalar(Math.max((box.max.x-box.min.x)/65, 1))
    }
    scene.fog = null
    filterOverview()
    ready.value = true
  } catch {
    if (!disposed) failed.value = '建筑模型加载失败，请刷新重试。'
  }
}

function toThree(point: number[]): THREE.Vector3 {
  return new THREE.Vector3(point[0] - centerIfc.x, point[2] - centerIfc.z, -(point[1] - centerIfc.y))
}

function filterOverview() {
  if(!props.overviewUrl || !modelGroup || !camera || !controls) return
  modelGroup.updateMatrixWorld(true)
  const box=new THREE.Box3()
  modelGroup.traverse(object=>{
    if(!(object instanceof THREE.Mesh)) return
    object.visible=!props.overviewStorey || object.userData.storeyGuid===props.overviewStorey
    if(object.visible) box.union(new THREE.Box3().setFromObject(object))
  })
  if(box.isEmpty()) return
  sceneRadius=Math.max(box.getSize(new THREE.Vector3()).length(),8)
  const center=box.getCenter(new THREE.Vector3())
  const vertical=THREE.MathUtils.degToRad(camera.fov)
  const horizontal=2*Math.atan(Math.tan(vertical/2)*camera.aspect)
  const distance=sceneRadius*.5/Math.sin(Math.min(vertical,horizontal)/2)*1.06
  controls.target.copy(center)
  camera.position.copy(center.clone().add(new THREE.Vector3(.7,.6,.9).normalize().multiplyScalar(distance)))
  controls.maxDistance=sceneRadius*5;controls.minDistance=sceneRadius*.04;controls.update()
  if(grid)grid.position.y=box.min.y-.3
}

function materialFor(mesh: MeshData): THREE.MeshStandardMaterial {
  const isTarget = mesh.guid === props.targetGuid
  const isSlab = mesh.ifc_class === 'IfcSlab'
  const base = isTarget ? 0x5eacc7 : isSlab ? 0xb9ccd8 : 0x8198ad
  const emissive = 0x000000
  return new THREE.MeshStandardMaterial({
    color: base,
    emissive,
    emissiveIntensity: 0,
    metalness: 0.16,
    roughness: isSlab ? 0.54 : 0.76,
    side: THREE.DoubleSide,
    transparent: false,
  })
}

function makeObject(mesh: MeshData): THREE.Mesh {
  const isTarget = mesh.guid === props.targetGuid
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
  {
    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geometry, 28),
      new THREE.LineBasicMaterial({ color: isTarget ? 0x176282 : 0x49657d, transparent: true, opacity: isTarget ? .8 : .35 }),
    )
    object.add(edges)
  }
  return object
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    if (child instanceof THREE.Mesh || child instanceof THREE.Line) {
      child.geometry.dispose()
      const material = child.material
      if (Array.isArray(material)) material.forEach((item) => item.dispose())
      else material.dispose()
    }
  })
}

function clearModel() {
  if (!scene || !modelGroup) return
  updateSelection('')
  clearEvidence()
  if (annotationGroup) { scene.remove(annotationGroup);disposeObject(annotationGroup);annotationGroup=null }
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
  updateAnnotations()
}

function resetView() {
  if (!scene || !camera || !controls) return
  if (props.overviewUrl) {
    filterOverview()
    return
  }
  const radius = sceneRadius * 0.72
  camera.position.set(radius * .52, radius * 1.05, radius * .72)
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
  selectionBox = new THREE.Box3Helper(box, new THREE.Color(0x1d4ed8))
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
    context.fillStyle = 'rgba(255, 255, 255, 0.95)'
    context.roundRect(2, 2, 380, 92, 16)
    context.fill()
    context.strokeStyle = 'rgba(251, 191, 36, 0.75)'
    context.lineWidth = 3
    context.stroke()
    context.fillStyle = '#8a5100'
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
  for (const [guid, target] of meshMap) {
    const isTarget = guid === props.targetGuid
    const atRisk = props.riskGuids.includes(guid)
    const material = target.material as THREE.MeshStandardMaterial
    material.color.setHex(atRisk ? 0xd66a36 : isTarget ? 0x5eacc7 : target.userData.ifcClass==='IfcSlab' ? 0xb9ccd8 : 0x8198ad)
    material.emissive.setHex(0x000000)
    material.emissiveIntensity = 0
    target.traverse((child) => {
      if (child instanceof THREE.LineSegments) {
        const line = child.material as THREE.LineBasicMaterial
        line.color.setHex(atRisk ? 0x9e431a : isTarget ? 0x176282 : 0x49657d)
        line.opacity = atRisk || isTarget ? .8 : .35
      }
    })
  }
}

function pick(event: PointerEvent) {
  if (!renderer || !camera || !raycaster || !modelGroup) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  if (annotationGroup) {
    raycaster.params.Line.threshold=.3
    for (const hit of raycaster.intersectObjects(annotationGroup.children,true)) {
      if (typeof hit.object.userData.edgeIndex==='number') { emit('selectEdge',hit.object.userData.edgeIndex);return }
      if (hit.object.userData.activityId) { emit('selectActivity',hit.object.userData.activityId);return }
    }
  }
  const hits = raycaster.intersectObjects(modelGroup.children, true).filter(hit=>hit.object.visible)
  for (const hit of hits) {
    let current: THREE.Object3D | null = hit.object
    if (props.overviewUrl) {
      while (current && !current.userData.storeyGuid) current = current.parent
      if (current?.userData.storeyGuid) emit('selectStorey', current.userData.storeyGuid)
      return
    }
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
  if (props.pointPlacement && event.button===0) {
    placing=true
    if (controls) controls.enabled=false
    renderer?.domElement.setPointerCapture(event.pointerId)
    placeOnFloor(event)
  }
}

function onPointerUp(event: PointerEvent) {
  if (placing) { placeOnFloor(event);placing=false;if (controls) controls.enabled=true;return }
  if (Math.abs(event.clientX - downX) < 5 && Math.abs(event.clientY - downY) < 5) pick(event)
}

function onPointerMove(event: PointerEvent) {
  if (placing) { placeOnFloor(event);return }
  if (!renderer || !camera || !raycaster || !modelGroup) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)
  const hits = raycaster.intersectObjects(modelGroup.children, true).filter(hit=>hit.object.visible)
  let nextHover: THREE.Mesh | null = null
  for (const hit of hits) {
    let current: THREE.Object3D | null = hit.object
    if (props.overviewUrl && current instanceof THREE.Mesh) { nextHover = current; break }
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
    scene.fog = new THREE.FogExp2(0xf2f5f8, 0.004)
    camera = new THREE.PerspectiveCamera(42, 1, 0.1, 800)
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.05
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.cursor = 'grab'
    host.value.appendChild(renderer.domElement)

    scene.add(new THREE.HemisphereLight(0xffffff, 0x8d9dab, 1.15))
    const key = new THREE.DirectionalLight(0xffffff, 1.8)
    key.position.set(18, 30, 16)
    scene.add(key)
    const rim = new THREE.DirectionalLight(0xc8d9e5, .7)
    rim.position.set(-20, 12, -24)
    scene.add(rim)
    const warm = new THREE.PointLight(0xf59e0b, 35, 60, 2)
    warm.position.set(0, 5, 0)
    scene.add(warm)

    grid = new THREE.GridHelper(80, 80, 0x9aaebe, 0xc6d1dc)
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
    if (props.overviewUrl) loadOverview()
    else rebuild()
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
watch(()=>[props.edgeSegments,props.selectedEdgeIndex,props.activityVolumes],updateAnnotations,{deep:true})
watch(()=>props.overviewStorey,filterOverview)
watch(() => props.meshes, () => { if (!props.overviewUrl) rebuild() }, { deep: false })
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

defineExpose({ focusGuid, resetView })
</script>

<template>
  <div class="viewer-shell">
    <div ref="host" class="viewer-canvas" />
    <div v-if="failed" class="viewer-error">
      <strong>三维视图不可用</strong>
      <span>{{ failed }}</span>
    </div>
    <div v-else-if="!meshes.length && !overviewUrl" class="viewer-loading">
      <strong>当前筛选没有已加载的几何</strong>
    </div>
    <div v-else-if="!ready" class="viewer-loading">
      <span class="loader" />
      <span>{{ overviewUrl ? '正在加载整栋建筑…' : '正在加载检查区域…' }}</span>
    </div>
    <div class="viewer-hint">旋转 · 缩放 · 平移</div>
    <div class="viewer-compass">
      <span>N</span>
      <i />
    </div>
  </div>
</template>

<style scoped>
.viewer-shell {
  --text: #20364c;
  --muted: #63798c;
  --line: #cad6e0;
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 480px;
  overflow: hidden;
  background: linear-gradient(180deg, #ffffff, #edf1f5);
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
  color: #526a7f;
  letter-spacing: 0.03em;
  pointer-events: none;
  background: rgba(255, 255, 255, 0.88);
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
  background: rgba(255, 255, 255, 0.88);
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
  background: rgba(242, 245, 248, 0.85);
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
