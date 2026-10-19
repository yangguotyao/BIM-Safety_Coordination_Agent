<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  Box,
  ChevronLeft,
  ChevronRight,
  Copy,
  Crosshair,
  Eye,
  Layers,
  Loader2,
  MapPin,
  Maximize2,
  RefreshCw,
  Ruler,
  Search,
  ShieldAlert,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-vue-next'
import BimViewer from '../components/BimViewer.vue'
import EmptyState from '../components/EmptyState.vue'
import { api } from '../api'
import type { ElementRow, Evidence, MeshData, MeshPayload } from '../types'
import { errorMessage, store, toast } from '../store'
import { formatNumber, observationLabel, observationValue, shortGuid } from '../utils'

const MODEL_ID = 'S1-bSDD-example'
const TARGET_GUID = '0FOHK4aT910wgskSbVHn0U'
const INDEXED_STOREY = '1Vhy2b2Mj9FRewx9CZZoux'

const route = useRoute()
const viewerRef = ref<InstanceType<typeof BimViewer> | null>(null)
const meshPayload = ref<MeshPayload | null>(null)
const storeys = ref<any[]>([])
const elements = ref<ElementRow[]>([])
const total = ref(0)
const detail = ref<ElementRow | null>(null)
const evidence = ref<Evidence | null>(null)
const selectedGuid = ref(TARGET_GUID)
const riskHighlight = ref(true)
const loadingMesh = ref(true)
const loadingTable = ref(false)
const loadingDetail = ref(false)
const loadingGeometry = ref(false)
const error = ref('')
const scopeNote = ref('')

const filters = reactive({
  storey: INDEXED_STOREY,
  ifcClass: '',
  q: '',
  page: 0,
  limit: 18,
})

const zone = computed(() => (meshPayload.value?.zone || {}) as Record<string, any>)
const evidencePoint = computed<number[] | null>(() => {
  if (!evidence.value) return null
  const point = zone.value.worker_point_m
  return Array.isArray(point) ? point : null
})
const evidenceLabel = computed(() => (evidence.value ? `${evidence.value.evidence_id} · 模拟人员位置` : ''))
const isRiskEvidence = computed(() => {
  if (!evidence.value) return false
  const observation = evidence.value.observation || {}
  const state = observation.guardrail_state
  const height = observation.guardrail_height_m
  return state === 'absent' || (state === 'present' && typeof height === 'number' && height < 1.2)
})
const riskGuids = computed(() => (riskHighlight.value && isRiskEvidence.value ? [TARGET_GUID] : []))
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
    scopeNote.value = response.loaded_scope?.note || ''
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
    const response = await api.get<{ evidence: Evidence }>(`/evidence/${id}`)
    evidence.value = response.evidence
    selectedGuid.value = TARGET_GUID
    await loadDetail(TARGET_GUID)
    await nextTick()
    viewerRef.value?.focusGuid(TARGET_GUID)
  } catch (err: any) {
    toast(errorMessage(err), 'error')
  }
}

async function selectElement(guid: string) {
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
  toast('正在从原始 IFC 按需提取几何；首次打开约需 10–20 秒。', 'info', 7000)
  try {
    const response = await api.get<{ mesh: MeshData }>(
      `/models/${MODEL_ID}/elements/${encodeURIComponent(detail.value.guid)}/mesh`,
    )
    if (meshPayload.value) {
      meshPayload.value.meshes.push(response.mesh)
    }
    await nextTick()
    viewerRef.value?.addMesh(response.mesh)
    viewerRef.value?.focusGuid(detail.value.guid)
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

function onStoreyChange() {
  filters.page = 0
  loadElements()
}

function onClassChange() {
  filters.page = 0
  loadElements()
}

watch(
  () => route.query.evidence,
  (id) => {
    if (typeof id === 'string' && id) selectEvidenceById(id)
  },
)

onMounted(async () => {
  await Promise.all([loadMesh(), loadStoreys()])
  await loadElements()
  const queryEvidence = typeof route.query.evidence === 'string' ? route.query.evidence : 'EV-001'
  await selectEvidenceById(queryEvidence)
})
</script>

<template>
  <div class="page bim-page">
    <div class="page-head">
      <div>
        <div class="eyebrow">BIM WORKSPACE · REAL IFC GEOMETRY</div>
        <h1>三维工作台</h1>
        <p class="sub">
          真实 S1 IFC 板与墙几何、1,247 个 05 层构件索引与模拟检查区叠加。首屏 35 个对象是区域预览，不是模型全量。
        </p>
      </div>
      <div class="head-actions">
        <span class="badge tone-teal"><ShieldCheck :size="12" /> 真实构件</span>
        <span class="badge tone-amber"><TriangleAlert :size="12" /> 模拟观察</span>
        <button class="btn btn-sm" @click="resetView"><Maximize2 :size="14" /> 重置视角</button>
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
        <div class="stat-label">首屏网格</div>
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
        <div class="stat">{{ zone.drop_height_m || 2.5 }}<span class="stat-unit">m</span></div>
        <div class="stat-label">演示坠落高度</div>
      </div>
    </div>

    <div class="workspace card">
      <div class="toolbar">
        <div class="tool-group">
          <Layers :size="14" class="dim" />
          <select class="select tool-select" :value="filters.storey" @change="onStoreyChange">
            <option v-for="item in storeys" :key="item.guid" :value="item.guid">
              {{ item.name }} · {{ item.element_count }} 构件
            </option>
          </select>
        </div>
        <div class="tool-group">
          <Box :size="14" class="dim" />
          <select class="select tool-select" :value="filters.ifcClass" @change="onClassChange">
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

      <div v-if="scopeNote" class="scope-note">
        <TriangleAlert :size="13" />
        {{ scopeNote }}
      </div>

      <div class="bim-grid">
        <div class="canvas-panel">
          <BimViewer
            ref="viewerRef"
            :meshes="meshPayload?.meshes || []"
            :target-guid="TARGET_GUID"
            :risk-guids="riskGuids"
            :selected-guid="selectedGuid"
            :evidence-point="evidencePoint"
            :evidence-label="evidenceLabel"
            @select="selectElement"
          />
          <div class="canvas-overlay">
            <div class="canvas-chip mono">
              <span class="live-dot" /> {{ meshPayload?.meshes.length || 35 }} / 1247 OBJECTS
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
              <div class="caption">SELECTED ELEMENT</div>
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
                <span v-if="selectedInPreview" class="badge tone-teal">预提取网格</span>
                <span v-else class="badge tone-amber">未加载 · 可按需提取</span>
              </span>
            </div>
            <div class="inspector-actions">
              <button class="btn btn-sm" :disabled="!selectedInPreview" @click="viewerRef?.focusGuid(detail.guid)">
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
            <div class="notice" style="margin-top: 10px">
              <Ruler :size="13" />
              <span>单位统一为米。前端仅做局部原点平移，后端保留原世界坐标与 GUID 映射。</span>
            </div>
          </template>

          <div class="inspector-section">
            <div class="section-title">CURRENT EVIDENCE</div>
            <div v-if="evidence" class="evidence-mini">
              <img :src="evidence.image_url" :alt="evidence.label" />
              <div class="evidence-mini-body">
                <div class="row" style="justify-content: space-between">
                  <span class="mono small">{{ evidence.evidence_id }}</span>
                  <span class="badge tone-amber">演示示意图</span>
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
            <EmptyState v-else title="未选择证据" detail="从证据库选择一条证据，可在三维中定位模拟人员位置。" />
          </div>

          <div class="inspector-section">
            <div class="section-title">ZONE & METHOD</div>
            <div class="kv">
              <span class="k">区域</span><span class="v mono">{{ zone.zone_id || 'ZONE-S1-L05-EDGE' }}</span>
              <span class="k">边线来源</span><span class="v">真实板投影 + 人工标注</span>
              <span class="k">人员点</span><span class="v mono">{{ zone.worker_point_provenance || 'simulated' }}</span>
              <span class="k">暴露阈值</span><span class="v">1.0 m（演示策略）</span>
            </div>
            <div class="notice warn" style="margin-top: 9px">
              <MapPin :size="13" />
              <span>
                标注板边不自动等于真实临空面；2.5 m 是演示坠落高度假设，17.3 m 是世界 Z 高程，二者不可等同。
              </span>
            </div>
          </div>
        </aside>
      </div>
    </div>

    <div class="card table-card">
      <div class="card-head">
        <div class="card-title"><Layers :size="15" /> 05 层构件索引 <span class="badge tone-slate">{{ formatNumber(total) }}</span></div>
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
              <td colspan="5"><EmptyState title="该筛选无构件" detail="切换楼层、类别或清空搜索；当前首版只为 05 层建立索引。" /></td>
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

    <div v-if="error" class="card" style="margin-top: 16px; padding: 18px; border-color: rgba(251,113,133,.35)">
      <div class="row" style="color: var(--red)"><TriangleAlert :size="16" /> {{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.bim-page {
  max-width: 1780px;
}
.stat-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  background: var(--line);
  margin-bottom: 16px;
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
</style>
