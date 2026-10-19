<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute,useRouter } from 'vue-router'
import { Box, ChevronLeft, ChevronRight, Copy, Crosshair, Layers, Loader2, Maximize2, RefreshCw, Search, ShieldAlert, TriangleAlert,Send,Paperclip,FileText,ClipboardList,BookOpen } from 'lucide-vue-next'
import BimViewer from '../components/BimViewer.vue'
import EmptyState from '../components/EmptyState.vue'
import { api } from '../api'
import type { CaseBundle,ElementRow, Evidence, MeshData, MeshPayload } from '../types'
import { actorId,errorMessage, refreshSummary,store, toast } from '../store'
import { formatNumber,localDateTime,isoDateTime, observationLabel, observationValue, shortGuid } from '../utils'

const MODEL_ID = 'S1-bSDD-example'
const TARGET_GUID = '0FOHK4aT910wgskSbVHn0U'
const INDEXED_STOREY = '1Vhy2b2Mj9FRewx9CZZoux'

const route = useRoute()
const router=useRouter(),browseStorey=ref(''),starting=ref(false),taskFile=ref<File|null>(null),sampleId=ref('')
const taskRequest=ref('全面检查 L05 楼板区域的临边防护和人员暴露风险，结合现场证据与规范依据提出整改要求。')
const taskTime=ref('2026-10-16T09:00:00+08:00')
const canStartTask=computed(()=>!browseStorey.value || browseStorey.value===INDEXED_STOREY)
const browsingFloor=computed(()=>buildingMeta.value?.storeys.find(s=>s.guid===browseStorey.value))
const floorLabel=(item:any)=>{
  const floor=parseInt(item.name,10)
  return floor===-1 ? '基础层 · -1' : floor===0 ? '首层 · 00' : floor===17 ? '17 层 · 屋面' : `${String(floor).padStart(2,'0')} 层`
}
function taskFileChanged(event:Event) {
  const file=(event.target as HTMLInputElement).files?.[0] || null
  if(file && file.size>20*1024*1024) {toast('文件不能超过20MB','warning');return}
  taskFile.value=file
  if(file)sampleId.value=''
}
async function startTask() {
  if(starting.value || !taskRequest.value.trim() || !canStartTask.value)return
  starting.value=true;let createdId=''
  try {
    const value=await api.post<CaseBundle>('/cases',{title:'05 层 · 安全检查',request_text:taskRequest.value.trim(),actor_id:actorId,
      as_of:taskTime.value,evidence_ids:taskFile.value ? [] : sampleId.value ? [sampleId.value] : []})
    createdId=value.case.case_id
    if(taskFile.value) {
      const data=new FormData();data.append('file',taskFile.value);data.append('stage','before');data.append('captured_at',taskTime.value);data.append('note',taskFile.value.name)
      await api.postForm(`/cases/${createdId}/evidence/upload`,data)
    }
    await api.post(`/cases/${createdId}/analyze`)
    await router.push(`/cases/${createdId}`);refreshSummary()
  } catch(cause) {toast(errorMessage(cause),'error');if(createdId)router.push(`/cases/${createdId}`)}
  finally {starting.value=false}
}
const overview = ref(!route.query.guid && !route.query.evidence && route.query.scope !== 'target')
const buildingMeta = ref<{exported_elements:number;storeys:any[];bytes:number} | null>(null)
const viewerRef = ref<InstanceType<typeof BimViewer> | null>(null)
const meshPayload = ref<MeshPayload | null>(null)
const storeys = ref<any[]>([])
const elements = ref<ElementRow[]>([])
const total = ref(0)
const detail = ref<ElementRow | null>(null)
const evidence = ref<Evidence | null>(null)
const selectedGuid = ref(typeof route.query.guid === 'string' ? route.query.guid : TARGET_GUID)
const evidenceZone = ref<Record<string, any> | null>(null)
const targetGuid = computed(() => evidence.value?.bim_guids[0] || selectedGuid.value)
const riskHighlight = ref(true)
const loadingMesh = ref(true)
const loadingTable = ref(false)
const loadingDetail = ref(false)
const loadingGeometry = ref(false)
const error = ref('')

const filters = reactive({
  storey: INDEXED_STOREY,
  ifcClass: '',
  q: '',
  page: 0,
  limit: 18,
})

const zone = computed(() => evidenceZone.value || (selectedGuid.value === TARGET_GUID ? meshPayload.value?.zone || {} : {}))
const visibleMeshes = computed(() => {
  if (filters.storey !== (zone.value.storey_guid || INDEXED_STOREY)) return []
  return (meshPayload.value?.meshes || []).filter(mesh => !filters.ifcClass || mesh.ifc_class === filters.ifcClass)
})
const selectedVisible = computed(() => visibleMeshes.value.some(mesh => mesh.guid === selectedGuid.value))
const evidencePoint = computed<number[] | null>(() => {
  if (!evidence.value || !visibleMeshes.value.some(mesh => mesh.guid === targetGuid.value)) return null
  const point = evidence.value.observation.worker_point_m || zone.value.worker_point_m
  return Array.isArray(point) ? point : null
})
const evidenceLabel = computed(() => (evidence.value ? `${evidence.value.evidence_id} · 标注人员位置` : ''))
const isRiskEvidence = computed(() => {
  if (!evidence.value) return false
  const observation = evidence.value.observation || {}
  const state = observation.guardrail_state
  const height = observation.guardrail_height_m
  return state === 'absent' || (state === 'present' && typeof height === 'number' && height < 1.2)
})
const riskGuids = computed(() => (riskHighlight.value && isRiskEvidence.value ? [targetGuid.value] : []))
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / filters.limit)))
const storeyLabel = computed(() => {
  const current = storeys.value.find((item) => item.guid === filters.storey)
  return current?.name || '05 vijfde verdieping'
})
const selectedInPreview = computed(() => {
  return Boolean(meshPayload.value?.meshes.some((mesh) => mesh.guid === selectedGuid.value))
})
const bboxText = computed(() => {
  const bbox = detail.value?.bbox_m
  if (!bbox) return '—'
  const format = (values: number[]) => values.map((value) => value.toFixed(2)).join(' / ')
  return `${format(bbox.min)}  →  ${format(bbox.max)}`
})
const edgeLength = computed(() => {
  const edge = zone.value.edge_segment_m
  if (!Array.isArray(edge) || edge.length !== 2) return '—'
  const [a, b] = edge
  return Math.hypot(a[0] - b[0], a[1] - b[1]).toFixed(2)
})
const editableClasses = [
  { value: '', label: '全部类别' },
  { value: 'IfcSlab', label: 'IfcSlab 楼板' },
  { value: 'IfcWall', label: 'IfcWall 墙' },
  { value: 'IfcBuildingElementProxy', label: 'IfcBuildingElementProxy' },
  { value: 'IfcCovering', label: 'IfcCovering 覆盖层' },
  { value: 'IfcMember', label: 'IfcMember 构件' },
  { value: 'IfcPlate', label: 'IfcPlate 板' },
  { value: 'IfcDoor', label: 'IfcDoor 门' },
  { value: 'IfcWindow', label: 'IfcWindow 窗' },
]

async function loadMesh() {
  loadingMesh.value = true
  error.value = ''
  try {
    meshPayload.value = await api.get<MeshPayload>(`/models/${MODEL_ID}/mesh?scope=target`)
  } catch (err: any) {
    error.value = errorMessage(err)
  } finally {
    loadingMesh.value = false
  }
}

async function loadStoreys() {
  try {
    const response = await api.get<{ rows: any[] }>(`/models/${MODEL_ID}/storeys`)
    storeys.value = response.rows
  } catch {
    storeys.value = []
  }
}

async function loadElements() {
  loadingTable.value = true
  try {
    const params = new URLSearchParams({
      limit: String(filters.limit),
      offset: String(filters.page * filters.limit),
      storey_guid: filters.storey,
    })
    if (filters.ifcClass) params.set('ifc_class', filters.ifcClass)
    if (filters.q.trim()) params.set('q', filters.q.trim())
    const response = await api.get<any>(`/models/${MODEL_ID}/elements?${params.toString()}`)
    elements.value = response.rows
    total.value = response.total
  } catch (err: any) {
    toast(errorMessage(err), 'error')
  } finally {
    loadingTable.value = false
  }
}

async function loadDetail(guid = selectedGuid.value) {
  loadingDetail.value = true
  try {
    const response = await api.get<{ element: ElementRow }>(`/models/${MODEL_ID}/elements/${encodeURIComponent(guid)}`)
    detail.value = response.element
  } catch {
    detail.value = null
  } finally {
    loadingDetail.value = false
  }
}

async function selectEvidenceById(id: string) {
  try {
    const response = await api.get<{ evidence: Evidence; zone: Record<string, any> }>(`/evidence/${id}`)
    evidence.value = response.evidence
    evidenceZone.value = response.zone
    selectedGuid.value = response.evidence.bim_guids[0] || TARGET_GUID
    await loadDetail(selectedGuid.value)
    if (!selectedInPreview.value) await loadSelectedGeometry()
    await nextTick()
    viewerRef.value?.focusGuid(selectedGuid.value)
  } catch (err: any) {
    toast(errorMessage(err), 'error')
  }
}

async function selectElement(guid: string) {
  if (evidence.value && !evidence.value.bim_guids.includes(guid)) {
    evidence.value=null
    evidenceZone.value=null
  }
  selectedGuid.value = guid
  await loadDetail(guid)
  await nextTick()
  if (meshPayload.value?.meshes.some((mesh) => mesh.guid === guid)) {
    viewerRef.value?.focusGuid(guid)
  }
}

async function loadSelectedGeometry() {
  if (!detail.value || loadingGeometry.value) return
  loadingGeometry.value = true
  const guid = detail.value.guid
  toast('正在从原始 IFC 按需提取几何；首次打开约需 10–20 秒。', 'info', 7000)
  try {
    const response = await api.get<{ mesh: MeshData }>(
      `/models/${MODEL_ID}/elements/${encodeURIComponent(guid)}/mesh`,
    )
    if (meshPayload.value) {
      meshPayload.value.meshes.push(response.mesh)
    }
    await nextTick()
    if (selectedGuid.value === guid) {
      await loadDetail(guid)
      viewerRef.value?.focusGuid(guid)
    }
    toast('已按需加载构件几何并加入场景。', 'success')
  } catch (err: any) {
    toast(errorMessage(err), 'error', 8000)
  } finally {
    loadingGeometry.value = false
  }
}

function resetView() {
  viewerRef.value?.resetView()
}

async function enterInspectionArea() {
  overview.value = false
  filters.storey = INDEXED_STOREY
  filters.ifcClass = ''
  filters.q = ''
  filters.page = 0
  await loadElements()
  if (!detail.value) await selectEvidenceById('EV-001')
}

function changeScope(event: Event) {
  if ((event.target as HTMLSelectElement).value === 'target') enterInspectionArea()
  else overview.value = true
}

function selectBuildingStorey(guid: string) {
  browseStorey.value=guid
}

async function copyGuid() {
  if (!detail.value) return
  try {
    await navigator.clipboard.writeText(detail.value.guid)
    toast('GUID 已复制', 'success', 2000)
  } catch {
    toast('复制失败，请手动选择', 'warning')
  }
}

function turnPage(delta: number) {
  const next = Math.min(Math.max(filters.page + delta, 0), pageCount.value - 1)
  if (next === filters.page) return
  filters.page = next
  loadElements()
}

let searchTimer: number | undefined
function onSearch() {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    filters.page = 0
    loadElements()
  }, 320)
}

function onClassChange() {
  filters.page = 0
  loadElements()
}

watch(
  () => route.query.evidence,
  (id) => {
    if (typeof id === 'string' && id) { overview.value = false; selectEvidenceById(id) }
  },
)

watch(()=>route.hash,async hash=>{
  if(hash!=='#home-task')return
  overview.value=true;await nextTick()
  const input=document.getElementById('home-task');input?.focus();input?.scrollIntoView({behavior:'smooth',block:'center'})
},{immediate:true})

onMounted(async () => {
  await Promise.all([loadMesh(), loadStoreys(), fetch('/bim/s1-building.json').then(r => {
    if (!r.ok) throw new Error('metadata unavailable')
    return r.json()
  }).then(data => buildingMeta.value = data).catch(() => {})])
  if (overview.value) return
  await loadElements()
  if (typeof route.query.evidence === 'string') await selectEvidenceById(route.query.evidence)
  else if (typeof route.query.guid === 'string') {
    await loadDetail(selectedGuid.value)
    if (!selectedInPreview.value) await loadSelectedGeometry()
    await nextTick()
    viewerRef.value?.focusGuid(selectedGuid.value)
  } else await selectEvidenceById('EV-001')
})
</script>

<template>
  <div class="page bim-page">
    <div class="page-head">
      <div>
        <h1>BIM 安全工作台</h1>
      </div>
      <div class="head-actions">
        <button v-if="!overview" class="btn" @click="overview=true"><Box :size="16" /> 建筑总览</button>
        <router-link v-if="!overview && detail?.ifc_class === 'IfcSlab'" class="btn btn-primary" :to="{path:'/inspection',query:{guid:selectedGuid}}"><ShieldAlert :size="16" /> 检查选中楼板</router-link>
        <button class="btn btn-sm" @click="resetView"><Maximize2 :size="14" /> 重置视角</button>
      </div>
    </div>

    <section v-if="overview" class="home-start">
      <div class="card building-workspace">
        <div class="building-toolbar"><span><Box :size="19" />{{ browsingFloor ? floorLabel(browsingFloor) : 'S1 · 整栋建筑' }}</span><select v-model="browseStorey" class="select" aria-label="浏览楼层"><option value="">整栋建筑</option><option v-for="floor in buildingMeta?.storeys || []" :key="floor.guid" :value="floor.guid">{{ floorLabel(floor) }}</option></select></div>
        <div class="building-canvas"><BimViewer ref="viewerRef" :meshes="[]" overview-url="/bim/s1-building.glb" :overview-storey="browseStorey" @select-storey="selectBuildingStorey" /></div>
        <div class="building-foot"><span>{{ buildingMeta?.storeys.length || 19 }} 个楼层 · {{ formatNumber(buildingMeta?.exported_elements || 16372) }} 个构件</span><button class="btn btn-sm" @click="enterInspectionArea">查看05层构件 <ChevronRight :size="15" /></button></div>
      </div>
      <form class="card task-launcher" @submit.prevent="startTask">
        <div class="task-launch-heading"><span class="task-icon"><ShieldAlert :size="23" /></span><div><span class="task-eyebrow">安全检查</span><h2>发起检查任务</h2></div><span class="badge" :class="canStartTask ? 'tone-blue' : 'tone-slate'">{{ canStartTask ? '05 层 · 板边区域' : '楼层浏览' }}</span></div>
        <label class="task-label" for="home-task">检查任务</label><textarea id="home-task" v-model="taskRequest" class="textarea task-prompt" rows="5" aria-label="检查任务" required />
        <div v-if="!canStartTask" class="floor-capability">{{ browsingFloor ? floorLabel(browsingFloor) : '' }}可浏览模型；安全检查目前支持05层。</div>
        <div class="launch-materials"><label class="btn btn-sm"><Paperclip :size="15" />添加现场资料<input type="file" accept=".png,.jpg,.jpeg,.pdf" aria-label="检查任务现场资料" @change="taskFileChanged" /></label><span v-if="taskFile" class="material-name">{{ taskFile.name }}</span><span v-else-if="sampleId" class="material-name">演示资料 {{ sampleId }}</span></div>
        <details class="launch-options"><summary>检查资料与时刻</summary><label>检查时刻<input class="input" type="datetime-local" :value="localDateTime(taskTime)" aria-label="任务检查时刻" @change="taskTime=isoDateTime(($event.target as HTMLInputElement).value)" /></label><label>载入演示资料<select v-model="sampleId" class="select" aria-label="载入演示资料" @change="taskFile=null"><option value="">不载入</option><option value="EV-001">05层检查资料 01 · 模拟示意图</option><option value="EV-003">05层检查资料 02 · 模拟示意图</option><option value="EV-004">05层检查资料 03 · 模拟示意图</option><option value="EV-007">05层检查资料 04 · 模拟示意图</option></select></label></details>
        <button class="btn btn-primary launch-submit" :disabled="starting || !canStartTask || !taskRequest.trim()"><Loader2 v-if="starting" :size="18" class="spin" /><Send v-else :size="18" />{{ starting ? '正在发起检查' : '发起检查' }}</button>
      </form>
      <nav class="home-shortcuts" aria-label="项目功能导航"><router-link class="card" to="/cases"><ClipboardList :size="21" /><span><strong>检查记录</strong><small>检查进度与处置结果</small></span><ChevronRight :size="17" /></router-link><router-link class="card" to="/evidence"><FileText :size="21" /><span><strong>现场资料</strong><small>照片与关联记录</small></span><ChevronRight :size="17" /></router-link><router-link class="card" to="/knowledge"><BookOpen :size="21" /><span><strong>规范依据</strong><small>条款与原文</small></span><ChevronRight :size="17" /></router-link></nav>
    </section>
    <template v-else>
    <div class="workspace card">
      <div class="toolbar">
        <select class="select scope-select" aria-label="选择检查范围" value="target" @change="changeScope"><option value="building">整栋建筑</option><option value="target">05 层 · 板边区域</option></select>
        <div class="tool-group">
          <Box :size="14" class="dim" />
          <select v-model="filters.ifcClass" class="select tool-select" aria-label="选择构件类别" @change="onClassChange">
            <option v-for="item in editableClasses" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </div>
        <div class="search-box">
          <Search :size="14" class="dim" />
          <input v-model="filters.q" class="input search-input" placeholder="搜索 GUID / 名称 / 类别" @input="onSearch" />
        </div>
        <button
          class="btn btn-sm"
          :class="{ 'btn-primary': riskHighlight }"
          @click="riskHighlight = !riskHighlight"
        >
          <ShieldAlert :size="14" /> 风险高亮
        </button>
        <button class="btn btn-sm" @click="loadElements"><RefreshCw :size="14" :class="{ spin: loadingTable }" /> 刷新</button>
      </div>

      <div class="bim-grid">
        <div class="canvas-panel">
          <BimViewer
            ref="viewerRef"
            :meshes="visibleMeshes"
            :target-guid="targetGuid"
            :risk-guids="riskGuids"
            :selected-guid="selectedGuid"
            :evidence-point="evidencePoint"
            :evidence-label="evidenceLabel"
            @select="selectElement"
          />
          <div class="canvas-overlay">
            <div class="canvas-chip mono">
              <span class="live-dot" /> 可见 {{ visibleMeshes.length }} / 已加载 {{ meshPayload?.meshes.length || 0 }}
            </div>
            <div class="canvas-legend">
              <span><i class="swatch slab" /> 楼板</span>
              <span><i class="swatch wall" /> 墙</span>
              <span><i class="swatch risk" /> 风险构件</span>
              <span><i class="swatch ev" /> 证据点</span>
            </div>
          </div>
          <div v-if="loadingMesh" class="canvas-loading">加载真实 IFC 网格…</div>
        </div>

        <aside class="inspector">
          <div class="inspector-head">
            <div>
              <div class="caption">选中构件</div>
              <div class="inspector-title">{{ detail?.name || '区域目标楼板' }}</div>
            </div>
            <span class="badge tone-cyan">{{ detail?.ifc_class || 'IfcSlab' }}</span>
          </div>

          <div v-if="loadingDetail" class="small muted" style="padding: 10px 0">读取构件属性…</div>
          <template v-else-if="detail">
            <div class="guid-line">
              <span class="mono break">{{ detail.guid }}</span>
              <button class="btn btn-ghost btn-icon btn-sm" title="复制 GUID" @click="copyGuid"><Copy :size="13" /></button>
            </div>
            <div class="kv">
              <span class="k">楼层</span><span class="v">{{ detail.storey_name }}</span>
              <span class="k">类别</span><span class="v mono">{{ detail.ifc_class }}</span>
              <span class="k">几何范围</span><span class="v mono">{{ bboxText }}</span>
              <span class="k">几何来源</span>
              <span class="v">
                <span v-if="selectedInPreview" class="badge tone-teal">已加载网格</span>
                <span v-else class="badge tone-amber">未加载 · 可按需提取</span>
              </span>
            </div>
            <div class="inspector-actions">
              <button class="btn btn-sm" :disabled="!selectedVisible" @click="viewerRef?.focusGuid(detail.guid)">
                <Crosshair :size="13" /> 三维定位
              </button>
              <button
                v-if="!selectedInPreview"
                class="btn btn-sm btn-primary"
                :disabled="loadingGeometry"
                @click="loadSelectedGeometry"
              >
                <Loader2 v-if="loadingGeometry" :size="13" class="spin" />
                <Box v-else :size="13" />
                按需加载几何
              </button>
            </div>
          </template>

          <div class="inspector-section">
            <div class="section-title">关联证据</div>
            <div v-if="evidence" class="evidence-mini">
              <img :src="evidence.image_url" :alt="evidence.label" />
              <div class="evidence-mini-body">
                <div class="row" style="justify-content: space-between">
                  <span class="mono small">{{ evidence.evidence_id }}</span>
                  <span class="badge tone-amber">{{ evidence.source==='upload' ? '上传原图' : '演示示意图' }}</span>
                </div>
                <div class="strong" style="margin-top: 4px">{{ evidence.label }}</div>
                <div class="tiny dim">{{ evidence.captured_at }}</div>
                <div class="obs-grid">
                  <span v-for="key in ['guardrail_state', 'guardrail_height_m', 'worker_present']" :key="key" class="chip">
                    <span class="k">{{ observationLabel(key) }}</span>
                    <span class="mono">{{ observationValue(evidence.observation[key]) }}</span>
                  </span>
                </div>
                <router-link class="small" to="/evidence" style="display: inline-flex; margin-top: 8px">
                  查看全部证据 <ChevronRight :size="12" />
                </router-link>
              </div>
            </div>
            <EmptyState v-else title="未选择证据" />
          </div>

          <div class="inspector-section">
            <div class="section-title">检查区域</div>
            <div class="kv">
              <span class="k">区域</span><span class="v mono">{{ zone.zone_id || '待建立检查区域' }}</span>
              <span class="k">边线来源</span><span class="v">真实板投影 + 人工标注</span>
              <span class="k">人员点</span><span class="v mono">{{ zone.worker_point_provenance || '待标注' }}</span>
              <span class="k">暴露阈值</span><span class="v">1.0 m（演示策略）</span>
            </div>
          </div>
        </aside>
      </div>
    </div>

    <div class="stat-strip">
      <div class="mini-stat">
        <div class="stat">{{ formatNumber(store.summary?.element_count || 16372) }}</div>
        <div class="stat-label">模型构件</div>
      </div>
      <div class="mini-stat">
        <div class="stat">{{ formatNumber(store.summary?.storey_element_count || 1247) }}</div>
        <div class="stat-label">05 层索引</div>
      </div>
      <div class="mini-stat">
        <div class="stat">{{ meshPayload?.meshes.length || 35 }}</div>
        <div class="stat-label">已加载网格</div>
      </div>
      <div class="mini-stat">
        <div class="stat">{{ storeys.length || 19 }}</div>
        <div class="stat-label">真实楼层</div>
      </div>
      <div class="mini-stat">
        <div class="stat">{{ edgeLength }}<span class="stat-unit">m</span></div>
        <div class="stat-label">标注边线长度</div>
      </div>
      <div class="mini-stat">
        <div class="stat">{{ evidence?.observation.drop_height_m ?? zone.drop_height_m ?? '—' }}<span class="stat-unit">m</span></div>
        <div class="stat-label">演示坠落高度</div>
      </div>
    </div>

    <div class="card table-card">
      <div class="card-head">
        <div class="card-title"><Layers :size="15" /> 构件索引 <span class="badge tone-slate">{{ formatNumber(total) }}</span></div>
        <div class="row small muted">
          <span>当前显示 {{ elements.length }} 条</span>
          <span class="divider-v" />
          <span class="mono">{{ storeyLabel }}</span>
        </div>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 78px">类别</th>
              <th>名称</th>
              <th style="width: 240px">GUID</th>
              <th style="width: 150px">几何</th>
              <th style="width: 110px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in elements"
              :key="item.guid"
              :class="{ 'is-active': item.guid === selectedGuid }"
              @click="selectElement(item.guid)"
            >
              <td><span class="badge tone-cyan">{{ item.ifc_class.replace('Ifc', '') }}</span></td>
              <td class="name-cell">{{ item.name }}</td>
              <td class="mono small dim">{{ shortGuid(item.guid, 12, 6) }}</td>
              <td>
                <span v-if="meshPayload?.meshes.some((mesh) => mesh.guid === item.guid)" class="badge tone-green">预览</span>
                <span v-else class="badge tone-slate">按需</span>
              </td>
              <td>
                <button class="btn btn-ghost btn-sm" @click.stop="selectElement(item.guid)">
                  <Crosshair :size="12" /> 查看
                </button>
              </td>
            </tr>
            <tr v-if="!elements.length && !loadingTable">
              <td colspan="5"><EmptyState title="该范围暂无构件" /></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="table-foot">
        <span class="small dim">第 {{ filters.page + 1 }} / {{ pageCount }} 页 · 共 {{ formatNumber(total) }} 个构件</span>
        <div class="row">
          <button class="btn btn-sm" :disabled="filters.page <= 0" @click="turnPage(-1)"><ChevronLeft :size="13" /> 上一页</button>
          <button class="btn btn-sm" :disabled="filters.page >= pageCount - 1" @click="turnPage(1)">下一页 <ChevronRight :size="13" /></button>
        </div>
      </div>
    </div>
    </template>

    <div v-if="error" class="card" style="margin-top: 16px; padding: 18px; border-color: rgba(251,113,133,.35)">
      <div class="row" style="color: var(--red)"><TriangleAlert :size="16" /> {{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.bim-page {
  max-width: 1780px;
}
.home-start{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(340px,1fr);gap:22px;align-items:stretch}.building-workspace{overflow:hidden}.building-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:19px 22px;border-bottom:1px solid var(--line)}.building-toolbar>span{display:flex;align-items:center;gap:9px;font-size:17px;font-weight:650}.building-toolbar .select{width:145px}.building-canvas{height:390px;position:relative}.building-canvas :deep(.viewer-shell){min-height:100%}.building-foot{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;gap:10px;border-top:1px solid var(--line)}.building-foot>span{font-size:12px;color:var(--muted)}.task-launcher{padding:26px;display:flex;flex-direction:column;min-width:0}.task-launch-heading{display:flex;align-items:center;gap:12px;margin-bottom:25px}.task-icon{display:grid;place-items:center;width:45px;height:45px;border-radius:12px;color:var(--blue);background:#edf4ff}.task-eyebrow{font-size:12px;color:var(--muted)}.task-launch-heading h2{font-size:23px;margin-top:4px}.task-launch-heading .badge{margin-left:auto}.task-label{font-size:13px;color:var(--text-soft);margin-bottom:10px}.task-prompt{font-size:16px;line-height:1.9;min-height:150px;resize:vertical;background:#f8fafc}.launch-materials{display:flex;align-items:center;gap:10px;margin:16px 0}.launch-materials input{display:none}.material-name{font-size:12px;color:var(--muted);overflow-wrap:anywhere;min-width:0}.launch-options{font-size:13px;color:var(--muted);margin:0 0 18px}.launch-options summary{cursor:pointer}.launch-options label{display:grid;gap:7px;margin-top:14px}.launch-submit{width:100%;min-height:46px;margin-top:auto}.floor-capability{padding:10px 0;color:var(--amber);font-size:13px}.home-shortcuts{grid-column:1/-1;display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.home-shortcuts>a{display:flex;align-items:center;gap:14px;padding:21px;color:var(--blue)}.home-shortcuts strong{font-size:16px;color:var(--text);display:block}.home-shortcuts small{display:block;font-size:12px;color:var(--muted);margin-top:7px}.home-shortcuts>a>svg:last-child{margin-left:auto;color:var(--muted)}.scope-select{max-width:210px}@media(max-width:1100px){.home-start{grid-template-columns:minmax(0,.95fr) minmax(300px,1fr)}.task-launcher{padding:22px}.building-canvas{height:380px}.building-foot{flex-wrap:wrap}.building-toolbar{padding:16px}.building-toolbar>span{font-size:15px}.task-launch-heading h2{font-size:21px}.task-launch-heading{flex-wrap:wrap}.task-launch-heading .badge{margin-left:0}}@media(max-width:720px){.home-start{grid-template-columns:1fr}.task-launcher{grid-row:1}.building-workspace{grid-row:2}.home-shortcuts{grid-row:3}.building-canvas{height:300px}.home-shortcuts{grid-template-columns:1fr}.task-launcher{padding:22px}.home-shortcuts>a{padding:17px}.task-launch-heading .badge{margin-left:auto}}
.stat-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  background: var(--line);
  margin-bottom: 16px;
  margin-top: 16px;
}
.mini-stat {
  background: var(--panel-2);
  padding: 12px 15px;
}
.mini-stat .stat {
  font-size: 20px;
}
.workspace {
  overflow: hidden;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.tool-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tool-select {
  height: 32px;
  width: 200px;
  font-size: 11.5px;
  padding-left: 9px;
}
.search-box {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0 9px;
  background: var(--panel-2);
  min-width: 240px;
  flex: 1;
  max-width: 380px;
}
.search-input {
  border: none;
  background: transparent;
  height: 32px;
  padding: 0;
  font-size: 11.5px;
}
.search-input:focus {
  box-shadow: none;
}
.scope-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 15px;
  font-size: 11px;
  color: var(--amber);
  background: rgba(251, 191, 36, 0.055);
  border-bottom: 1px solid rgba(251, 191, 36, 0.16);
}
.preview-scope {
  padding: 9px 15px;
  border-bottom: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
  line-height: 1.6;
}
.bim-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 344px;
  min-height: 620px;
}
.canvas-panel {
  position: relative;
  min-height: 620px;
  border-right: 1px solid var(--line);
}
.canvas-overlay {
  position: absolute;
  inset: 14px 14px auto 14px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  pointer-events: none;
}
.canvas-chip {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--text-soft);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 5px 8px;
  backdrop-filter: blur(8px);
}
.live-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--teal);
  box-shadow: 0 0 8px var(--teal);
  animation: pulse 1.8s ease-in-out infinite;
}
.canvas-legend {
  display: flex;
  gap: 11px;
  align-items: center;
  font-size: 11px;
  color: var(--muted);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 5px 9px;
}
.canvas-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.swatch {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.swatch.slab { background: #0e7490; }
.swatch.wall { background: #2b4058; }
.swatch.risk { background: #7f1d1d; border: 1px solid #fb7185; }
.swatch.ev { background: #fbbf24; border-radius: 50%; }
.canvas-loading {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 11px;
  color: var(--muted);
}
.inspector {
  padding: 16px;
  overflow-y: auto;
  max-height: 680px;
}
.inspector-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
.inspector-title {
  font-size: 13.5px;
  font-weight: 600;
  margin-top: 4px;
  max-width: 230px;
  line-height: 1.4;
}
.guid-line {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 10px 0 12px;
  padding: 7px 8px;
  border-radius: 7px;
  background: var(--panel-2);
  border: 1px solid var(--line);
  font-size: 11px;
  color: var(--teal);
}
.guid-line .mono {
  flex: 1;
  min-width: 0;
}
.inspector-actions {
  display: flex;
  gap: 7px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.inspector-section {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}
.inspector-section .section-title {
  margin-bottom: 10px;
}
.evidence-mini {
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
  background: var(--panel-2);
}
.evidence-mini img {
  width: 100%;
  height: 110px;
  object-fit: cover;
  display: block;
  opacity: 0.88;
}
.evidence-mini-body {
  padding: 10px;
}
.obs-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.obs-grid .chip {
  font-size: 11px;
  padding: 2px 6px;
}
.table-card {
  margin-top: 16px;
  overflow: hidden;
}
.name-cell {
  max-width: 440px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.table-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}
.divider-v {
  width: 1px;
  height: 12px;
  background: var(--line);
}
@media (max-width: 1180px) {
  .bim-grid {
    grid-template-columns: 1fr;
  }
  .canvas-panel {
    border-right: none;
    border-bottom: 1px solid var(--line);
  }
  .inspector {
    max-height: none;
  }
  .stat-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 600px) {
  .page-head { gap: 10px; margin-bottom: 12px; }
  .page-head h1 { font-size: 23px; }
  .page-head .eyebrow, .page-head .sub, .head-actions > .badge { display: none; }
  .head-actions { gap: 8px; }
  .toolbar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; padding: 10px; }
  .tool-group { min-width: 0; }
  .tool-select { width: 100%; min-width: 0; }
  .search-box { grid-column: 1 / -1; min-width: 0; max-width: none; }
  .preview-scope { font-size: 11px; padding: 7px 10px; }
  .canvas-panel { height: clamp(300px, 55vh, 480px); min-height: 300px; }
  .canvas-panel :deep(.viewer-shell) { min-height: 300px; }
  .canvas-overlay { inset: 10px 10px auto; }
  .canvas-legend { display: none; }
}
</style>
