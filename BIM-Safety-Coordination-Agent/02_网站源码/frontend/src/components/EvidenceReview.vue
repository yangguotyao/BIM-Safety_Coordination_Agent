<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Loader2, ScanEye, CheckCircle2 } from 'lucide-vue-next'
import { api } from '../api'
import { errorMessage, toast } from '../store'
import type { CaseBundle, Evidence } from '../types'
const props = defineProps<{evidence:Evidence; caseId:string; version:number; status:string}>()
const emit = defineEmits<{refresh:[]; saved:[bundle:CaseBundle]}>()
const candidate = ref<Record<string,any>>(props.evidence.perception || {})
const busy = ref(''), editing = ref(false), acknowledged = ref(false)
const source = ref('simulated'), note = ref('本演示由人工核对并填写观察参数。')
const form = reactive<Record<string,any>>({})
const boolFields = [
  ['worker_present','人员在场'], ['boundary_is_exposed','检查边界暴露'],
  ['guardrail_fixed','防护固定'], ['guardrail_continuous','防护连续'], ['ppe_confirmed','PPE已确认'],
]
const locked = computed(() => ['closed','analyzing'].includes(props.status) ||
  (props.evidence.stage==='before' && ['approved','rectifying','pending_verification'].includes(props.status)))
const isImage = computed(() => /\.(png|jpe?g)$/i.test(props.evidence.file_path || ''))
watch(() => props.evidence.perception, value => { candidate.value=value || {}; if(!editing.value) resetForm() },{deep:true})
function resetForm() {
  const values = candidate.value.confirmed ? props.evidence.observation : candidate.value.observation || props.evidence.observation
  form.guardrail_state = values.guardrail_state || 'unknown'
  for (const [key] of boolFields) form[key] = values[key]===true ? 'true' : values[key]===false ? 'false' : 'unknown'
  form.guardrail_height_m = values.guardrail_height_m ?? ''
  form.drop_height_m = values.drop_height_m ?? ''
  for (const [i,key] of ['x','y','z'].entries()) form[key] = values.worker_point_m?.[i] ?? ''
  source.value = candidate.value.source || 'simulated'
  note.value = candidate.value.human_note || '本演示由人工核对并填写观察参数。'
  acknowledged.value = false
}
function edit() { resetForm(); editing.value=!editing.value }
async function inspect() {
  busy.value='vision'
  try {
    const result = await api.post<{perception:Record<string,any>}>(`/cases/${props.caseId}/evidence/${props.evidence.evidence_id}/inspect`)
    candidate.value=result.perception
    resetForm(); editing.value=true
    emit('refresh')
    toast('图像观察候选已生成，请核对并补充测量参数。','success')
  } catch(cause) { toast(errorMessage(cause),'error',8000) }
  finally { busy.value='' }
}
const number = (value:any) => value==='' || value==null ? null : Number(value)
async function save() {
  busy.value='save'
  try {
    const observation:Record<string,any> = {guardrail_state:form.guardrail_state,
      guardrail_height_m:number(form.guardrail_height_m),drop_height_m:number(form.drop_height_m),
      worker_point_m: ['x','y','z'].every(key => form[key]!=='') ? ['x','y','z'].map(key=>Number(form[key])) : null}
    for (const [key] of boolFields) observation[key] = form[key]==='unknown' ? null : form[key]==='true'
    const result = await api.post<CaseBundle>(`/cases/${props.caseId}/evidence/${props.evidence.evidence_id}/observation`,
      {observation,source:source.value,note:note.value,expected_case_version:props.version})
    editing.value=false
    candidate.value=result.evidence.find(item=>item.evidence_id===props.evidence.evidence_id)?.perception || {}
    emit('saved',result)
    toast('观察已确认。检查时证据可重新分析，实施后证据可继续复核。','success',6000)
  } catch(cause) { toast(errorMessage(cause),'error',8000) }
  finally { busy.value='' }
}
</script>

<template>
  <section class="observation-review">
    <div class="observation-status"><CheckCircle2 v-if="candidate.confirmed" :size="16" /><ScanEye v-else :size="16" /><strong>{{ candidate.confirmed ? '观察已由人工确认' : candidate.status==='candidate' ? '图像已识别，等待人工确认' : '新证据尚待观察与确认' }}</strong></div>
    <div v-if="candidate.summary" class="vision-result"><span>{{ candidate.model }} · 图像观察候选</span><p>{{ candidate.summary }}</p><ul v-if="candidate.uncertainties?.length"><li v-for="item in candidate.uncertainties" :key="item">{{ item }}</li></ul></div>
    <div v-if="!locked" class="row"><button v-if="isImage && !candidate.status" class="btn btn-sm" :disabled="!!busy" @click="inspect"><Loader2 v-if="busy==='vision'" class="spin" :size="14" /><ScanEye v-else :size="14" /> Qwen 分析图片</button><button class="btn btn-sm" :disabled="!!busy" @click="edit">{{ editing ? '收起观察表单' : candidate.confirmed ? '修改人工观察' : '确认现场观察' }}</button></div>
    <form v-if="editing && !locked" class="observation-form" @submit.prevent="save">
      <label>临边防护<select v-model="form.guardrail_state" class="select" aria-label="临边防护观察"><option value="unknown">待确认</option><option value="absent">未设置</option><option value="present">已设置</option></select></label>
      <label v-for="[key,label] in boolFields" :key="key">{{ label }}<select v-model="form[key]" class="select" :aria-label="label"><option value="unknown">待确认</option><option value="true">是</option><option value="false">否</option></select></label>
      <label>防护高度（m）<input v-model="form.guardrail_height_m" class="input" type="number" min="0" max="1000" step="0.01" aria-label="防护高度（m）" placeholder="人工测量或模拟值" /></label>
      <label>坠落高度（m）<input v-model="form.drop_height_m" class="input" type="number" min="0" max="1000" step="0.01" aria-label="坠落高度（m）" placeholder="不使用模型绝对标高" /></label>
      <details class="full"><summary>补充人员三维标注（可选，单位 m）</summary><div class="coordinate-fields"><input v-for="key in ['x','y','z']" :key="key" v-model="form[key]" class="input" type="number" step="any" :aria-label="`人员坐标 ${key}`" :placeholder="key.toUpperCase()" /></div></details>
      <label class="full">观察来源<select v-model="source" class="select" aria-label="观察来源"><option value="simulated">本演示人工模拟标注</option><option value="human_observed">人工核对的现场观察与测量</option></select></label>
      <label class="full">核对说明<textarea v-model="note" class="textarea" rows="2" required aria-label="观察核对说明" /></label>
      <label class="full acknowledge"><input v-model="acknowledged" type="checkbox" required /> 我已核对来源与观察值；未知项保留为待确认。</label>
      <button class="btn btn-primary full" :disabled="!acknowledged || !!busy"><Loader2 v-if="busy==='save'" class="spin" :size="14" /> 保存并确认观察</button>
    </form>
    <span v-else-if="locked" class="badge tone-slate">观察已冻结</span>
  </section>
</template>

<style scoped>
.observation-review{margin-top:16px;padding-top:15px;border-top:1px solid var(--line)}.observation-status{display:flex;gap:7px;align-items:center;font-size:13px;color:var(--blue)}.vision-result{padding:12px;border-radius:8px;background:var(--panel-2);margin:12px 0;font-size:12px;line-height:1.8}.vision-result>span{font-size:11px;color:var(--muted)}.vision-result p{margin-top:7px}.vision-result ul{padding-left:18px;color:var(--muted)}.observation-note{font-size:11px;line-height:1.8;color:var(--muted);margin:10px 0}.observation-form{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:15px}.observation-form label{font-size:12px;display:grid;gap:7px;min-width:0}.observation-form .full{grid-column:1/-1}.observation-form .acknowledge{display:flex;align-items:flex-start;line-height:1.8}.acknowledge input{margin-top:5px}.coordinate-fields{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.observation-form summary{font-size:12px;cursor:pointer;color:var(--blue)}@media(max-width:600px){.observation-form{grid-template-columns:1fr}}
</style>
