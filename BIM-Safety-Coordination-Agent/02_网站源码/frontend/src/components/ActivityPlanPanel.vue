<script setup lang="ts">
import { computed,ref,watch } from 'vue'
import { Plus,CalendarClock,Save,Trash2,Loader2 } from 'lucide-vue-next'
import { api } from '../api'
import { errorMessage,toast } from '../store'
import { formatDateTime,formatTime,localDateTime,isoDateTime } from '../utils'
import type { Activity,CaseBundle } from '../types'
const props=defineProps<{bundle:CaseBundle}>()
const emit=defineEmits<{updated:[bundle:CaseBundle];preview:[activities:Activity[]];selectPair:[id:string]}>()
const values=ref<Activity[]>([]),editing=ref(false),saving=ref(false),reason=ref('')
const caseData=computed(()=>props.bundle.case)
const execution=computed(()=>['approved','rectifying','pending_verification'].includes(caseData.value.status))
const canEdit=computed(()=>['draft','needs_evidence','pending_review','reopened','rejected'].includes(caseData.value.status) || (execution.value && caseData.value.controls.some(c=>c.verification_criteria?.coordination_required)))
const coordination=computed(()=>props.bundle.coordination || {})
watch(()=>`${caseData.value.case_id}:${props.bundle.activity_plan?.revision || 0}`,()=>{
  values.value=JSON.parse(JSON.stringify(props.bundle.activity_plan?.activities || []))
  editing.value=false;reason.value='';emit('preview',values.value)
},{immediate:true})
watch(values,()=>{if(editing.value) emit('preview',values.value)},{deep:true})
function makeActivity(index:number):Activity {
  const task=props.bundle.context?.task || {},zone=props.bundle.context?.zone.data || {}
  const box=zone.target?.bbox_m,p=zone.worker_point_m || box?.min || [18,20,17.3]
  return {task_id:`ACT-${String(index+1).padStart(2,'0')}`,activity:index===0 ? task.activity || '材料转运' : '相邻墙面作业',
    trade:index===0 ? '机电' : '装修',owner:index===0 ? task.owner || '机电班组' : '装修班组',
    planned_start:task.planned_start,planned_end:task.planned_end,bim_guids:[...caseData.value.bim_guids],
    workspace:{min:[p[0]-1.5,p[1]-2,p[2]],max:[p[0]+1.5,p[1]+2,p[2]+2]}}
}
function startEditing() {
  editing.value=true
  if (!values.value.length) values.value=[makeActivity(0),makeActivity(1)]
  emit('preview',values.value)
}
function addActivity() {
  const next=makeActivity(values.value.length)
  while(values.value.some(item=>item.task_id===next.task_id)) next.task_id+='N'
  values.value.push(next)
}
const timeline=computed(()=>{
  const valid=values.value.flatMap(a=>[Date.parse(a.planned_start || ''),Date.parse(a.planned_end || '')]).filter(Number.isFinite)
  const start=valid.length ? Math.min(...valid) : 0,end=valid.length ? Math.max(...valid) : 1
  return {start,end,valid:valid.length>0,span:Math.max(end-start,60000)}
})
function bar(activity:Activity) {
  const start=Date.parse(activity.planned_start || ''),end=Date.parse(activity.planned_end || '')
  return {left:`${(start-timeline.value.start)/timeline.value.span*100}%`,width:`${Math.max(1,(end-start)/timeline.value.span*100)}%`}
}
const missingLabel=(key:string)=>key.replace(/\.(trade|owner|planned_start|planned_end|bim_guids|workspace)$/,(_,field)=>' · '+({trade:'工种',owner:'责任主体',planned_start:'开始时间',planned_end:'结束时间',bim_guids:'关联构件',workspace:'作业范围'} as Record<string,string>)[field])
const conflictTasks=computed(()=>new Set<string>((coordination.value.conflicts || []).flatMap((p:any)=>p.task_ids)))
async function save() {
  saving.value=true
  try {
    const result=await api.put<CaseBundle>(`/cases/${caseData.value.case_id}/activity-plan`,{
      activities:values.value,reason:reason.value || '人工编制演示作业计划',expected_case_version:caseData.value.version})
    editing.value=false;emit('updated',result)
    toast(result.coordination?.complete ? result.coordination?.conflicts.length ? '计划已保存，存在时空冲突。' : '计划校核通过。' : '计划已保存，请补齐活动资料。','success')
  } catch(cause) { toast(errorMessage(cause),'error') }
  finally { saving.value=false }
}
</script>
<template>
  <section class="activity-panel">
    <header class="panel-heading"><div><CalendarClock :size="19" /><h3>施工活动</h3><span v-if="bundle.activity_plan" class="badge tone-slate">v{{ bundle.activity_plan.revision }}</span><span v-if="editing" class="badge tone-amber">未保存</span></div><button v-if="canEdit && !editing" class="btn btn-sm" @click="startEditing">{{ values.length ? '调整计划' : '编制作业计划' }}</button></header>
    <template v-if="values.length">
      <div v-if="timeline.valid" class="time-scale"><span>{{ formatDateTime(new Date(timeline.start).toISOString()) }}</span><span>{{ formatDateTime(new Date(timeline.end).toISOString()) }}</span></div>
      <div v-for="item in values" :key="item.task_id" class="activity-track"><div><strong>{{ item.activity }}</strong><span>{{ item.owner || '责任人待补充' }}</span></div><div class="track"><span v-if="item.planned_start && item.planned_end" :style="bar(item)" :class="{conflict:!editing && conflictTasks.has(item.task_id)}">{{ formatTime(item.planned_start) }}–{{ formatTime(item.planned_end) }}</span></div></div>
      <div v-if="!editing && coordination.configured" class="coord-result"><span class="badge" :class="!coordination.complete ? 'tone-amber' : coordination.conflicts.length ? 'tone-red' : 'tone-green'">{{ !coordination.complete ? '活动资料待补充' : coordination.conflicts.length ? `${coordination.conflicts.length} 组时空冲突` : '当前计划无时空冲突' }}</span><span v-if="coordination.missing_fields?.length" class="missing">{{ coordination.missing_fields.map(missingLabel).join('、') }}</span></div>
      <button v-for="pair in coordination.conflicts || []" :key="pair.pair_id" class="conflict-row" @click="emit('selectPair',pair.pair_id)"><strong>{{ pair.activities.join(' / ') }}</strong><span>{{ pair.owners.join(' · ') }}</span><span>{{ formatTime(pair.overlap_start) }}–{{ formatTime(pair.overlap_end) }}</span><span>定位冲突区域 →</span></button>
      <form v-if="editing" class="activity-form" @submit.prevent="save">
        <article v-for="(item,index) in values" :key="item.task_id" class="activity-input">
          <div class="activity-title"><strong>活动 {{ index+1 }}</strong><span class="mono">{{ item.task_id }}</span><button v-if="!execution" type="button" class="btn btn-ghost btn-icon btn-sm" :disabled="values.length<=2" :aria-label="`删除活动${index+1}`" @click="values.splice(index,1)"><Trash2 :size="15" /></button></div>
          <div class="activity-fields"><label>活动名称<input v-model="item.activity" :aria-label="`活动${index+1}名称`" class="input" :disabled="execution" required /></label><label>工种<input v-model="item.trade" :aria-label="`活动${index+1}工种`" class="input" :disabled="execution" /></label><label>责任主体<input v-model="item.owner" :aria-label="`活动${index+1}责任人`" class="input" :disabled="execution" /></label></div>
          <div class="activity-dates"><label>开始<input :value="localDateTime(item.planned_start)" type="datetime-local" @change="item.planned_start=isoDateTime(($event.target as HTMLInputElement).value) || null" :aria-label="`活动${index+1}开始`" class="input" /></label><label>结束<input :value="localDateTime(item.planned_end)" type="datetime-local" @change="item.planned_end=isoDateTime(($event.target as HTMLInputElement).value) || null" :aria-label="`活动${index+1}结束`" class="input" /></label></div>
          <details class="workspace-fields"><summary>作业范围（m）</summary><button v-if="!item.workspace" type="button" class="btn btn-sm" @click="item.workspace=makeActivity(index).workspace">设置范围</button><div v-else class="volume-fields"><label v-for="(axis,i) in ['X','Y','Z']" :key="axis">{{ axis }} 最小<input v-model.number="item.workspace.min[i]" class="input" type="number" step="any" :aria-label="`活动${index+1}${axis}最小`" /></label><label v-for="(axis,i) in ['X','Y','Z']" :key="axis+'max'">{{ axis }} 最大<input v-model.number="item.workspace.max[i]" class="input" type="number" step="any" :aria-label="`活动${index+1}${axis}最大`" /></label></div></details>
        </article>
        <div class="plan-save"><button v-if="!execution" type="button" class="btn" :disabled="values.length>=8" @click="addActivity"><Plus :size="16" />增加活动</button><label>调整依据<input v-model="reason" aria-label="计划调整依据" class="input" :required="execution" /></label><button class="btn btn-primary" :disabled="saving"><Loader2 v-if="saving" :size="15" class="spin" /><Save v-else :size="15" />保存并校核</button></div>
      </form>
      <details v-if="bundle.activity_plan?.history.length" class="plan-history"><summary>计划版本</summary><p v-for="item in bundle.activity_plan.history" :key="item.revision">v{{ item.revision }} · {{ item.reason }} · {{ formatDateTime(item.at) }}</p></details>
    </template>
    <div v-else class="panel-empty">暂无多活动计划</div>
  </section>
</template>
<style scoped>
.panel-heading,.panel-heading>div{display:flex;align-items:center;gap:10px}.panel-heading{justify-content:space-between;margin-bottom:22px}.time-scale{display:flex;justify-content:space-between;font-size:12px;color:var(--muted);margin-left:235px;padding-bottom:12px}.activity-track{display:grid;grid-template-columns:220px 1fr;gap:15px;align-items:center;margin-bottom:16px}.activity-track strong,.activity-track div>span{display:block}.activity-track strong{font-size:14px}.activity-track div>span:not(.track>span){font-size:12px;color:var(--muted);margin-top:4px}.track{height:36px;border-radius:7px;background:repeating-linear-gradient(90deg,#f1f5f9,#f1f5f9 calc(25% - 1px),#dee7f1 25%);position:relative}.track>span{position:absolute;top:4px;height:28px;display:flex;align-items:center;justify-content:center;background:#c6e2f4;color:#295b7c;border-radius:5px;font-size:12px;min-width:65px}.track>span.conflict{background:#f8d9d1;color:#ab472d}.coord-result{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:20px 0}.missing{font-size:12px;color:var(--amber)}.conflict-row{display:flex;width:100%;text-align:left;align-items:center;gap:20px;flex-wrap:wrap;border:1px solid #f1cbc0;border-radius:9px;background:#fff8f5;padding:16px;margin-top:10px;color:var(--text-soft);font-size:13px}.conflict-row strong{flex:1;color:#a9442c}.conflict-row>span:last-child{color:var(--blue)}.activity-form{margin-top:24px}.activity-input{border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:14px}.activity-title{display:flex;align-items:center;gap:12px;margin-bottom:16px}.activity-title .mono{font-size:12px;color:var(--muted)}.activity-title button{margin-left:auto}.activity-fields{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}.activity-dates{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}.activity-form label{display:grid;gap:7px;font-size:13px;min-width:0}.workspace-fields{margin-top:16px}.workspace-fields summary,.plan-history summary{cursor:pointer;color:var(--blue);font-size:13px}.volume-fields{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:14px}.plan-save{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}.plan-save label{flex:1;min-width:180px}.plan-history{margin-top:20px;border-top:1px solid var(--line);padding-top:16px}.plan-history p{font-size:12px;margin-top:10px;color:var(--muted)}.panel-empty{padding:30px;text-align:center;color:var(--muted)}@media(max-width:700px){.activity-track{grid-template-columns:1fr;gap:8px}.time-scale{margin-left:0}.activity-fields,.activity-dates{grid-template-columns:1fr}.conflict-row{gap:10px}}
</style>
