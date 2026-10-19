<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertTriangle, ArrowLeft, Box, ArrowRight, BadgeCheck, CalendarClock, Check, CheckCircle2, ClipboardCheck, Clock, ExternalLink, FileJson, FileText, History, ImagePlus, Info, Loader2, Lock, MapPin, Plus, RefreshCw, RotateCcw, ShieldCheck, Sparkles, Upload, UserCheck, XCircle } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import Modal from '../components/Modal.vue'
import StatusBadge from '../components/StatusBadge.vue'
import TaskWorkspace from '../components/TaskWorkspace.vue'
import CaseProgress from '../components/CaseProgress.vue'
import EvidenceReview from '../components/EvidenceReview.vue'
import ModelCalls from '../components/ModelCalls.vue'
import CaseWorkspace from '../components/CaseWorkspace.vue'
import AgentAnalysisPanel from '../components/AgentAnalysisPanel.vue'
import AgentAssurancePanel from '../components/AgentAssurancePanel.vue'
import RectificationPanel from '../components/RectificationPanel.vue'
import { api } from '../api'
import { errorMessage, refreshSummary, toast } from '../store'
import type { CaseBundle, CaseEvent, Evidence, Run, Rule } from '../types'
import {
  demoTime,
  eventLabel,
  formatDateTime,
  formatTime,
  resultLabel,
  shortGuid,
  statusLabel,
  statusTone,
} from '../utils'

const route = useRoute()
const router = useRouter()
const bundle = ref<CaseBundle | null>(null)
const loading = ref(true)
const busy = ref('')
const activeTab = ref('overview')
const runDetail = ref<Run | null>(null)
const allEvidence = ref<Evidence[]>([])
const evidenceModal = ref(false)
const selectedEvidenceIds = ref<string[]>([])
const uploadFile = ref<File | null>(null)
const uploadRef = ref<HTMLInputElement | null>(null)
const uploadStage = ref('before')
const uploadCapturedAt = ref('')
const pollTimer = ref<number | undefined>(undefined)
const loadedCaseId = ref('')
const taskPanelOpen = ref(false)
const taskPanelElement = ref<HTMLDetailsElement | null>(null)
const workArea = ref<HTMLDivElement | null>(null)
const analysisArea=ref<HTMLDivElement|null>(null)
const workspace=ref<InstanceType<typeof CaseWorkspace>|null>(null)

const reviewForm = reactive({
  decision: 'approve',
  reviewer: '演示安全员',
  comment: '',
  reviewed_at: '',
  control_version: 0,
  newAction: '',
  minHeight: 1.2,
  manualRequirements: '',
})
const reopenForm = reactive({
  reason: '新证据显示条件变化，需要重新检查。',
  evidenceIds: [] as string[],
})

const caseData = computed(() => bundle.value?.case || null)
const evidence = computed(() => (bundle.value?.evidence || []).map(item => ({
  ...item, image_url: item.image_url || `/api/files/evidence/${encodeURIComponent(item.evidence_id)}`,
})))
const rules = computed(() => bundle.value?.rules || [])
const events = computed(() => bundle.value?.events || [])
const runs = computed(() => bundle.value?.runs || [])
const latestRun = computed<Run | null>(() => runDetail.value || runs.value[0] || null)
const finding = computed(() => caseData.value?.findings?.find(f=>f.result==='risk_candidate') || caseData.value?.findings?.[0] || null)
const controls = computed(() => caseData.value?.controls || [])
const controlLabels: Record<string,string> = { proposed:'待审核', approved:'已批准', implementing:'实施中', verified:'已复核',superseded:'已失效' }
const observationLabels: Record<string,string> = { guardrail_state:'临边防护', guardrail_height_m:'防护高度', worker_present:'人员在场', drop_height_m:'坠落高度假设' }
function observationText(key: string, value: unknown) {
  if (value == null || value === 'unknown') return '待确认'
  if (value === true || value === false) return value ? '是' : '否'
  if (key.endsWith('_m')) return `${value} m`
  return value === 'present' ? '已设置' : value === 'absent' ? '未设置' : String(value)
}
const acceptedCriteria = computed(() => Object.values(caseData.value?.review?.verification_snapshot || {}).length
  ? Object.values(caseData.value!.review!.verification_snapshot!)
  : controls.value.flatMap(c => c.verification_criteria ? [c.verification_criteria] : []))
const manualRequirements = computed(() => acceptedCriteria.value.flatMap(c => c.manual_requirements || []))
const criteriaLabel=computed(()=>[
  acceptedCriteria.value.some(c=>c.guardrail_required) ? `栏杆高度 ≥ ${Math.max(...acceptedCriteria.value.filter(c=>c.guardrail_required).map(c=>c.min_height_m))} m，防护固定且连续` : '',
  acceptedCriteria.value.some(c=>c.coordination_required) ? '活动时空冲突已消除' : '',
].filter(Boolean).join('；'))

function applyWorkspaceBundle(value:CaseBundle) {
  bundle.value=value
  reviewForm.newAction=''
  refreshSummary()
}
const isAnalyzing = computed(() => caseData.value?.status === 'analyzing')
const canAnalyze = computed(() => ['draft', 'needs_evidence', 'reopened'].includes(caseData.value?.status || ''))
const canReview = computed(() => caseData.value?.status === 'pending_review')
const canImplement = computed(() => caseData.value?.status === 'approved')
const canVerify = computed(() => caseData.value?.status === 'pending_verification')
const canReopen = computed(() => caseData.value?.status === 'closed')
const afterEvidence = computed(() => evidence.value.filter((item) => item.stage === 'after'))
const pendingObservation = computed(() => evidence.value.some(item => item.source==='upload' && item.stage==='before' && !item.perception?.confirmed))
const pendingAfterObservation = computed(() => afterEvidence.value.some(item=>item.source==='upload' && !item.perception?.confirmed))
const pendingText=computed(()=>!!bundle.value?.site_text && !bundle.value.site_text.complete)
const pendingPlan=computed(()=>bundle.value?.coordination?.configured && !bundle.value.coordination.complete)
const planHasConflicts=computed(()=>!!bundle.value?.coordination?.conflicts.length)
const analysisFailed = computed(() => runDetail.value?.status==='failed')
const availableEvidence = computed(() =>
  allEvidence.value.filter((item) => !(caseData.value?.evidence_ids || []).includes(item.evidence_id))
    .filter(item => item.zone_id===caseData.value?.zone_id && (caseData.value?.bim_guids || []).every(guid=>item.bim_guids.includes(guid)))
    .filter(item => !['rectifying','pending_verification'].includes(caseData.value?.status || '') || item.stage === 'after')
    .sort((a,b) => Number(b.evidence_id === 'EV-010') - Number(a.evidence_id === 'EV-010')),
)
const nextStep = computed(() => ({
  draft: { title:'检查资料已准备好', detail:'开始分析，关联区域构件、现场证据和规范依据。', action:'开始分析' },
  analyzing: { title:'Agent 正在分析现场风险', detail:'正在校核模型、作业时间、证据与规范，结果完成后会自动显示。', action:'' },
    needs_evidence: { title:analysisFailed.value ? '本次分析未完成，请查看原因后重试' : pendingObservation.value ? '请先确认新证据的现场观察' : pendingText.value ? '现场文本待澄清' : pendingPlan.value ? '活动资料待补充' : '核对缺失项并继续分析', detail:'', action:analysisFailed.value ? '重试分析' : pendingObservation.value ? '确认现场观察' : pendingText.value ? '核对现场文本' : pendingPlan.value ? '补齐活动计划' : !evidence.value.some(e=>e.stage==='before') ? '添加现场资料' : '继续风险分析' },
  pending_review: { title:controls.value.length ? '分析已完成，等待人工审核' : '检查结果待人工确认', detail:controls.value.length ? '先查看风险与依据，再确认候选措施和验收要求。' : '本次检查项未发现问题。人工确认后可完成检查，无需整改。', action:controls.value.length ? '审核控制措施' : '确认检查结果' },
  approved: { title:planHasConflicts.value ? '请按批准措施调整作业计划' : '整改措施已批准，下一步完成隐患整改', detail:'', action:planHasConflicts.value ? '调整作业计划' : '提交隐患整改' },
  rectifying: { title:'请补充整改后的复核资料', detail:'选择晚于实施时刻、属于同一区域的证据，用于后续复核。', action:'提交整改资料' },
  pending_verification: { title:pendingAfterObservation.value ? '请确认整改后新证据的观察' : '整改后证据已提交，等待复核', detail:'核对图像候选与人工量测，再按已批准版本的要求复核。', action:pendingAfterObservation.value ? '核对整改后观察' : '复核这次整改' },
  closed: { title:'本次检查已完成闭环', detail:controls.value.length ? '分析、审批、实施与复核记录均已保存，可导出报告。' : '检查结果已由人工确认，本次无需整改，可导出报告。', action:'导出检查报告' },
  reopened: { title:'本次检查需要重新处理', detail:'先查看复核失败或条件变化的原因，再补充资料并重新分析。', action:'重新分析' },
  rejected: { title:'措施未获批准，请调整检查任务', detail:'保留审核意见，根据要求补充资料或重新组织检查。', action:'调整检查任务' },
}[caseData.value?.status || 'draft']))

async function nextAction() {
  if (!caseData.value || busy.value) return
  if (caseData.value.status==='needs_evidence' && analysisFailed.value) {await analyze();return}
  if (caseData.value.status === 'needs_evidence' && pendingObservation.value) { await showTab('evidence'); return }
  const coordinationPanel=caseData.value.status==='needs_evidence' ? pendingText.value ? 'text' : pendingPlan.value ? 'activities' : '' : canImplement.value && planHasConflicts.value ? 'activities' : ''
  if(coordinationPanel) {activeTab.value='overview';await nextTick();await workspace.value?.openPanel(coordinationPanel);return}
  if (caseData.value.status === 'pending_verification' && pendingAfterObservation.value) { await showTab('verify'); return }
  if(caseData.value.status==='needs_evidence' && !evidence.value.some(e=>e.stage==='before')) {evidenceModal.value=true;return}
  if (canAnalyze.value) { await analyze(); return }
  if (canReview.value) { await showTab('review'); return }
  if (canImplement.value || canVerify.value) { await showTab('verify'); return }
  if (caseData.value.status === 'rectifying') { await showTab('verify'); return }
  if (caseData.value.status === 'closed') { await exportCase('docx'); return }
  activeTab.value = 'overview'
  taskPanelOpen.value = true
  await nextTick()
  taskPanelElement.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function showTab(tab: string) {
  activeTab.value = tab
  await nextTick();
  (tab==='overview' ? analysisArea.value : workArea.value)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
async function assuranceTarget(target:string){
  if(target==='knowledge'){router.push('/knowledge');return}
  if(target==='activities' || target==='text'){
    await showTab('overview');await nextTick();workspace.value?.openPanel(target);return
  }
  await showTab(target)
}
const branchNotice = computed(() => {
  const status = caseData.value?.status
    if (status === 'needs_evidence') return { tone: 'amber', text: analysisFailed.value ? '模型或工具调用未完成，已保留现场资料；请重试分析，或查看运行记录。' : '分析发现关键证据或字段不足，案例进入“待补证”；补齐后需重新分析，不能直接关闭。' }
  if (status === 'reopened') return { tone: 'rose', text: '案例已重新打开；此前的 closed / verification 事件保留，不会被覆盖。' }
  if (status === 'rejected') return { tone: 'red', text: '审核已拒绝该演示控制方案；案例不会进入整改或关闭。' }
  return null
})

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const response = await api.get<CaseBundle>(`/cases/${route.params.id}`)
    bundle.value = response
    if (loadedCaseId.value !== response.case.case_id) {
      loadedCaseId.value = response.case.case_id
      activeTab.value = ['approved','rectifying','pending_verification','closed'].includes(response.case.status) ? 'verify' : 'overview'
      taskPanelOpen.value = false
    }
    if (!reviewForm.reviewed_at) reviewForm.reviewed_at = demoTime(response.case.as_of, 10)
    const controlChanged=reviewForm.control_version!==response.case.control_version
    reviewForm.control_version = response.case.control_version
    if ((!reviewForm.newAction || controlChanged) && response.case.controls[0]) {
      reviewForm.newAction = response.case.controls[0].action
      reviewForm.minHeight = response.case.controls[0].verification_criteria?.min_height_m || 1.2
    }
    const latest = response.runs[0]
    if (latest) {
      try {
        const run = await api.get<{ run: Run }>(`/runs/${latest.run_id}`)
        runDetail.value = run.run
      } catch {
        runDetail.value = null
      }
    }
    if (response.case.status === 'analyzing') startPolling()
    else stopPolling()
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

async function loadAllEvidence() {
  try {
    const response = await api.get<{ rows: Evidence[] }>('/evidence')
    allEvidence.value = response.rows
  } catch {
    allEvidence.value = []
  }
}

function startPolling() {
  if (pollTimer.value) return
  pollTimer.value = window.setInterval(() => load(true), 1500)
}

function stopPolling() {
  if (pollTimer.value) {
    window.clearInterval(pollTimer.value)
    pollTimer.value = undefined
  }
}

async function analyze() {
  if (!caseData.value || busy.value) return
  busy.value = 'analyze'
  try {
    await api.post(`/cases/${caseData.value.case_id}/analyze`)
    toast('分析已启动，Agent 正在写入实际 trace。', 'success')
    await load()
    activeTab.value = 'overview'
    await refreshSummary()
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    busy.value = ''
  }
}

async function submitReview(decisionOverride?: string) {
  if (!caseData.value || busy.value) return
  const decision = decisionOverride || reviewForm.decision
  busy.value = 'review'
  try {
    const payload: any = {
      decision,
      reviewer: reviewForm.reviewer,
      comment: reviewForm.comment,
      reviewed_at: reviewForm.reviewed_at,
      control_version: reviewForm.control_version,
      expected_case_version: caseData.value.version,
    }
    if (decision === 'modify') {
      const current = controls.value[0]
      if (!reviewForm.newAction.trim()) {
        toast('请填写修改后的控制措施', 'warning')
        return
      }
      payload.new_controls = [
        {
          control_id: current?.control_id,
          finding_id: current?.finding_id || finding.value?.finding_id,
          action: reviewForm.newAction.trim(),
          owner: current?.owner || '演示机电班组',
          verification_requirements: current?.verification_requirements || [],
          verification_criteria: {
            ...current?.verification_criteria,
            guardrail_required:current?.verification_criteria?.guardrail_required ?? true,min_height_m: reviewForm.minHeight,
            fixed_required:current?.verification_criteria?.fixed_required ?? true,continuous_required:current?.verification_criteria?.continuous_required ?? true,
            manual_requirements: reviewForm.manualRequirements.split('\n').map(s => s.trim()).filter(Boolean),
          },
        },
        ...controls.value.slice(1),
      ]
    }
    const response = await api.post<CaseBundle>(`/cases/${caseData.value.case_id}/review`, payload)
    bundle.value = response
    reviewForm.control_version = response.case.control_version
    if (decision === 'modify') reviewForm.decision = 'approve'
    toast(decision === 'approve' ? '已记录人工批准。' : decision === 'reject' ? '已记录拒绝。' : '控制措施已更新，等待重新审核。', 'success')
    await refreshSummary()
    if (decision === 'approve') await showTab('verify')
  } catch (error: any) {
    toast(errorMessage(error), 'error', 7000)
  } finally {
    busy.value = ''
  }
}

async function addEvidence(ids: string[]) {
  if (!caseData.value || busy.value) return
  if (!ids.length) {
    toast('请选择至少一条证据', 'warning')
    return
  }
  busy.value = 'evidence'
  try {
    const response = await api.post<CaseBundle>(`/cases/${caseData.value.case_id}/evidence`, {
      evidence_ids: ids,
      actor: '演示安全员',
    })
    bundle.value = response
    selectedEvidenceIds.value = []
    evidenceModal.value = false
    if (response.case.status === 'pending_verification') await showTab('verify')
    toast('证据已追加到案例。', 'success')
  } catch (error: any) {
    toast(errorMessage(error), 'error', 7000)
  } finally {
    busy.value = ''
  }
}

async function uploadEvidence() {
  if (!caseData.value || !uploadFile.value || busy.value) return
  busy.value = 'upload'
  try {
    const data = new FormData()
    data.append('file', uploadFile.value)
    data.append('captured_at', uploadCapturedAt.value)
    data.append('stage', uploadStage.value)
    data.append('note', uploadFile.value.name)
    const response = await api.postForm<CaseBundle>(`/cases/${caseData.value.case_id}/evidence/upload`, data)
    bundle.value = response
    uploadFile.value = null
    if (uploadRef.value) uploadRef.value.value = ''
    evidenceModal.value = false
    await showTab('evidence')
    toast('新证据已保存。可用 Qwen 分析图片，再确认现场观察。', 'success', 6000)
  } catch (error: any) {
    toast(errorMessage(error), 'error', 7000)
  } finally {
    busy.value = ''
  }
}

async function submitReopen() {
  if (!caseData.value || busy.value) return
  if (!reopenForm.evidenceIds.length) {
    toast('请选择条件变化的新证据', 'warning')
    return
  }
  busy.value = 'reopen'
  try {
    const response = await api.post<CaseBundle>(`/cases/${caseData.value.case_id}/reopen`, {
      reason: reopenForm.reason,
      evidence_ids: reopenForm.evidenceIds,
      actor: '演示安全员',
    })
    bundle.value = response
    toast('案例已重新打开，closed 事件保留。', 'success')
    await refreshSummary()
    activeTab.value = 'overview'
  } catch (error: any) {
    toast(errorMessage(error), 'error', 7000)
  } finally {
    busy.value = ''
  }
}

async function exportCase(format: 'json' | 'docx') {
  if (!caseData.value) return
  try {
    await api.download(`/cases/${caseData.value.case_id}/export?format=${format}`, `${caseData.value.case_id}.${format}`)
    toast('导出已开始。', 'success')
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  }
}

function toggleReopenEvidence(id: string) {
  if (reopenForm.evidenceIds.includes(id)) {
    reopenForm.evidenceIds = reopenForm.evidenceIds.filter((item) => item !== id)
  } else {
    reopenForm.evidenceIds = [...reopenForm.evidenceIds, id]
  }
}

function toggleSelectedEvidence(id: string) {
  if (selectedEvidenceIds.value.includes(id)) {
    selectedEvidenceIds.value = selectedEvidenceIds.value.filter((item) => item !== id)
  } else {
    selectedEvidenceIds.value = [...selectedEvidenceIds.value, id]
  }
}

function onUploadChange(event: Event) {
  const target = event.target as HTMLInputElement
  uploadFile.value = target.files?.[0] || null
}

function openBim(evidenceId: string) {
  router.push({ path: '/', query: evidenceId ? { evidence: evidenceId } : { guid:caseData.value?.bim_guids[0] } })
}

function observationSaved(response:CaseBundle) { bundle.value=response; refreshSummary() }
watch(evidenceModal, open => {
  if (!open || !caseData.value) return
  uploadStage.value = ['rectifying','pending_verification','approved'].includes(caseData.value.status) ? 'after' : 'before'
  uploadCapturedAt.value = uploadStage.value==='before' ? caseData.value.as_of : demoTime(caseData.value.implementation?.implemented_at || caseData.value.as_of, caseData.value.implementation ? 10 : 30)
})

function verificationName(name:string) {return name.replace('已记录人工实施','整改记录已提交').replace('人工实施时刻','整改完成时刻')}
function verificationSource(source:string='') {return ({'cases.implementation':'整改记录','evidence.perception':'确认观察','evidence_check':'资料关联校核','after 证据观察':'整改后观察','verify 请求':'复核人确认'} as Record<string,string>)[source] || source}

function checkTone(result: string) {
  if (result === 'pass') return 'tone-green'
  if (result === 'fail') return 'tone-red'
  return 'tone-amber'
}

watch(
  () => route.params.id,
  () => {
    stopPolling()
    load()
    loadAllEvidence()
  },
)

onMounted(() => {
  load()
  loadAllEvidence()
})
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="page detail-page">
    <div v-if="loading" class="card loading-block">
      <Loader2 :size="18" class="spin" />
      <span>读取 Safety Case…</span>
    </div>

    <template v-else-if="caseData">
      <div class="detail-head">
        <div class="detail-title-wrap">
          <router-link class="back-link" to="/cases"><ArrowLeft :size="13" /> 返回检查记录</router-link>
          <div class="title-row">
            <h1>{{ caseData.title }}</h1>
            <StatusBadge :status="caseData.status" dot />
          </div>
          <div class="detail-meta">
            <span>S1 建设项目 · {{ bundle?.context?.zone.storey_name || '05 层板边' }}</span><span class="sep">·</span>
            <span><CalendarClock :size="12" /> {{ formatDateTime(caseData.as_of) }}</span>
          </div>
        </div>
        <div class="head-actions">
          <button class="btn btn-sm" @click="load()"><RefreshCw :size="13" /> 刷新</button>
          <button class="btn btn-sm" @click="exportCase('docx')"><FileText :size="13" /> 导出报告</button>
          <details class="head-more"><summary>更多</summary><button class="btn btn-sm" @click="exportCase('json')"><FileJson :size="13" /> 导出 JSON</button><div class="small muted">{{ caseData.case_id }} · v{{ caseData.version }}<br />{{ caseData.model_id }} @ {{ caseData.model_version }}</div></details>
        </div>
      </div>

      <CaseProgress :status="caseData.status" :no-rectification="caseData.status === 'closed' && controls.length === 0" interactive @select="showTab($event)" />
      <section v-if="nextStep" class="current-work" :class="{ completed: caseData.status === 'closed' }"><span class="current-work-icon"><CheckCircle2 v-if="caseData.status === 'closed'" :size="23" /><Loader2 v-else-if="isAnalyzing" :size="23" class="spin" /><ClipboardCheck v-else :size="23" /></span><div><span class="current-work-label">{{ caseData.status === 'closed' ? '检查结果' : '当前待办' }}</span><h2>{{ nextStep.title }}</h2></div><button v-if="nextStep.action" class="btn btn-primary" :disabled="Boolean(busy)" @click="nextAction">{{ nextStep.action }} <ArrowRight :size="15" /></button><span v-else class="badge tone-blue">正在分析</span></section>

      <div v-if="analysisFailed && caseData.status==='needs_evidence'" class="notice danger" style="margin:14px 0"><AlertTriangle :size="16" /><span>{{ runDetail?.error }}</span><router-link class="btn btn-sm" :to="`/agent?run=${caseData.last_run_id}`">查看运行记录</router-link></div>
      <div v-if="branchNotice" class="branch-banner" :class="`branch-${branchNotice.tone}`">
        <AlertTriangle :size="14" />
        <span>{{ branchNotice.text }}</span>
      </div>

      <div v-if="(['overview','evidence'].includes(activeTab) || isAnalyzing) && bundle" ref="analysisArea"><AgentAnalysisPanel :bundle="bundle" :run="latestRun" @completed="load(true)" /><AgentAssurancePanel :bundle="bundle" :run="latestRun" @updated="load(true)" @navigate="assuranceTarget" /></div>
      <div ref="workArea" class="case-section-navigation">          <div class="tabs card">
            <button class="tab" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">协同工作台</button>
            <button class="tab" :class="{ active: activeTab === 'evidence' }" @click="activeTab = 'evidence'">
              现场资料 <span class="tab-count">{{ evidence.length }}</span>
            </button>
            <button class="tab" :class="{ active: activeTab === 'review' }" @click="activeTab = 'review'">
              审核与措施 <span v-if="canReview" class="tab-alert" />
            </button>
            <button class="tab" :class="{ active: activeTab === 'verify' }" @click="activeTab = 'verify'">整改与复核</button>
            <button class="tab" :class="{ active: activeTab === 'events' }" @click="activeTab = 'events'">
              处置记录 <span class="tab-count">{{ events.length }}</span>
            </button>
          </div></div>
      <CaseWorkspace v-if="activeTab==='overview' && bundle" ref="workspace" :bundle="bundle" :run="latestRun" @updated="applyWorkspaceBundle" />
      <div class="detail-grid" :class="{'workspace-active':activeTab==='overview'}">
        <div class="detail-main">
          <div v-if="acceptedCriteria.length && ['review','verify'].includes(activeTab)" class="notice" style="margin: 14px 0; padding: 14px">
            <ShieldCheck :size="16" /><span>验收要求 · 控制版本 v{{ caseData.control_version }}：{{ criteriaLabel }}。{{ manualRequirements.length ? `另有 ${manualRequirements.length} 项人工确认要求。` : '' }}</span>
          </div>
          <div v-if="activeTab === 'overview'" class="tab-panel">
            <div class="card controls-card">
              <div class="card-head">
                <div class="card-title"><ShieldCheck :size="15" /> 控制措施 <span class="badge tone-slate">v{{ caseData.control_version }}</span></div>
                <span class="badge" :class="caseData.review ? `tone-${caseData.review.decision === 'approve' ? 'green' : caseData.review.decision === 'reject' ? 'red' : 'violet'}` : 'tone-slate'">
                  {{ caseData.review ? (caseData.review.decision === 'approve' ? '已批准' : caseData.review.decision === 'reject' ? '已拒绝' : '已修改') : '待审核' }}
                </span>
              </div>
              <div class="card-body">
                <div v-if="controls.length" class="control-list">
                  <div v-for="control in controls" :key="control.control_id" class="control-item">
                    <div class="control-top">
                      <span :title="control.control_id">控制措施 · v{{ control.version }}</span>
                      <span class="badge tone-slate">{{ controlLabels[control.status] || control.status }}</span>
                    </div>
                    <p>{{ control.action }}</p>
                    <div class="control-meta">
                      <span><UserCheck :size="12" /> {{ control.owner }}</span>
                      <span><ClipboardCheck :size="12" /> {{ control.verification_requirements?.length || 0 }} 项验证要求</span>
                    </div>
                    <ul v-if="control.verification_requirements?.length" class="req-list">
                      <li v-for="req in control.verification_requirements" :key="req">{{ req }}</li>
                    </ul>
                  </div>
                </div>
                <EmptyState v-else title="没有控制措施" detail="正常样例无需整改；若为风险候选，分析会生成待人工审核的候选措施。" />
              </div>
            </div>

            <details ref="taskPanelElement" class="card task-context" :open="taskPanelOpen"><summary>检查任务与 Agent 分析依据 <span>查看任务理解、工具选择与会话记忆</span></summary><TaskWorkspace :case-data="caseData" @updated="load()" /></details>
            <details class="overview-extras"><summary>数据来源、适用边界与版本</summary>
            <div class="overview-bottom">
              <section class="card">
                <div class="card-head"><div class="card-title"><Info :size="15" /> 数据性质与假设</div></div>
                <div class="card-body">
                  <div class="kv">
                    <span class="k">项目</span><span class="v">{{ caseData.project_id }}</span>
                    <span class="k">区域</span><span class="v mono">{{ caseData.zone_id }}</span>
                    <span class="k">任务</span><span class="v mono">{{ caseData.task_id }}</span>
                    <span class="k">provenance</span><span class="v mono">{{ caseData.provenance }}</span>
                    <span class="k">模式</span><span class="v">{{ caseData.mode === 'demo' ? '演示模式（确定性模板）' : '真实模型模式' }}</span>
                  </div>
                  <ul class="assumption-list">
                    <li v-for="item in caseData.assumptions" :key="item">{{ item }}</li>
                  </ul>
                </div>
              </section>
              <section class="card">
                <div class="card-head"><div class="card-title"><History :size="15" /> 状态与版本</div></div>
                <div class="card-body">
                  <div class="kv">
                    <span class="k">状态</span><span class="v">{{ statusLabel(caseData.status) }}</span>
                    <span class="k">案例版本</span><span class="v mono">v{{ caseData.version }}</span>
                    <span class="k">控制版本</span><span class="v mono">v{{ caseData.control_version }}</span>
                    <span class="k">最近 run</span><span class="v mono">{{ caseData.last_run_id || '—' }}</span>
                    <span class="k">分析完整</span>
                    <span class="v">{{ caseData.analysis_incomplete ? '否 · 需补证' : '是' }}</span>
                  </div>
                  <div class="notice" style="margin-top: 12px">
                    <Lock :size="13" />
                    <span>未经人工批准不会进入整改；未提交实施后证据与人工确认不会关闭。</span>
                  </div>
                </div>
              </section>
            </div>
            </details>
          </div>

          <div v-else-if="activeTab === 'evidence'" class="tab-panel">
            <div class="card">
              <div class="card-head">
                <div class="card-title"><ImagePlus :size="15" /> 案例证据链 <span class="badge tone-slate">{{ evidence.length }}</span></div>
                <div class="row">
                  <button class="btn btn-sm" @click="evidenceModal = true"><Upload :size="13" /> 补证 / 上传</button>
                  <button v-if="canAnalyze" class="btn btn-sm btn-primary" :disabled="busy === 'analyze'" @click="analyze">
                    <RefreshCw :size="13" /> 重新分析
                  </button>
                </div>
              </div>
              <div class="card-body">
                <div v-if="evidence.length" class="evidence-grid">
                  <article v-for="item in evidence" :key="item.evidence_id" class="evidence-card">
                    <div class="evidence-img-wrap" @click="openBim(item.evidence_id)">
                      <img v-if="!item.file_path?.toLowerCase().endsWith('.pdf')" :src="item.image_url" :alt="item.label" />
                      <span v-else class="small">PDF 证据 · 可人工录入观察</span>
                    </div>
                    <div class="evidence-body">
                      <div class="row" style="justify-content: space-between">
                        <span class="mono small">{{ item.evidence_id }}</span>
                        <span class="badge" :class="item.stage === 'after' ? 'tone-teal' : 'tone-cyan'">{{ item.stage === 'after' ? '实施后' : '检查时' }}</span>
                      </div>
                      <strong>{{ item.label }}</strong>
                      <div class="demo-flag"><span class="badge tone-amber">{{ item.source==='upload' ? item.perception?.confirmed ? '人工确认观察' : '上传证据 · 待核对' : '演示示意图 · 非现场照片' }}</span></div>
                      <div class="tiny dim">{{ formatDateTime(item.captured_at) }}</div>
                      <div class="obs-list">
                        <span v-for="key in ['guardrail_state', 'guardrail_height_m', 'worker_present', 'drop_height_m']" :key="key" class="chip">
                          <span class="k">{{ observationLabels[key] || key }}</span>
                          <span>{{ observationText(key, item.observation[key]) }}</span>
                        </span>
                      </div>
                      <div class="evidence-actions">
                        <button class="btn btn-sm" @click="openBim(item.evidence_id)"><MapPin :size="12" /> BIM 定位</button>
                        <span class="tiny dim">{{ item.provenance }}</span>
                      </div>
                      <EvidenceReview v-if="item.source==='upload'" :evidence="item" :case-id="caseData.case_id" :version="caseData.version" :status="caseData.status" @refresh="load(true)" @saved="observationSaved" />
                    </div>
                  </article>
                </div>
                <EmptyState v-else title="没有证据" detail="选择包内 12 条证据之一，或上传 PNG/JPG/PDF。" />
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'review'" class="tab-panel">
            <section v-if="controls.length" class="card review-controls"><div class="card-head"><div class="card-title"><ShieldCheck :size="16" /> {{ canReview ? '请先确认本次控制措施' : '本次控制措施' }}</div><span class="badge tone-blue">v{{ caseData.control_version }}</span></div><div class="card-body"><div v-for="control in controls" :key="control.control_id" class="review-control"><p>{{ control.action }}</p><span><UserCheck :size="13" /> 整改责任：{{ control.owner }}</span></div></div></section>
            <div v-if="canReview" class="card">
              <div class="card-head">
                <div class="card-title"><BadgeCheck :size="15" /> 人工审核</div>
                <span class="badge tone-violet">等待演示安全员</span>
              </div>
              <div class="card-body">
                <div class="decision-grid">
                  <button class="decision" :class="{ active: reviewForm.decision === 'approve' }" @click="reviewForm.decision = 'approve'">
                    <CheckCircle2 :size="17" />
                    <strong>批准</strong>
                    <span>{{ controls.length ? '确认后进入隐患整改' : '确认结果并完成检查' }}</span>
                  </button>
                  <button class="decision" :class="{ active: reviewForm.decision === 'modify' }" @click="reviewForm.decision = 'modify'">
                    <RefreshCw :size="17" />
                    <strong>修改措施</strong>
                    <span>新版本重新审核</span>
                  </button>
                  <button class="decision danger" :class="{ active: reviewForm.decision === 'reject' }" @click="reviewForm.decision = 'reject'">
                    <XCircle :size="17" />
                    <strong>拒绝</strong>
                    <span>不进入整改</span>
                  </button>
                </div>
                <div class="form-row" style="margin-top: 16px">
                  <div class="field">
                    <label>审核人（演示身份）</label>
                    <input v-model="reviewForm.reviewer" class="input" />
                  </div>
                  <div class="field">
                    <label>审核时刻</label>
                    <input v-model="reviewForm.reviewed_at" class="input mono" />
                  </div>
                </div>
                <div v-if="reviewForm.decision === 'modify'" class="field" style="margin-top: 14px">
                  <label>修改后的控制措施</label>
                  <textarea v-model="reviewForm.newAction" class="textarea" placeholder="描述修改后的措施；提交后控制版本 +1，必须重新审核。" />
                  <div class="form-row" style="margin-top: 12px">
                    <div v-if="controls[0]?.verification_criteria?.guardrail_required!==false" class="field"><label for="min-height">栏杆最低验收高度（m）</label><input id="min-height" v-model.number="reviewForm.minHeight" class="input" type="number" min="1.2" max="3" step="0.05" /></div>
                    <div class="field"><label for="manual-requirements">其他需人工逐项确认的要求（每行一项）</label><textarea id="manual-requirements" v-model="reviewForm.manualRequirements" class="textarea" placeholder="例如：材料通道调整已完成" /></div>
                  </div>
                </div>
                <div class="field" style="margin-top: 14px">
                  <label>审核意见</label>
                  <textarea v-model="reviewForm.comment" class="textarea" placeholder="记录批准范围、限制条件或拒绝理由。" />
                </div>
                <div class="notice" style="margin-top: 13px">
                  <Lock :size="13" />
                  <span>
                    {{ controls.length ? `本次审核针对控制措施 v${caseData.control_version}。修改措施后，需要重新审核最新版本。` : '本次检查未生成整改措施，请核对检查范围与依据后确认结果。' }}
                  </span>
                </div>
                <div class="form-actions">
                  <button class="btn btn-primary" :disabled="busy === 'review'" @click="submitReview()">
                    <Loader2 v-if="busy === 'review'" :size="14" class="spin" />
                    <Check v-else :size="14" />
                    {{ reviewForm.decision === 'modify' ? '保存修改，重新审核' : reviewForm.decision === 'reject' ? '拒绝本次措施' : controls.length ? '批准措施，进入整改' : '确认结果并完成检查' }}
                  </button>
                </div>
              </div>
            </div>
            <div v-else class="card">
              <div class="card-head"><div class="card-title"><BadgeCheck :size="15" /> 审核记录</div></div>
              <div class="card-body">
                <div v-if="caseData.review" class="review-record">
                  <div class="row" style="justify-content: space-between">
                    <span class="badge" :class="caseData.review.decision === 'approve' ? 'tone-green' : caseData.review.decision === 'reject' ? 'tone-red' : 'tone-violet'">
                      {{ caseData.review.decision === 'approve' ? '已批准' : caseData.review.decision === 'reject' ? '已拒绝' : '已修改' }}
                    </span>
                    <span class="mono small dim">控制 v{{ caseData.review.control_version }}</span>
                  </div>
                  <p style="margin-top: 12px">{{ caseData.review.comment }}</p>
                  <div class="review-meta">
                    <span><UserCheck :size="12" /> {{ caseData.review.reviewer }}</span>
                    <span><Clock :size="12" /> {{ formatDateTime(caseData.review.reviewed_at) }}</span>
                  </div>
                </div>
                <EmptyState v-else title="尚未审核" />
              </div>
            </div>
          </div>

          <div v-else-if="activeTab === 'verify'" class="tab-panel">
            <RectificationPanel v-if="bundle && ['approved','rectifying','pending_verification'].includes(caseData.status)" :bundle="bundle" @updated="applyWorkspaceBundle" />
            <div v-else-if="caseData.verification" class="card">
              <div class="card-head">
                <div class="card-title"><ClipboardCheck :size="15" /> 复核结果</div>
                <span class="badge" :class="caseData.verification.result === 'pass_in_demo_scope' ? 'tone-green' : 'tone-red'">
                  {{ caseData.verification.result === 'pass_in_demo_scope' ? '通过（演示范围）' : '未通过' }}
                </span>
              </div>
              <div class="card-body">
                <div class="verify-head">
                  <div class="verify-big" :class="caseData.verification.result === 'pass_in_demo_scope' ? 'ok' : 'fail'">
                    <CheckCircle2 v-if="caseData.verification.result === 'pass_in_demo_scope'" :size="25" />
                    <XCircle v-else :size="25" />
                  </div>
                  <div>
                    <h2>{{ caseData.verification.result === 'pass_in_demo_scope' ? '检查已完成闭环' : '检查需要重新处理' }}</h2>
                    <p class="small muted">{{ caseData.verification.remaining_risk }}</p>
                  </div>
                </div>
                <div class="verify-checks">
                  <div v-for="check in caseData.verification.checks" :key="check.name" class="verify-check">
                    <span class="badge" :class="checkTone(check.result)">{{ resultLabel(check.result) }}</span>
                    <span>{{ verificationName(check.name) }}</span>
                    <span class="tiny dim">{{ verificationSource(check.source) }}</span>
                  </div>
                </div>
                <details v-if="canReopen" class="reopen-box"><summary>现场条件变化时，重新打开本次检查</summary>
                  <div class="field" style="margin-top: 10px">
                    <label>条件变化说明</label>
                    <textarea v-model="reopenForm.reason" class="textarea" />
                  </div>
                  <div class="field" style="margin-top: 10px">
                    <label>选择新证据</label>
                    <div class="verify-evidence-list">
                      <button
                        v-for="item in availableEvidence"
                        :key="item.evidence_id"
                        class="verify-evidence"
                        :class="{ selected: reopenForm.evidenceIds.includes(item.evidence_id) }"
                        @click="toggleReopenEvidence(item.evidence_id)"
                      >
                        <img :src="item.image_url" :alt="item.label" />
                        <div>
                          <div class="mono small">{{ item.evidence_id }}</div>
                          <div class="tiny">{{ item.label }}</div>
                        </div>
                        <Check v-if="reopenForm.evidenceIds.includes(item.evidence_id)" :size="14" class="check" />
                      </button>
                    </div>
                  </div>
                  <button class="btn btn-danger" style="margin-top: 12px" :disabled="busy === 'reopen'" @click="submitReopen">
                    <RotateCcw :size="13" /> 保留历史并重新打开
                  </button>
                </details>
              </div>
            </div>

            <div v-else-if="caseData.status === 'closed'" class="card">
              <div class="card-head"><div class="card-title"><CheckCircle2 :size="15" /> 本次检查无需整改</div><span class="badge tone-green">已完成</span></div>
              <div class="card-body">
                <p class="small muted">
                  本次已检查项未发现防护缺失或高度不足；人工审核后直接关闭，因此没有实施与复核记录。该结论不代表整个现场安全。
                </p>
              </div>
            </div>

            <div v-else class="card">
              <EmptyState title="尚未进入实施与复核" />
            </div>
          </div>

          <div v-else-if="activeTab === 'events'" class="tab-panel">
            <div class="card">
              <div class="card-head"><div class="card-title"><History :size="15" /> 事件日志</div><span class="badge tone-slate">{{ events.length }} events</span></div>
              <div class="card-body">
                <div class="timeline">
                  <div v-for="event in events" :key="event.id" class="timeline-item">
                    <div class="timeline-dot" :class="`tone-${statusTone(event.status)}`" />
                    <div class="timeline-body">
                      <div class="timeline-top">
                        <strong>{{ eventLabel(event.event) }}</strong>
                        <span class="badge" :class="`tone-${statusTone(event.status)}`">{{ statusLabel(event.status) }}</span>
                        <span class="mono tiny dim" style="margin-left: auto">{{ formatDateTime(event.at) }}</span>
                      </div>
                      <div class="small muted">{{ event.actor }} · {{ event.provenance }}</div>
                      <details v-if="Object.keys(event.detail || {}).length" class="event-detail">
                        <summary>查看详情</summary>
                        <pre>{{ JSON.stringify(event.detail, null, 2) }}</pre>
                      </details>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <aside v-if="activeTab!=='overview'" class="detail-rail">
          <ModelCalls :calls="bundle?.model_calls || []" />
          <section class="card case-context-rail"><div class="card-head"><div class="card-title"><MapPin :size="16" /> 检查区域与资料</div></div><div class="card-body"><span class="area-label">S1 建设项目</span><h3>{{ bundle?.context?.zone.storey_name || "05 层板边" }}</h3><p class="area-activity">{{ bundle?.context?.task.activity || "机电材料转运作业区域" }}</p><p class="mono small">{{ caseData.bim_guids.join(", ") }}</p><button class="btn" style="width:100%;margin:15px 0 19px" @click="openBim(caseData.evidence_ids[0] || '')"><Box :size="15" /> 查看 BIM 区域</button><div v-if="evidence[0]" class="rail-evidence"><img :src="evidence[0].image_url" :alt="evidence[0].label" /><span class="badge tone-amber">{{ evidence[0].source==="upload" ? "上传原图" : "演示示意图" }}</span></div><div v-if="evidence[0]" class="rail-evidence-caption"><strong>{{ evidence[0].label }}</strong><span>检查时证据 · {{ evidence[0].evidence_id }}</span></div><div class="rail-dates"><span>检查时刻</span><strong>{{ formatDateTime(caseData.as_of) }}</strong><template v-if="caseData.review"><span>审核人</span><strong>{{ caseData.review.reviewer }}</strong></template><template v-if="caseData.implementation"><span>实施责任</span><strong>{{ caseData.implementation.owner }}</strong></template><template v-else-if="controls[0]"><span>拟整改责任</span><strong>{{ controls[0].owner }}</strong></template></div></div></section>
          <details class="card trace-disclosure"><summary><Sparkles :size="15" /> 查看 Agent 运行过程</summary><div class="card-body"><p class="small muted">{{ latestRun ? `本次分析记录 ${latestRun.events?.length || 0} 个节点事件。` : '分析完成后可查看工具与执行记录。' }}</p><p v-if="latestRun?.error" class="run-error">{{ latestRun.error }}</p><router-link v-if="latestRun" class="btn btn-sm" style="width:100%;margin-top:14px" :to="`/agent?run=${latestRun.run_id}`">打开完整运行记录 <ArrowRight :size="12" /></router-link></div></details>
        </aside>
      </div>
    </template>

    <Modal :open="evidenceModal" :title="caseData?.status === 'rectifying' ? '提交整改后证据' : '补充检查证据'" width="760px" @close="evidenceModal = false">
      <div class="section-title">包内证据 · 未加入当前案例</div>
      <div v-if="availableEvidence.length" class="add-evidence-list">
        <button
          v-for="item in availableEvidence"
          :key="item.evidence_id"
          class="add-evidence"
          :class="{ selected: selectedEvidenceIds.includes(item.evidence_id) }"
          @click="toggleSelectedEvidence(item.evidence_id)"
        >
          <img :src="item.image_url" :alt="item.label" />
          <div>
            <div class="mono small">{{ item.evidence_id }}</div>
            <div class="small">{{ item.label }}</div>
            <div class="tiny dim">{{ item.stage }} · {{ formatDateTime(item.captured_at) }}</div>
          </div>
          <Check v-if="selectedEvidenceIds.includes(item.evidence_id)" :size="14" class="check" />
        </button>
      </div>
      <div v-else class="small dim" style="padding: 12px 0">暂无匹配的预置证据</div>

      <div class="divider" />
      <div class="section-title">上传文件</div>
      <div class="upload-box">
        <input ref="uploadRef" type="file" accept=".png,.jpg,.jpeg,.pdf" aria-label="上传现场证据" @change="onUploadChange" />
        <label class="field">证据阶段<select v-model="uploadStage" class="select" aria-label="上传证据阶段"><option value="before">检查时</option><option value="after">实施后</option></select></label>
        <label class="field">拍摄时刻<input v-model="uploadCapturedAt" class="input" aria-label="上传证据拍摄时刻" /></label>
        <div class="small dim">PNG / JPG / PDF · 最大 20 MB</div>
      </div>

      <template #footer>
        <button class="btn" @click="evidenceModal = false">取消</button>
        <button class="btn" :disabled="!selectedEvidenceIds.length || busy === 'evidence'" @click="addEvidence(selectedEvidenceIds)">
          <Loader2 v-if="busy === 'evidence'" :size="13" class="spin" />
          <Plus :size="13" />
          追加所选证据
        </button>
        <button class="btn btn-primary" :disabled="!uploadFile || busy === 'upload'" @click="uploadEvidence">
          <Loader2 v-if="busy === 'upload'" :size="13" class="spin" />
          <Upload v-else :size="13" />
          上传文件
        </button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.case-section-navigation{scroll-margin-top:85px;margin:20px 0}.detail-grid.workspace-active{grid-template-columns:1fr}.workspace-active .detail-main{min-width:0}

.current-work{display:flex;align-items:center;gap:17px;padding:21px 24px;border:1px solid #c6d8f3;border-radius:14px;background:linear-gradient(105deg,#f7faff,#edf4ff);margin-bottom:23px}.current-work-icon{width:47px;height:47px;display:grid;place-items:center;flex-shrink:0;background:#e2edff;color:var(--blue);border-radius:13px}.current-work>div{flex:1}.current-work-label{font-size:10px;color:#728cad}.current-work h2{font-size:18px;margin:4px 0 7px;font-weight:700}.current-work p{font-size:12px;color:var(--muted);line-height:1.7}.current-work .btn{height:40px;padding:0 18px}.current-work.completed{border-color:#c9e5d8;background:linear-gradient(105deg,#fafdfb,#eef9f3)}.completed .current-work-icon{background:#ddf2e6;color:var(--green)}.task-context{overflow:hidden;scroll-margin-top:88px}.task-context>summary{display:flex;gap:10px;align-items:center;padding:19px 20px;cursor:pointer;font-size:13px;font-weight:600;color:var(--text-soft)}.task-context>summary:before{content:'›';font-size:19px;color:var(--blue)}.task-context[open]>summary:before{transform:rotate(90deg)}.task-context>summary span{font-size:10px;font-weight:400;color:var(--dim);margin-left:auto}.overview-extras>summary{cursor:pointer;font-size:12px;color:var(--muted);padding:14px 2px}.overview-extras .overview-bottom{margin-top:5px}.check-details{margin-top:19px;padding-top:15px;border-top:1px solid var(--line)}.check-details>summary{cursor:pointer;font-size:12px;color:var(--blue)}.review-control p{font-size:15px;line-height:1.9;color:var(--text);margin:0 0 12px}.review-control>span{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted)}.review-controls{border-top:3px solid #799fce}.area-label{font-size:11px;color:var(--muted)}.case-context-rail h3{font-size:20px;margin-top:8px}.area-activity{font-size:11px;color:var(--muted);margin-top:7px}.rail-evidence{height:150px;position:relative;border-radius:9px;overflow:hidden;background:#e7eef5}.rail-evidence img{width:100%;height:100%;object-fit:contain}.rail-evidence .badge{position:absolute;left:8px;bottom:8px;font-size:10px}.rail-evidence-caption{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:12px}.rail-evidence-caption strong{font-size:12px}.rail-evidence-caption>span{font-size:10px;color:var(--muted)}.rail-dates{display:grid;grid-template-columns:auto 1fr;gap:13px 10px;border-top:1px solid var(--line);margin-top:17px;padding-top:17px;font-size:11px}.rail-dates>span{color:var(--muted)}.rail-dates>strong{text-align:right;font-weight:500;color:var(--text-soft)}.trace-disclosure>summary{display:flex;align-items:center;gap:8px;cursor:pointer;padding:17px 18px;font-size:12px;color:var(--muted)}.trace-disclosure>summary:after{content:'›';margin-left:auto}.trace-disclosure[open]>summary:after{transform:rotate(90deg)}.trace-disclosure .card-body{padding-top:0}.head-more{font-size:11px;color:var(--muted)}.head-more>summary{cursor:pointer;padding:9px}.head-more[open]{display:grid;gap:9px;max-width:260px}.head-more .small{font-size:10px;line-height:1.8;overflow-wrap:anywhere}.detail-grid{scroll-margin-top:87px}
@media(max-width:750px){.current-work{padding:17px;gap:12px;flex-wrap:wrap}.current-work h2{font-size:16px}.current-work .btn{margin-left:59px}.task-context>summary span{display:none}.current-work p{font-size:11px}}
.detail-page {
  max-width: 1780px;
}
.loading-block {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 60px;
  color: var(--muted);
}
.detail-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  margin-bottom: 16px;
}
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--dim);
  margin-bottom: 8px;
}
.back-link:hover {
  color: var(--teal);
}
.title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.title-row h1 {
  font-size: 27px;
}
.detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--dim);
  flex-wrap: wrap;
}
.detail-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.sep {
  color: #33475c;
}
.branch-banner {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 13px;
  border-radius: 9px;
  margin-bottom: 12px;
  font-size: 11.5px;
  border: 1px solid var(--line);
}
.branch-amber { color: var(--amber); background: rgba(251, 191, 36, 0.055); border-color: rgba(251, 191, 36, 0.2); }
.branch-rose { color: #bc4b60; background: rgba(253, 164, 175, 0.055); border-color: rgba(253, 164, 175, 0.2); }
.branch-red { color: var(--red); background: rgba(251, 113, 133, 0.055); border-color: rgba(251, 113, 133, 0.2); }
.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 288px;
  gap: 16px;
  align-items: start;
}
.detail-main {
  min-width: 0;
}
.tabs {
  padding: 0 12px;
  margin-bottom: 12px;
  overflow-x: auto;
}
.tab-count {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--dim);
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(148, 163, 184, 0.08);
}
.tab-alert {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--violet);
  box-shadow: 0 0 7px var(--violet);
  display: inline-block;
  vertical-align: middle;
}
.tab-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.finding-card .card-body {
  padding-top: 17px;
}
.finding-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}
.finding-hero h2 {
  font-size: 23px;
  letter-spacing: -0.02em;
}
.finding-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.finding-rule-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  align-items: flex-end;
  flex: none;
}
.rule-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 3px 7px;
  color: var(--muted);
  background: var(--panel-2);
}
.rule-pill:hover {
  color: var(--teal);
  border-color: rgba(45, 212, 191, 0.3);
}
.narrative-block {
  margin-top: 16px;
  padding: 12px 14px;
  border: 1px solid rgba(167, 139, 250, 0.2);
  background: rgba(167, 139, 250, 0.04);
  border-radius: 8px;
}
.narrative-head {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: var(--violet);
  font-weight: 550;
}
.narrative-head .badge {
  margin-left: auto;
}
.narrative-block p {
  margin-top: 7px;
  color: var(--text-soft);
  font-size: 13px;
  line-height: 1.7;
}
.narrative-basis {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
}
.narrative-basis .caption {
  margin-right: 3px;
}
.narrative-basis .mono {
  font-size: 11px;
  color: var(--muted);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 2px 5px;
  background: var(--panel-2);
}
.check-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 18px;
  padding-top: 15px;
  border-top: 1px solid var(--line);
}
.check-item {
  display: flex;
  gap: 8px;
  padding: 8px 9px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--panel-2);
}
.check-icon {
  width: 19px;
  height: 19px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex: none;
  margin-top: 1px;
}
.check-name {
  font-size: 11px;
  font-weight: 550;
  color: var(--text-soft);
}
.check-source {
  font-size: 11px;
  color: var(--dim);
  margin-top: 1px;
}
.check-note {
  font-size: 11px;
  color: var(--dim);
  line-height: 1.45;
  margin-top: 3px;
}
.uncertainties {
  margin-top: 15px;
  padding: 11px 13px;
  border-left: 2px solid var(--amber);
  background: rgba(251, 191, 36, 0.04);
  border-radius: 0 6px 6px 0;
}
.uncertainties ul,
.assumption-list,
.req-list {
  margin: 0;
  padding-left: 16px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.7;
}
.controls-card .control-list {
  display: flex;
  flex-direction: column;
  gap: 11px;
}
.control-item {
  padding: 13px 14px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--panel-2);
}
.control-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--teal);
}
.control-item p {
  margin-top: 8px;
  color: var(--text-soft);
  font-size: 14px;
  line-height: 1.7;
}
.control-meta {
  display: flex;
  gap: 15px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--dim);
}
.control-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.req-list {
  margin-top: 7px;
}
.overview-bottom {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.assumption-list {
  margin-top: 12px;
}
.evidence-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.evidence-card {
  border: 1px solid var(--line);
  border-radius: 9px;
  overflow: hidden;
  background: var(--panel-2);
}
.evidence-img-wrap {
  position: relative;
  cursor: pointer;
  overflow: hidden;
}
.evidence-img-wrap img {
  width: 100%;
  height: 150px;
  object-fit: cover;
  display: block;
  opacity: 0.92;
  transition: 180ms ease;
}
.evidence-img-wrap:hover img {
  transform: scale(1.02);
  opacity: 1;
}
.demo-flag {
  margin-top: 3px;
}
.demo-flag .badge {
  font-size: 11px;
}
.evidence-body {
  padding: 11px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.evidence-body strong {
  font-size: 11.5px;
}
.obs-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 7px;
}
.obs-list .chip {
  font-size: 11px;
  padding: 2px 5px;
}
.evidence-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}
.decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 9px;
}
.decision {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 12px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: var(--panel-2);
  color: var(--muted);
  text-align: left;
}
.decision strong {
  font-size: 12px;
  color: var(--text-soft);
}
.decision span {
  font-size: 11px;
  color: var(--dim);
}
.decision.active {
  border-color: var(--teal);
  background: rgba(45, 212, 191, 0.07);
  color: var(--teal);
}
.decision.active strong {
  color: var(--teal);
}
.decision.danger.active {
  border-color: var(--red);
  background: rgba(251, 113, 133, 0.07);
  color: var(--red);
}
.decision.danger.active strong {
  color: var(--red);
}
.review-record p {
  color: var(--text-soft);
  font-size: 12px;
  line-height: 1.7;
}
.review-meta {
  display: flex;
  gap: 15px;
  margin-top: 12px;
  font-size: 11px;
  color: var(--dim);
}
.review-meta span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.implementation-record {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(45, 212, 191, 0.05);
  border: 1px solid rgba(45, 212, 191, 0.16);
}
.record-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: rgba(45, 212, 191, 0.1);
  color: var(--teal);
}
.verify-evidence-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  max-height: 230px;
  overflow-y: auto;
}
.verify-evidence {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--panel-2);
  color: var(--text-soft);
  text-align: left;
}
.verify-evidence img {
  width: 54px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
  opacity: 0.85;
}
.verify-evidence.selected {
  border-color: var(--teal);
  box-shadow: 0 0 0 1px rgba(45, 212, 191, 0.25);
}
.verify-evidence:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.verify-evidence .check {
  margin-left: auto;
  color: var(--teal);
}
.confirm-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 14px;
  font-size: 11px;
  color: var(--muted);
}
.confirm-line input {
  accent-color: var(--teal);
  margin-top: 2px;
}
.verify-head {
  display: flex;
  align-items: center;
  gap: 14px;
}
.verify-big {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex: none;
}
.verify-big.ok {
  color: var(--green);
  background: rgba(52, 211, 153, 0.1);
  border: 1px solid rgba(52, 211, 153, 0.28);
}
.verify-big.fail {
  color: var(--red);
  background: rgba(251, 113, 133, 0.1);
  border: 1px solid rgba(251, 113, 133, 0.28);
}
.verify-head h2 {
  font-size: 17px;
}
.verify-head p {
  margin-top: 4px;
}
.verify-checks {
  margin-top: 16px;
  border-top: 1px solid var(--line);
}
.verify-check {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(124, 160, 196, 0.08);
  font-size: 11px;
}
.verify-check .dim {
  margin-left: auto;
  font-size: 11px;
}
.reopen-box {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}
.reopen-box > summary { cursor: pointer; font-size: 12px; color: var(--muted); }
.narrative-reference { margin-top: 10px; font-size: 11px; color: var(--muted); }
.narrative-reference > summary { cursor: pointer; }
.timeline {
  position: relative;
  padding-left: 6px;
}
.timeline-item {
  display: flex;
  gap: 12px;
  position: relative;
  padding-bottom: 18px;
}
.timeline-item::before {
  content: "";
  position: absolute;
  left: 4px;
  top: 12px;
  bottom: 0;
  width: 1px;
  background: var(--line);
}
.timeline-item:last-child::before {
  display: none;
}
.timeline-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  margin-top: 5px;
  background: currentColor;
  box-shadow: 0 0 8px currentColor;
  z-index: 1;
}
.timeline-body {
  flex: 1;
  min-width: 0;
}
.timeline-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.timeline-top strong {
  font-size: 11.5px;
  font-weight: 600;
}
.event-detail {
  margin-top: 6px;
}
.event-detail summary {
  font-size: 11px;
  color: var(--dim);
  cursor: pointer;
}
.event-detail pre {
  margin: 6px 0 0;
  padding: 9px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel-2);
  font-size: 11px;
  color: var(--muted);
  overflow: auto;
  max-height: 180px;
}
.detail-rail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 78px;
}
.run-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 9px;
  border-bottom: 1px solid var(--line);
}
.trace-mini {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}
.trace-mini-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.trace-seq {
  font-size: 11px;
  color: var(--dim);
  border: 1px solid var(--line);
  border-radius: 4px;
  width: 20px;
  height: 18px;
  display: grid;
  place-items: center;
  flex: none;
}
.trace-node {
  font-size: 11px;
  color: var(--text-soft);
  line-height: 1.35;
}
.rail-list {
  margin: 0;
  padding-left: 15px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.75;
}
.add-evidence-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px;
  max-height: 260px;
  overflow-y: auto;
  margin-top: 8px;
}
.add-evidence {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px;
  border: 1px solid var(--line);
  border-radius: 7px;
  background: var(--panel-2);
  color: var(--text-soft);
  text-align: left;
}
.add-evidence img {
  width: 52px;
  height: 42px;
  object-fit: cover;
  border-radius: 4px;
  opacity: 0.85;
}
.add-evidence.selected {
  border-color: var(--teal);
}
.add-evidence .check {
  margin-left: auto;
  color: var(--teal);
}
.upload-box {
  margin-top: 8px;
  padding: 12px;
  border: 1px dashed var(--line-strong);
  border-radius: 8px;
  background: var(--panel-2);
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.upload-box input {
  font-size: 11px;
  color: var(--muted);
}
@media (max-width: 1150px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
  .detail-rail {
    position: static;
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
}
@media (max-width: 900px) {
  .detail-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .check-grid,
  .overview-bottom,
  .evidence-grid,
  .decision-grid,
  .detail-rail,
  .add-evidence-list {
    grid-template-columns: 1fr;
  }
  .finding-hero {
    flex-direction: column;
  }
  .finding-rule-list {
    align-items: flex-start;
  }
}
</style>
