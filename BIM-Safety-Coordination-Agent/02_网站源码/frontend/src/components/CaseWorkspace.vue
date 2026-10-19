<script setup lang="ts">
import { t } from '../i18n'
import { computed,nextTick,ref,watch } from 'vue'
import { Box,MapPin,Crosshair,Layers,FileText,CalendarClock,GitBranch,Loader2,Check,ShieldAlert } from 'lucide-vue-next'
import BimViewer from './BimViewer.vue'
import ScopeEditor from './ScopeEditor.vue'
import ActivityPlanPanel from './ActivityPlanPanel.vue'
import SiteNotesPanel from './SiteNotesPanel.vue'
import EvidenceReview from './EvidenceReview.vue'
import ModelCalls from './ModelCalls.vue'
import Modal from './Modal.vue'
import { api } from '../api'
import { errorMessage,toast } from '../store'
import { formatDateTime,observationLabel,resultLabel } from '../utils'
import type { Activity,CaseBundle,Evidence,Finding,MeshData,MeshPayload,Run,ScopeAnnotation } from '../types'
const props=defineProps<{bundle:CaseBundle;run?:Run|null}>()
const emit=defineEmits<{updated:[bundle:CaseBundle]}>()
const meshes=ref<MeshData[]>([]),guid=ref(''),selectedFindingId=ref(''),evidenceId=ref(''),panel=ref('state')
const loading=ref(false),error=ref(''),activePair=ref(''),draftActivities=ref<Activity[]|null>(null)
const scopeOpen=ref(false),scopeSaving=ref(false),scopeDraft=ref<ScopeAnnotation>({guid:'',edge_index:0,worker_point_m:null,worker_point_source:'simulated',boundary_confirmed:false})
const viewer=ref<InstanceType<typeof BimViewer>|null>(null),bottom=ref<HTMLElement|null>(null)
const selectedFinding=computed(()=>props.bundle.case.findings.find(f=>f.finding_id===selectedFindingId.value) || null)
const selectedEvidence=computed(()=>props.bundle.evidence.find(e=>e.evidence_id===evidenceId.value) || null)
const zone=computed(()=>props.bundle.context?.zone.data || {})
const task=computed(()=>props.bundle.context?.task || {})
const canEditScope=computed(()=>['draft','needs_evidence','pending_review','reopened','rejected'].includes(props.bundle.case.status))
const point=computed(()=>guid.value===(zone.value.guid || zone.value.target?.guid || props.bundle.case.bim_guids[0]) ? props.bundle.spatial?.data?.point_m || zone.value.worker_point_m || null : null)
const edge=computed(()=>point.value && zone.value.edge_segment_m ? [zone.value.edge_segment_m] : [])
const selectedRules=computed(()=>props.bundle.rules.filter(r=>selectedFinding.value?.rule_ids.includes(r.rule_id)))
const activities=computed(()=>draftActivities.value || props.bundle.activity_plan?.activities || [])
const volumes=computed(()=>{
  const conflicts=props.bundle.coordination?.conflicts || []
  const highlighted=activePair.value ? conflicts.filter((p:any)=>p.pair_id===activePair.value) : conflicts
  const marked=new Set<string>(highlighted.flatMap((p:any)=>p.task_ids))
  const result=activities.value.filter(a=>a.workspace).map(a=>({task_id:a.task_id,workspace:a.workspace!,conflict:marked.has(a.task_id)}))
  for(const pair of highlighted) if(pair.intersection_m) result.push({task_id:'INTERSECTION-'+pair.pair_id,workspace:pair.intersection_m,conflict:true})
  return result
})
const observationKeys=['guardrail_state','guardrail_height_m','worker_present','guardrail_fixed','guardrail_continuous']
const hasMissing=computed(()=>[...(props.bundle.case.safety_state?.missing_fields || []),...(props.bundle.site_text?.missing_fields || [])])
function observationValue(value:any,key:string) {
  if(value==null) return '—'
  if(typeof value==='boolean') return value ? t('是') : t('否')
  if(typeof value==='number') return `${value}${key.endsWith('_m') ? ' m' : ''}`
  return ({present:t('已设置'),absent:t('未设置'),unknown:t('未知')} as Record<string,string>)[value] || String(value)
}
function imageUrl(item:Evidence) {return item.image_url || `/api/files/evidence/${encodeURIComponent(item.evidence_id)}`}
function coordinationResolved(item:Finding) {
  return item.kind==='coordination' && props.bundle.coordination?.complete && !props.bundle.coordination.conflicts.some((pair:any)=>pair.pair_id===item.pair_id)
}
function chooseEvidence(id:string) {evidenceId.value=id}
async function chooseFinding(finding:Finding) {
  selectedFindingId.value=finding.finding_id
  guid.value=finding.bim_guids[0] || props.bundle.case.bim_guids[0]
  evidenceId.value=finding.evidence_ids.find(id=>props.bundle.evidence.some(e=>e.evidence_id===id)) || ''
  activePair.value=finding.pair_id || ''
  if (finding.kind==='coordination') panel.value='activities'
  else if (finding.kind==='text') panel.value='text'
  else panel.value='state'
  await nextTick();viewer.value?.focusGuid(guid.value)
}
async function selectPanel(value:string) {panel.value=value;await nextTick();bottom.value?.scrollIntoView({behavior:'smooth',block:'start'})}
defineExpose({openPanel:selectPanel})
function selectPair(id:string) {
  activePair.value=id
  const finding=props.bundle.case.findings.find(f=>f.pair_id===id)
  if(finding) selectedFindingId.value=finding.finding_id
  viewer.value?.focusGuid(guid.value)
}
function selectActivity(id:string) {
  const pair=(props.bundle.coordination?.pairs || []).find((p:any)=>p.task_ids.includes(id))
  if(pair) selectPair(pair.pair_id)
}
function openScope() {
  const source=props.bundle.case.scope || zone.value
  scopeDraft.value={guid:props.bundle.case.bim_guids[0],edge_index:source.edge_index || 0,
    worker_point_m:props.bundle.spatial?.data?.point_m || source.worker_point_m || null,
    worker_point_source:source.worker_point_source || 'simulated',boundary_confirmed:false}
  scopeOpen.value=true
}
async function saveScope() {
  scopeSaving.value=true
  try {
    const result=await api.put<CaseBundle>(`/cases/${props.bundle.case.case_id}/scope`,{...scopeDraft.value,expected_case_version:props.bundle.case.version})
    scopeOpen.value=false;emit('updated',result);toast(t('范围标注已保存，待重新分析。'),'success')
  } catch(cause) {toast(errorMessage(cause),'error')}
  finally {scopeSaving.value=false}
}
watch(()=>props.bundle.case.case_id,()=>{
  guid.value=props.bundle.case.bim_guids[0]
  selectedFindingId.value='';evidenceId.value=props.bundle.evidence[0]?.evidence_id || '';panel.value='state';activePair.value=''
  draftActivities.value=null
},{immediate:true})
watch(()=>props.bundle.case.findings,items=>{
  if(!items.some(f=>f.finding_id===selectedFindingId.value)) {
    const next=items.find(f=>f.result==='risk_candidate') || items[0]
    if(next) chooseFinding(next)
    else selectedFindingId.value=''
  }
},{immediate:true})
let loadSequence=0
watch(guid,async value=>{
  if(!value) return
  const seq=++loadSequence;loading.value=true;error.value=''
  try {
    const payload=await api.get<MeshPayload>('/models/S1-bSDD-example/mesh?scope=target')
    let all=payload.meshes
    if(!all.some(m=>m.guid===value)) {
      const response=await api.get<{mesh:MeshData}>(`/models/S1-bSDD-example/elements/${encodeURIComponent(value)}/mesh`)
      all=[...all,response.mesh]
    }
    if(seq!==loadSequence) return
    meshes.value=all;await nextTick();viewer.value?.focusGuid(value)
  } catch(cause) {if(seq===loadSequence) error.value=errorMessage(cause)}
  finally {if(seq===loadSequence) loading.value=false}
},{immediate:true})
</script>
<template>
  <section class="case-workspace card">
    <header class="workspace-heading"><div><Layers :size="20" /><h2>{{ t('协同工作台') }}</h2></div><div class="workspace-actions"><button class="btn btn-sm" :disabled="!canEditScope" @click="openScope"><Crosshair :size="15" />{{ t('范围与人员') }}</button><button class="btn btn-sm" @click="selectPanel('activities')"><CalendarClock :size="15" />{{ t('施工活动') }}</button><button class="btn btn-sm" @click="selectPanel('text')"><FileText :size="15" />{{ t('现场文本') }}</button><button class="btn btn-sm" @click="selectPanel('trace')"><GitBranch :size="15" />{{ t('Agent 记录') }}</button></div></header>
    <div class="linked-workspace">
      <aside class="scope-rail"><div class="rail-label"><MapPin :size="15" />{{ bundle.context?.zone.storey_name || t('05 层') }}</div><h3>{{ task.activity }}</h3><dl><dt>{{ t('责任主体') }}</dt><dd>{{ task.owner }}</dd><dt>{{ t('检查时刻') }}</dt><dd>{{ formatDateTime(bundle.case.as_of) }}</dd><dt>{{ t('距边线') }}</dt><dd>{{ bundle.spatial?.data?.distance_m ?? '—' }} m <span class="badge tone-amber">{{ zone.worker_point_source==='human_observed' ? t('人工标注') : t('模拟点') }}</span></dd><dt>{{ t('构件') }}</dt><dd class="mono guid">{{ guid }}</dd></dl><div class="finding-list"><h4>{{ t('风险与检查项') }}</h4><button v-for="item in bundle.case.findings" :key="item.finding_id" class="finding-item" :class="{active:selectedFindingId===item.finding_id,risk:item.result==='risk_candidate' && !coordinationResolved(item)}" @click="chooseFinding(item)"><ShieldAlert v-if="item.result==='risk_candidate'" :size="17" /><Check v-else :size="17" /><span><strong>{{ item.hazard }}</strong><small>{{ coordinationResolved(item) ? `计划冲突已消除 · ${bundle.case.status==='closed' ? t('已复核') : t('待复核')}` : resultLabel(item.result) }}</small></span></button><span v-if="!bundle.case.findings.length" class="rail-empty">{{ t('等待分析') }}</span></div></aside>
      <div class="linked-canvas"><BimViewer ref="viewer" :meshes="meshes" :target-guid="guid" :selected-guid="guid" :risk-guids="selectedFinding?.result==='risk_candidate' ? selectedFinding.bim_guids : []" :edge-segments="edge" :evidence-point="point" evidence-label="检查人员点" :activity-volumes="volumes" @select="id=>{if(bundle.case.bim_guids.includes(id)) guid=id}" @select-activity="selectActivity" /><div class="canvas-header"><span class="badge tone-blue"><Box :size="13" />{{ bundle.context?.zone.storey_name || t('05 层') }}</span><button class="btn btn-sm" @click="viewer?.focusGuid(guid)">{{ t('定位当前构件') }}</button></div><div v-if="loading" class="linked-loading"><Loader2 class="spin" :size="18" /></div><div v-if="error" class="linked-error">{{ error }}</div></div>
      <aside class="evidence-rail"><div class="rail-title"><h3>{{ t('现场证据') }}</h3><span>{{ bundle.evidence.length }}</span></div><div class="evidence-picks"><button v-for="item in bundle.evidence" :key="item.evidence_id" :class="{active:evidenceId===item.evidence_id}" @click="chooseEvidence(item.evidence_id)"><img v-if="!item.file_path?.endsWith('.pdf')" :src="imageUrl(item)" :alt="item.label" /><span v-else>PDF</span><small>{{ item.stage==='after' ? t('整改后') : t('检查时') }}</small></button></div><template v-if="selectedEvidence"><a :href="imageUrl(selectedEvidence)" target="_blank" rel="noopener" class="linked-photo"><img v-if="!selectedEvidence.file_path?.endsWith('.pdf')" :src="imageUrl(selectedEvidence)" :alt="selectedEvidence.label" /><span v-else>{{ t('查看 PDF 证据') }}</span></a><div class="photo-meta"><strong>{{ selectedEvidence.label }}</strong><span>{{ formatDateTime(selectedEvidence.captured_at) }}</span><small>{{ selectedEvidence.evidence_id }}</small></div><div class="observation-compare"><div class="compare-heading"><span>{{ t('观察项') }}</span><span>{{ t('模型候选') }}</span><span>{{ selectedEvidence.source==='upload' ? t('人工确认') : t('样例观察') }}</span></div><div v-for="key in observationKeys" :key="key"><span>{{ observationLabel(key) }}</span><span>{{ observationValue(selectedEvidence.perception?.observation?.[key],key) }}</span><strong>{{ selectedEvidence.source!=='upload' || selectedEvidence.perception?.confirmed ? observationValue(selectedEvidence.observation[key],key) : t('待确认') }}</strong></div></div><EvidenceReview v-if="selectedEvidence.source==='upload'" :key="selectedEvidence.evidence_id" :evidence="selectedEvidence" :case-id="bundle.case.case_id" :version="bundle.case.version" :status="bundle.case.status" @refresh="api.get<CaseBundle>(`/cases/${bundle.case.case_id}`).then(value=>emit('updated',value))" @saved="emit('updated',$event)" /></template><p v-else class="evidence-empty">{{ selectedFinding?.kind==='coordination' ? '本项依据：活动时间与作业范围' : '选择同案现场证据' }}</p><div v-if="selectedRules.length" class="linked-rules"><h4>规范依据</h4><details v-for="rule in selectedRules" :key="rule.rule_id"><summary>{{ rule.standard }} · {{ rule.clause }}</summary><p>{{ rule.text }}</p><a :href="`/api/files/rules/${rule.rule_id}#page=${rule.pdf_page}`" target="_blank" rel="noopener">查看原文 · 第 {{ rule.pdf_page }} 页</a></details></div></aside>
    </div>
    <div ref="bottom" class="workspace-bottom"><div class="workspace-tabs"><button :class="{active:panel==='state'}" @click="panel='state'">安全状态</button><button :class="{active:panel==='activities'}" @click="panel='activities'">活动与时空冲突<span v-if="bundle.coordination?.conflicts.length">{{ bundle.coordination.conflicts.length }}</span></button><button :class="{active:panel==='text'}" @click="panel='text'">现场文本<span v-if="bundle.site_text?.conflicts.some((c:any)=>!c.resolution)">待澄清</span></button><button :class="{active:panel==='trace'}" @click="panel='trace'">Agent 记录</button></div>
      <div v-if="panel==='state'" class="state-content"><div class="state-grid"><div><span>活动</span><strong>{{ task.activity }}</strong></div><div><span>位置</span><strong>{{ bundle.context?.zone.storey_name }}</strong></div><div><span>时间</span><strong>{{ formatDateTime(bundle.case.as_of) }}</strong></div><div><span>活动计划</span><strong>{{ bundle.activity_plan ? `当前 v${bundle.activity_plan.revision}` : '单项活动' }}</strong></div></div><article v-if="selectedFinding" class="selected-finding"><h3>{{ selectedFinding.hazard }}</h3><span v-if="selectedFinding.kind==='coordination' && coordinationResolved(selectedFinding)" class="badge tone-green">计划已调整 · 下列为分析时快照</span><p v-if="selectedFinding.narrative">{{ selectedFinding.narrative.summary }}</p><div class="check-grid"><div v-for="check in selectedFinding.checks" :key="check.name"><span>{{ check.name }}</span><strong :class="check.result==='fail' ? 'failed' : check.result==='pass' ? 'passed' : 'unknown'">{{ resultLabel(check.result) }}</strong></div></div><ul v-if="selectedFinding.uncertainties.length"><li v-for="item in selectedFinding.uncertainties" :key="item">{{ item }}</li></ul></article><div v-if="hasMissing.length" class="state-missing">待补充：{{ [...new Set(hasMissing)].map(key=>observationLabel(key)).join('、') }}</div></div>
      <div v-else-if="panel==='activities'" class="bottom-panel"><ActivityPlanPanel :bundle="bundle" @updated="emit('updated',$event)" @preview="draftActivities=$event" @select-pair="selectPair" /></div>
      <div v-else-if="panel==='text'" class="bottom-panel"><SiteNotesPanel :bundle="bundle" @updated="emit('updated',$event)" @select-evidence="chooseEvidence" /></div>
      <div v-else class="bottom-panel"><div v-if="run?.events?.length" class="execution-list"><details v-for="event in run.events" :key="event.seq"><summary><span>{{ event.seq }}</span><strong>{{ event.node }}</strong><span>{{ event.tool || event.role }}</span><small>{{ event.status }}</small></summary><p>{{ event.rationale }}</p><pre>{{ JSON.stringify(event.output,null,2) }}</pre></details></div><div v-else class="trace-empty">暂无运行记录</div><ModelCalls :calls="bundle.model_calls || []" /></div>
    </div>
    <Modal :open="scopeOpen" title="范围与人员标注" width="1050px" @close="scopeOpen=false"><ScopeEditor v-model="scopeDraft" :guid="scopeDraft.guid" /><label class="scope-ack"><input v-model="scopeDraft.boundary_confirmed" type="checkbox" />确认所选检查边线、人员点与来源</label><template #footer><button class="btn" @click="scopeOpen=false">取消</button><button class="btn btn-primary" :disabled="!scopeDraft.boundary_confirmed || scopeSaving" @click="saveScope"><Loader2 v-if="scopeSaving" :size="15" class="spin" />保存范围标注</button></template></Modal>
  </section>
</template>
<style scoped>
.case-workspace{margin:24px 0;overflow:hidden}.workspace-heading{display:flex;align-items:center;justify-content:space-between;gap:18px;flex-wrap:wrap;padding:22px 24px;border-bottom:1px solid var(--line)}.workspace-heading>div{display:flex;align-items:center;gap:10px}.workspace-actions{flex-wrap:wrap}.linked-workspace{display:grid;grid-template-columns:220px minmax(360px,1fr) 300px;min-height:580px}.scope-rail{padding:22px 18px;border-right:1px solid var(--line);background:#f9fbfd}.rail-label{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted);margin-bottom:12px}.scope-rail h3{line-height:1.6}.scope-rail dl{font-size:12px;margin:20px 0}.scope-rail dt{color:var(--muted);margin-top:12px}.scope-rail dd{margin:5px 0 0;color:var(--text-soft)}.guid{font-size:11px;overflow-wrap:anywhere}.finding-list{padding-top:18px;border-top:1px solid var(--line)}.finding-list h4{font-size:14px;margin-bottom:13px}.finding-item{display:flex;gap:8px;width:100%;padding:12px 10px;background:white;border:1px solid var(--line);border-radius:9px;text-align:left;margin-bottom:10px;color:var(--text-soft)}.finding-item svg{flex-shrink:0;margin-top:2px}.finding-item strong{display:block;font-size:13px;font-weight:600}.finding-item small{display:block;font-size:11px;color:var(--muted);margin-top:7px}.finding-item.active{border-color:#93b4e4;background:#edf4ff}.finding-item.risk svg{color:#cc653c}.rail-empty{font-size:13px;color:var(--muted)}.linked-canvas{height:620px;position:relative;min-width:0}.canvas-header{position:absolute;inset:15px 15px auto;display:flex;justify-content:space-between;align-items:center;gap:10px;pointer-events:none}.canvas-header button{pointer-events:auto}.linked-loading{position:absolute;inset:0;display:grid;place-items:center;background:#f5f8fbd9;color:var(--blue)}.linked-error{position:absolute;bottom:40px;left:20px;right:20px;color:var(--red);background:white;padding:12px}.evidence-rail{padding:20px 18px;border-left:1px solid var(--line);max-height:620px;overflow-y:auto}.rail-title{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.rail-title>span{font-size:12px;color:var(--muted)}.evidence-picks{display:flex;gap:8px;overflow-x:auto;padding-bottom:12px}.evidence-picks button{position:relative;border:2px solid transparent;background:var(--panel-2);padding:0;border-radius:7px;min-width:66px;width:66px;overflow:hidden}.evidence-picks button.active{border-color:var(--blue)}.evidence-picks img{width:100%;height:52px;object-fit:cover}.evidence-picks small{display:block;font-size:10px;color:var(--muted);padding:3px}.linked-photo{display:block;text-align:center;background:#f2f5f8;border-radius:8px;overflow:hidden}.linked-photo img{width:100%;max-height:230px;object-fit:contain;display:block}.photo-meta{display:grid;gap:5px;margin:12px 0}.photo-meta strong{font-size:12px;overflow-wrap:anywhere}.photo-meta span,.photo-meta small{font-size:11px;color:var(--muted)}.observation-compare{font-size:11px;margin-top:16px}.observation-compare>div{display:grid;grid-template-columns:1fr .8fr .8fr;gap:5px;border-bottom:1px solid var(--line);padding:9px 0}.observation-compare .compare-heading{color:var(--muted);font-size:10px}.observation-compare strong{font-weight:500;color:var(--text)}.linked-rules{border-top:1px solid var(--line);margin-top:20px;padding-top:16px}.linked-rules h4{font-size:14px}.linked-rules details{margin-top:12px;font-size:12px}.linked-rules summary{cursor:pointer;color:var(--blue)}.linked-rules p{font-size:12px;line-height:1.8;margin:10px 0}.evidence-empty{font-size:13px;padding:25px 0;color:var(--muted)}.workspace-bottom{border-top:1px solid var(--line);scroll-margin-top:82px}.workspace-tabs{display:flex;padding:0 20px;border-bottom:1px solid var(--line);gap:10px;overflow-x:auto}.workspace-tabs button{display:flex;align-items:center;gap:8px;white-space:nowrap;padding:17px 12px;border:0;border-bottom:2px solid transparent;background:none;color:var(--muted);font-size:14px}.workspace-tabs button.active{color:var(--blue);border-bottom-color:var(--blue);font-weight:600}.workspace-tabs span{font-size:11px;color:#b76032;background:#fff0e5;border-radius:5px;padding:2px 5px}.bottom-panel,.state-content{padding:24px}.state-grid{display:grid;grid-template-columns:1.7fr 1fr 1.3fr 1fr;gap:18px}.state-grid>div{display:grid;gap:8px;border-right:1px solid var(--line);padding-right:14px}.state-grid span{font-size:12px;color:var(--muted)}.state-grid strong{font-size:14px;font-weight:500}.selected-finding{margin-top:24px;border-top:1px solid var(--line);padding-top:22px}.selected-finding>p{margin-top:14px;font-size:14px;line-height:1.9;color:var(--text-soft)}.check-grid{display:grid;grid-template-columns:1fr 1fr;column-gap:30px;margin-top:16px}.check-grid>div{display:flex;justify-content:space-between;gap:15px;border-bottom:1px solid var(--line);padding:10px 0;font-size:13px}.check-grid strong{font-size:12px;font-weight:500;white-space:nowrap}.passed{color:var(--green)}.failed{color:var(--red)}.unknown{color:var(--amber)}.selected-finding ul,.state-missing{font-size:13px;line-height:1.8;color:var(--amber);margin-top:16px}.execution-list details{border:1px solid var(--line);border-radius:8px;margin-bottom:10px;padding:14px}.execution-list summary{display:flex;gap:12px;font-size:12px;flex-wrap:wrap;cursor:pointer}.execution-list small{margin-left:auto;color:var(--muted)}.execution-list p{font-size:12px;margin-top:12px;color:var(--muted)}.execution-list pre{font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:350px;overflow:auto;background:var(--panel-2);padding:14px}.scope-ack{display:flex;gap:10px;align-items:center;margin-top:18px;font-size:14px}.trace-empty{padding:25px;color:var(--muted)}@media(max-width:1450px){.linked-workspace{grid-template-columns:200px minmax(300px,1fr) 260px}.evidence-rail{padding:18px 14px}}@media(max-width:1200px){.linked-workspace{grid-template-columns:210px minmax(0,1fr)}.evidence-rail{grid-column:1/-1;border-left:0;border-top:1px solid var(--line);max-height:none;display:grid;grid-template-columns:1fr 1fr;column-gap:22px}.rail-title,.evidence-picks,.linked-rules,.evidence-rail>.observation-review{grid-column:1/-1}.linked-photo{grid-column:1;grid-row:3/6}.photo-meta,.observation-compare{grid-column:2}.linked-canvas{height:550px}.state-grid{grid-template-columns:1fr 1fr}}@media(max-width:720px){.linked-workspace{grid-template-columns:1fr}.scope-rail{border-right:0;border-bottom:1px solid var(--line)}.scope-rail dl{display:grid;grid-template-columns:80px 1fr;gap:8px;margin:14px 0}.scope-rail dt,.scope-rail dd{margin:0}.finding-list{display:flex;gap:10px;overflow-x:auto;align-items:flex-start}.finding-list h4{display:none}.finding-item{min-width:220px}.linked-canvas{height:480px}.evidence-rail{display:block}.evidence-picks{margin-top:12px}.linked-photo img{max-height:300px}.workspace-heading{padding:18px}.workspace-heading>div{gap:8px}.bottom-panel,.state-content{padding:18px}.check-grid{grid-template-columns:1fr}.state-grid{gap:14px}.state-grid>div{border-right:0}.workspace-tabs{padding:0 8px}}
</style>
