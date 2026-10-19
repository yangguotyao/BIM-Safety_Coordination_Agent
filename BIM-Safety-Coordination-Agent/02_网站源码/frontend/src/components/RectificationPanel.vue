<script setup lang="ts">
import { t } from '../i18n'
import { computed,reactive,ref,watch } from 'vue'
import { Upload,Loader2,ShieldCheck,CheckCircle2 } from 'lucide-vue-next'
import EvidenceReview from './EvidenceReview.vue'
import { api } from '../api'
import { errorMessage,toast } from '../store'
import { demoTime,formatDateTime,localDateTime,isoDateTime } from '../utils'
import type { CaseBundle,Evidence } from '../types'
const props=defineProps<{bundle:CaseBundle}>()
const emit=defineEmits<{updated:[value:CaseBundle]}>()
const busy=ref(''),file=ref<File|null>(null),fileInput=ref<HTMLInputElement|null>(null),selectedId=ref(''),manualConfirmed=ref(false)
const materialSource=ref<'demo'|'upload'>('upload'),demoId=ref(''),demoEvidence=ref<Evidence[]>([]),replacing=ref(false),materialsError=ref('')
const demoLabels:Record<string,{title:string;comment:string}>={
  'EV-002':{title:t('补设临边防护'),comment:'演示整改：补设高度1.2m的模拟防护栏杆，核对固定与连续性。使用内置整改示意图及模拟观察，非现场实测。'},
  'EV-010':{title:t('栏杆加高与防护复核'),comment:'演示整改：将模拟防护栏杆加高至1.2m，核对固定与连续性。使用内置整改示意图及模拟观察，非现场实测。'},
}
const form=reactive({owner:'',implemented_at:'',comment:'按批准的整改措施完成处置。',captured_at:'',reviewer:'演示安全员',as_of:''})
const current=computed(()=>props.bundle.case)
const after=computed(()=>props.bundle.evidence.filter(item=>item.stage==='after'))
const selected=computed(()=>after.value.find(item=>item.evidence_id===selectedId.value) || after.value.at(-1))
const required=computed(()=>Object.values(current.value.review?.verification_snapshot || {}).flatMap(c=>c.manual_requirements || []))
const confirmed=computed(()=>!!selected.value && (selected.value.source!=='upload' || selected.value.perception?.confirmed===true))
const before=computed(()=>props.bundle.evidence.find(item=>item.stage==='before' && current.value.findings.some(f=>f.evidence_ids.includes(item.evidence_id))) || props.bundle.evidence.find(item=>item.stage==='before'))
const recommendedId=computed(()=>before.value?.observation.guardrail_state==='present' ? 'EV-010' : 'EV-002')
const materials=computed(()=>demoEvidence.value.filter(item=>item.source==='seed' && item.stage==='after' && demoLabels[item.evidence_id] && item.observation.simulated===true &&
  item.project_id===current.value.project_id && item.model_id===current.value.model_id && item.model_version===current.value.model_version && item.zone_id===current.value.zone_id &&
  current.value.bim_guids.length>0 && current.value.bim_guids.every(guid=>item.bim_guids.includes(guid))).sort((a,b)=>Number(b.evidence_id===recommendedId.value)-Number(a.evidence_id===recommendedId.value)))
const demoMaterial=computed(()=>materials.value.find(item=>item.evidence_id===demoId.value))
const draftVisible=computed(()=>current.value.status==='approved' || !selected.value || replacing.value || !!file.value)
const materialIssue=computed(()=>{
  if(materialSource.value!=='demo' || !demoMaterial.value)return ''
  if(Date.parse(demoMaterial.value.captured_at)<=Date.parse(current.value.implementation?.implemented_at || form.implemented_at))return t('这份资料不晚于整改完成时刻，请调整演示时刻或上传新资料。')
  const height=Math.max(0,...Object.values(current.value.review?.verification_snapshot || {}).filter(c=>c.guardrail_required).map(c=>c.min_height_m))
  if(Number(demoMaterial.value.observation.guardrail_height_m)<height)return t('这份资料的防护高度未达到已批准要求，请上传新资料。')
  return ''
})
const preview=computed(()=>draftVisible.value ? materialSource.value==='demo' ? demoMaterial.value : null : selected.value?.source==='seed' ? selected.value : null)
const comparisons=computed(()=>{
  const values=(item:Evidence|null|undefined)=>{const o=item?.observation || {};return [o.guardrail_state==='present' ? t('已设置') : o.guardrail_state==='absent' ? t('未设置') : t('待确认'),o.guardrail_height_m==null ? t('待确认') : `${o.guardrail_height_m} m`,o.guardrail_fixed===true && o.guardrail_continuous===true ? t('固定、连续') : o.guardrail_fixed===false || o.guardrail_continuous===false ? t('待整改') : t('待确认'),o.worker_present===true ? t('是') : o.worker_present===false ? t('否') : t('待确认')]}
  const old=values(before.value),next=values(preview.value)
  return [t('临边防护'),t('防护高度'),t('固定与连续性'),t('人员在场')].map((label,index)=>({label,before:old[index],after:next[index]}))
})
function chooseMaterial(){
  if(materialSource.value!=='demo')return
  const item=demoMaterial.value;if(!item)return
  file.value=null;form.captured_at=item.captured_at
  form.as_of=demoTime(item.captured_at,10);form.comment=demoLabels[item.evidence_id]!.comment
}
function chooseUpload(){
  materialSource.value='upload'
  if(Object.values(demoLabels).some(item=>item.comment===form.comment))form.comment='按批准的整改措施完成处置。'
}
watch(()=>current.value.case_id,async caseId=>{
  form.owner=props.bundle.context?.task.owner || '演示机电班组'
  form.implemented_at=current.value.implementation?.implemented_at || demoTime(current.value.review?.reviewed_at || current.value.as_of,10)
  form.captured_at=demoTime(form.implemented_at,10);form.as_of=demoTime(form.captured_at,10)
  form.comment='按批准的整改措施完成处置。'
  file.value=null;selectedId.value='';manualConfirmed.value=false;replacing.value=false;demoEvidence.value=[];demoId.value='';materialsError.value='';materialSource.value='upload'
  try {
    const result=await api.get<{rows:Evidence[]}>(`/evidence?stage=after&zone_id=${encodeURIComponent(current.value.zone_id)}`)
    if(current.value.case_id!==caseId)return
    demoEvidence.value=result.rows
    if(materials.value.length){demoId.value=materials.value[0]!.evidence_id;materialSource.value='demo';if(current.value.status==='approved' || !selected.value)chooseMaterial()}
  } catch(cause){if(current.value.case_id===caseId)materialsError.value=errorMessage(cause)}
},{immediate:true})
function fileChanged(event:Event){
  const picked=(event.target as HTMLInputElement).files?.[0] || null
  if(picked && picked.size>20*1024*1024){toast(t('文件不能超过20MB'),'warning');return}
  file.value=picked
}
function update(value:CaseBundle){emit('updated',value)}
async function refresh(){emit('updated',await api.get<CaseBundle>(`/cases/${current.value.case_id}`))}
async function submit(){
  const material=materialSource.value==='demo' ? demoMaterial.value : null
  const upload=materialSource.value==='upload' ? file.value : null
  if((!material && !upload) || busy.value || materialIssue.value)return
  const capturedAt=material?.captured_at || form.captured_at
  if(Date.parse(capturedAt)<=Date.parse(current.value.implementation?.implemented_at || form.implemented_at)) {toast(t('整改后资料时刻须晚于整改完成时刻'),'warning');return}
  busy.value='submit';replacing.value=true
  try {
    let value=props.bundle
    if(current.value.status==='approved') {
      value=await api.post<CaseBundle>(`/cases/${current.value.case_id}/implementation`,{owner:form.owner,implemented_at:form.implemented_at,comment:form.comment,expected_case_version:current.value.version})
      update(value)
    }
    const prior=new Set(value.case.evidence_ids)
    if(material){
      value=await api.post<CaseBundle>(`/cases/${current.value.case_id}/evidence`,{evidence_ids:[material.evidence_id],actor:form.owner})
      selectedId.value=material.evidence_id;form.as_of=demoTime(material.captured_at,10)
    } else if(upload){
      const data=new FormData();data.append('file',upload);data.append('stage','after');data.append('captured_at',capturedAt);data.append('note',upload.name)
      value=await api.postForm<CaseBundle>(`/cases/${current.value.case_id}/evidence/upload`,data)
      selectedId.value=value.case.evidence_ids.find(id=>!prior.has(id)) || ''
    }
    update(value);replacing.value=false
    const item=value.evidence.find(e=>e.evidence_id===selectedId.value)
    file.value=null;if(fileInput.value)fileInput.value.value=''
    if(item?.source==='upload' && /\.(png|jpe?g)$/i.test(item.file_path || '')){
      busy.value='vision'
      try {await api.post(`/cases/${current.value.case_id}/evidence/${item.evidence_id}/inspect`);await refresh()}
      catch(cause){toast(errorMessage(cause),'warning')}
    }
    toast(material ? t('演示整改资料已关联，请确认后复核。') : t('整改资料已提交，请核对观察后复核。'),'success')
  } catch(cause){toast(errorMessage(cause),'error')}
  finally {busy.value=''}
}
async function verify(){
  if(!selected.value || !confirmed.value || busy.value)return
  busy.value='verify'
  try {
    const value=await api.post<CaseBundle>(`/cases/${current.value.case_id}/verify`,{after_evidence_ids:[selected.value.evidence_id],
      reviewer:form.reviewer,reviewer_confirmed:true,manual_checks_confirmed:manualConfirmed.value,as_of:form.as_of,expected_case_version:current.value.version})
    update(value);toast(value.case.status==='closed' ? t('复核通过，检查已关闭。') : t('复核未通过，请继续处理。'),value.case.status==='closed' ? 'success' : 'warning')
  } catch(cause){toast(errorMessage(cause),'error')}
  finally {busy.value=''}
}
</script>
<template>
  <section class="card rectification-panel">
    <header class="rectification-heading"><ShieldCheck :size="20" /><h2>{{ t('隐患整改与复核') }}</h2><span class="badge tone-blue">{{ current.status==='approved' ? t('待整改') : current.status==='rectifying' ? t('整改中') : t('待复核') }}</span></header>
    <div class="rectification-body">
      <div v-if="current.status==='approved'" class="rectification-fields"><label>{{ t('整改责任主体') }}<input v-model="form.owner" class="input" :aria-label="t('整改责任主体')" /></label><label>{{ t('整改完成时刻') }}<input class="input" type="datetime-local" :value="localDateTime(form.implemented_at)" :aria-label="t('整改完成时刻')" @change="form.implemented_at=isoDateTime(($event.target as HTMLInputElement).value)" /></label><label class="wide">{{ t('整改情况') }}<textarea v-model="form.comment" class="textarea" rows="2" :aria-label="t('整改情况')" /></label></div>
      <div v-else-if="current.implementation" class="rectification-record"><CheckCircle2 :size="17" /><span>{{ current.implementation.owner }} · {{ formatDateTime(current.implementation.implemented_at) }}</span><strong>{{ t('整改已提交') }}</strong></div>
      <form v-if="draftVisible" class="rectification-upload" @submit.prevent="submit">
        <div class="material-tabs"><button type="button" class="btn btn-sm" :class="{'btn-primary':materialSource==='demo'}" @click="materialSource='demo';chooseMaterial()">{{ t('选择演示整改资料') }}</button><button type="button" class="btn btn-sm" :class="{'btn-primary':materialSource==='upload'}" @click="chooseUpload">{{ t('上传新资料') }}</button></div>
        <template v-if="materialSource==='demo'"><label v-if="materials.length" class="material-select">{{ t('整改资料') }}<select v-model="demoId" class="select" :aria-label="t('选择演示整改资料')" @change="chooseMaterial"><option v-for="item in materials" :key="item.evidence_id" :value="item.evidence_id">{{ demoLabels[item.evidence_id]!.title }} · {{ item.evidence_id }}{{ item.evidence_id===recommendedId ? t('（推荐）') : '' }}</option></select></label><p v-else class="material-notice">{{ materialsError || t('当前检查范围没有匹配的内置整改资料，请上传新资料。') }}</p><div v-if="demoMaterial" class="demo-preview"><img :src="demoMaterial.image_url" :alt="demoLabels[demoMaterial.evidence_id]!.title" /><div><h3>{{ demoLabels[demoMaterial.evidence_id]!.title }}</h3><span class="badge tone-amber">{{ t('演示模拟') }}</span><span>{{ formatDateTime(demoMaterial.captured_at) }} · {{ demoMaterial.evidence_id }}</span><small>{{ t('同一区域与构件 · 内置整改示意图') }}</small></div></div></template>
        <template v-else><label class="rectification-file"><Upload :size="22" /><strong>{{ file?.name || '上传整改后照片或复核资料' }}</strong><input ref="fileInput" type="file" accept=".png,.jpg,.jpeg,.pdf" aria-label="上传整改复核资料" @change="fileChanged" /></label><label class="material-select">资料拍摄时刻<input class="input" type="datetime-local" :value="localDateTime(form.captured_at)" aria-label="整改资料拍摄时刻" @change="form.captured_at=isoDateTime(($event.target as HTMLInputElement).value)" /></label></template>
        <div v-if="preview" class="observation-comparison"><table><thead><tr><th>检查项</th><th>检查时</th><th>整改后（模拟）</th></tr></thead><tbody><tr v-for="row in comparisons" :key="row.label"><th>{{ row.label }}</th><td>{{ row.before }}</td><td>{{ row.after }}</td></tr></tbody></table></div>
        <p v-if="materialIssue" class="material-notice">{{ materialIssue }}</p><div class="upload-action"><button class="btn btn-primary" :disabled="!!busy || !!materialIssue || (materialSource==='demo' ? !demoMaterial : !file)"><Loader2 v-if="busy" :size="16" class="spin" />{{ busy==='vision' ? '正在识别整改后资料' : '提交整改与证据' }}</button><button v-if="selected && current.status!=='approved'" type="button" class="btn" :disabled="!!busy" @click="replacing=false;file=null">取消更换</button></div>
      </form>
      <template v-if="selected && !draftVisible"><div class="review-evidence"><img v-if="!selected.file_path?.endsWith('.pdf')" :src="selected.image_url || `/api/files/evidence/${selected.evidence_id}`" :alt="selected.label" /><div><h3>本次复核资料</h3><span>{{ formatDateTime(selected.captured_at) }}</span><small>{{ selected.evidence_id }}{{ selected.source==='seed' ? ' · 演示模拟' : '' }}</small><button class="btn btn-sm" :disabled="!!busy" @click="replacing=true;chooseMaterial()">更换复核资料</button></div></div><div v-if="preview" class="observation-comparison"><table><thead><tr><th>检查项</th><th>检查时</th><th>整改后（模拟）</th></tr></thead><tbody><tr v-for="row in comparisons" :key="row.label"><th>{{ row.label }}</th><td>{{ row.before }}</td><td>{{ row.after }}</td></tr></tbody></table></div><EvidenceReview v-if="selected.source==='upload' && busy!=='vision'" :key="selected.evidence_id" :evidence="selected" :case-id="current.case_id" :version="current.version" :status="current.status" @saved="update" @refresh="refresh" /><div v-if="busy==='vision'" class="vision-pending"><Loader2 class="spin" :size="16" />正在识别整改后资料</div>
        <div v-if="current.status==='pending_verification'" class="verification-confirm"><div class="rectification-fields"><label>复核人<input v-model="form.reviewer" class="input" aria-label="复核人" /></label><label>复核时刻<input class="input" type="datetime-local" :value="localDateTime(form.as_of)" aria-label="复核时刻" @change="form.as_of=isoDateTime(($event.target as HTMLInputElement).value)" /></label></div><label v-if="required.length" class="manual-check"><input v-model="manualConfirmed" type="checkbox" />已逐项核验：{{ required.join('；') }}</label><button class="btn btn-primary verify-submit" :disabled="!!busy || !confirmed || (required.length>0 && !manualConfirmed)" @click="verify"><Loader2 v-if="busy==='verify'" class="spin" :size="16" /><ShieldCheck v-else :size="16" />确认资料并执行复核</button></div>
      </template>
    </div>
  </section>
</template>
<style scoped>
.material-tabs{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}.material-select{display:grid;gap:8px;font-size:14px;margin-top:15px}.demo-preview{display:grid;grid-template-columns:160px 1fr;gap:18px;align-items:center;margin-top:18px}.demo-preview img{width:100%;height:120px;object-fit:contain;background:#f1f5f9;border-radius:8px}.demo-preview>div{display:grid;justify-items:start;gap:9px}.demo-preview h3{font-size:16px}.demo-preview span:not(.badge),.demo-preview small{font-size:12px;color:var(--muted)}.material-notice{font-size:13px;color:var(--amber);margin-top:14px}.observation-comparison{overflow-x:auto;margin-top:18px}.observation-comparison table{width:100%;border-collapse:collapse;font-size:13px}.observation-comparison th,.observation-comparison td{padding:11px 13px;border-bottom:1px solid var(--line);text-align:left}.observation-comparison thead{background:#f2f6fa}.observation-comparison tbody th{font-weight:500}.observation-comparison tbody td:last-child{color:var(--green)}@media(max-width:650px){.demo-preview{grid-template-columns:110px 1fr;gap:12px}.demo-preview h3{font-size:14px}.observation-comparison th,.observation-comparison td{padding:9px 7px}}
.rectification-heading{display:flex;align-items:center;gap:10px;padding:21px 24px;border-bottom:1px solid var(--line)}.rectification-heading>svg{color:var(--blue)}.rectification-heading h2{font-size:21px}.rectification-heading .badge{margin-left:auto}.rectification-body{padding:24px}.rectification-fields{display:grid;grid-template-columns:1fr 1fr;gap:16px}.rectification-fields label,.upload-action label{display:grid;gap:8px;font-size:14px;min-width:0}.rectification-fields .wide{grid-column:1/-1}.rectification-upload{margin-top:22px}.rectification-file{display:grid;justify-items:center;gap:12px;padding:25px;border:1px dashed #b6c9dd;border-radius:10px;background:#f8fafc;color:var(--blue)}.rectification-file strong{font-size:14px}.rectification-file input{font-size:12px;max-width:100%}.upload-action{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-top:16px}.upload-action label{flex:1}.rectification-record{display:flex;align-items:center;gap:9px;padding:14px;background:#f0f8f4;color:var(--green);border-radius:9px;font-size:13px;flex-wrap:wrap}.rectification-record strong{margin-left:auto;font-weight:500}.review-evidence{display:grid;grid-template-columns:180px 1fr;gap:20px;align-items:center;margin-top:20px}.review-evidence>img{width:100%;height:130px;object-fit:contain;border-radius:8px;background:#f1f5f9}.review-evidence>div{display:grid;gap:9px;justify-items:start}.review-evidence span,.review-evidence small{font-size:12px;color:var(--muted)}.review-evidence input{display:none}.verification-confirm{border-top:1px solid var(--line);padding-top:22px;margin-top:22px}.verify-submit{margin-top:20px;min-height:44px}.manual-check{display:flex;align-items:center;gap:8px;font-size:13px;margin-top:15px}.vision-pending{display:flex;gap:8px;color:var(--blue);font-size:13px;padding:18px 0}@media(max-width:650px){.rectification-body{padding:18px}.rectification-fields{grid-template-columns:1fr}.upload-action{flex-direction:column;align-items:stretch}.review-evidence{grid-template-columns:130px 1fr;gap:12px}.rectification-heading{padding:18px}.rectification-heading h2{font-size:19px}}
</style>
