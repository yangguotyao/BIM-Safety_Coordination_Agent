<script setup lang="ts">
import { computed,reactive,ref } from 'vue'
import { Plus,FileText,Save,Loader2,ScanText } from 'lucide-vue-next'
import { api } from '../api'
import { errorMessage,toast } from '../store'
import { formatDateTime,localDateTime,isoDateTime } from '../utils'
import type { CaseBundle,SiteNote } from '../types'
const props=defineProps<{bundle:CaseBundle}>()
const emit=defineEmits<{updated:[bundle:CaseBundle];selectEvidence:[id:string]}>()
const busy=ref(''),editing=ref(false)
const form=reactive({title:'巡检记录',source:'现场巡检',captured_at:'',body:'',supersedes_note_id:null as string|null})
const resolutions=reactive<Record<string,{decision:string;reason:string}>>({})
const canEdit=computed(()=>['draft','needs_evidence','pending_review','reopened','rejected'].includes(props.bundle.case.status))
const notes=computed(()=>props.bundle.site_notes || [])
const context=computed(()=>props.bundle.site_text || {conflicts:[],facts:[],pending_notes:[],missing_fields:[]})
const fieldLabels:Record<string,string>={guardrail_state:'临边防护',guardrail_height_m:'防护高度',drop_height_m:'坠落高度',worker_present:'人员在场',guardrail_fixed:'防护固定',guardrail_continuous:'防护连续',boundary_is_exposed:'检查边界暴露',ppe_confirmed:'PPE',record_relevance:'记录有效性'}
const value=(item:any)=>item==null ? '未知' : item===true ? '是' : item===false ? '否' : item==='present' ? '已设置' : item==='absent' ? '未设置' : String(item)
function edit(note?:SiteNote) {
  Object.assign(form,note ? {title:note.title,source:note.source,captured_at:note.captured_at,body:note.body,supersedes_note_id:note.note_id} :
    {title:'巡检记录',source:'现场巡检',captured_at:props.bundle.case.as_of,body:'',supersedes_note_id:null})
  editing.value=true
}
async function save() {
  busy.value='save'
  try {
    const result=await api.post<CaseBundle>(`/cases/${props.bundle.case.case_id}/site-notes`,{...form,expected_case_version:props.bundle.case.version})
    editing.value=false;emit('updated',result);toast('现场记录已保存。','success')
  } catch(cause) {toast(errorMessage(cause),'error')}
  finally {busy.value=''}
}
async function extract(note:SiteNote) {
  busy.value=note.note_id
  try {
    const result=await api.post<CaseBundle>(`/cases/${props.bundle.case.case_id}/site-notes/${note.note_id}/extract`)
    emit('updated',result);toast('文本候选与来源已保存。','success')
  } catch(cause) {toast(errorMessage(cause),'error')}
  finally {busy.value=''}
}
function resolution(id:string) {
  return resolutions[id] ||= {decision:'retain_observation',reason:''}
}
async function resolve(conflict:any) {
  busy.value=conflict.conflict_id
  try {
    const result=await api.post<CaseBundle>(`/cases/${props.bundle.case.case_id}/site-notes/resolve`,{
      conflict_id:conflict.conflict_id,observation_hash:conflict.observation_hash,...resolution(conflict.conflict_id),expected_case_version:props.bundle.case.version})
    emit('updated',result);toast('人工澄清已保存。','success')
  } catch(cause) {toast(errorMessage(cause),'error')}
  finally {busy.value=''}
}
</script>
<template>
  <section class="site-notes-panel">
    <header class="notes-heading"><div><FileText :size="19" /><h3>现场文本</h3><span class="badge tone-slate">{{ notes.filter(n=>n.current).length }}</span></div><button v-if="canEdit && !editing" class="btn btn-sm" @click="edit()"><Plus :size="15" />新增记录</button></header>
    <form v-if="editing" class="note-form" @submit.prevent="save"><div class="note-fields"><label>记录名称<input v-model="form.title" class="input" aria-label="现场记录名称" required /></label><label>来源<input v-model="form.source" class="input" aria-label="现场记录来源" required /></label><label>记录时刻<input :value="localDateTime(form.captured_at)" type="datetime-local" @change="form.captured_at=isoDateTime(($event.target as HTMLInputElement).value)" class="input" aria-label="现场记录时刻" required /></label></div><label>记录原文<textarea v-model="form.body" class="textarea" rows="5" maxlength="6000" aria-label="现场记录原文" required /></label><div class="note-actions"><button type="button" class="btn" @click="editing=false">取消</button><button class="btn btn-primary" :disabled="!!busy"><Save :size="15" />保存记录</button></div></form>
    <div v-if="context.pending_notes?.length" class="note-pending">{{ context.pending_notes.length }} 份记录待提取候选</div>
    <div v-if="context.missing_fields?.length" class="note-pending">待人工补充：{{ context.missing_fields.map((key:string)=>fieldLabels[key] || key).join('、') }}</div>
    <article v-for="conflict in context.conflicts || []" :key="conflict.conflict_id" class="text-conflict" :class="{resolved:conflict.resolution}"><header><strong>{{ fieldLabels[conflict.field] || conflict.field }} · {{ conflict.resolution ? '已澄清' : '存在差异' }}</strong><button v-if="conflict.evidence_id" class="btn btn-sm" @click="emit('selectEvidence',conflict.evidence_id)">核对照片</button></header><div class="comparison"><div><span>文本候选</span><strong>{{ value(conflict.text_value) }}</strong><a :href="`#${conflict.paragraph_id}`">{{ conflict.paragraph_id }}</a></div><div><span>已确认观察</span><strong>{{ value(conflict.observation_value) }}</strong><small>{{ conflict.evidence_id }}</small></div></div><blockquote>{{ conflict.quote }}</blockquote><p v-if="conflict.resolution" class="resolved-reason">{{ conflict.resolution.reason }} · {{ formatDateTime(conflict.resolution.at) }}</p><form v-else-if="canEdit" class="resolution-form" @submit.prevent="resolve(conflict)"><select v-model="resolution(conflict.conflict_id).decision" class="select" aria-label="文本差异处理"><option value="retain_observation">保留图像观察</option><option value="text_unreliable">文本不作为判定依据</option></select><input v-model="resolution(conflict.conflict_id).reason" class="input" aria-label="文本澄清依据" minlength="3" placeholder="核对依据" required /><button class="btn btn-primary" :disabled="!!busy">确认澄清</button></form></article>
    <div v-if="context.excluded_notes?.length" class="excluded-text">{{ context.excluded_notes.length }} 份记录在本次时间范围外</div>
    <details v-for="note in notes" :key="note.note_id" class="note-record" :open="note.current"><summary><strong>{{ note.title }}</strong><span>{{ note.source }} · {{ formatDateTime(note.captured_at) }}</span><span class="badge tone-slate">v{{ note.version }}{{ note.current ? '' : ' · 历史' }}</span></summary><div class="note-content"><p v-for="paragraph in note.paragraphs" :id="paragraph.id" :key="paragraph.id"><small class="mono">{{ paragraph.id }}</small>{{ paragraph.text }}</p><div v-if="note.analysis" class="note-extraction"><strong>{{ note.analysis.model }}</strong><p>{{ note.analysis.summary }}</p><ul><li v-for="(fact,index) in note.analysis.facts" :key="index">{{ fieldLabels[fact.field] }}：{{ value(fact.value) }} <a :href="`#${fact.paragraph_id}`">原文</a><q>{{ fact.quote }}</q></li></ul><p v-for="uncertainty in note.analysis.uncertainties" :key="uncertainty" class="uncertainty">{{ uncertainty }}</p></div><div v-if="canEdit && note.current" class="note-actions"><button v-if="!note.analysis" class="btn btn-sm btn-primary" :disabled="!!busy" @click="extract(note)"><Loader2 v-if="busy===note.note_id" :size="15" class="spin" /><ScanText v-else :size="15" />提取文本候选</button><button class="btn btn-sm" @click="edit(note)">修订记录</button></div></div></details>
    <div v-if="!notes.length && !editing" class="notes-empty">暂无现场文本记录</div>
  </section>
</template>
<style scoped>
.notes-heading,.notes-heading>div{display:flex;align-items:center;gap:10px}.notes-heading{justify-content:space-between;margin-bottom:20px}.note-form{padding:20px;background:var(--panel-2);border-radius:10px;margin-bottom:20px}.note-form label{display:grid;gap:7px;font-size:13px;margin-bottom:14px;min-width:0}.note-fields{display:grid;grid-template-columns:1fr 1fr 1.2fr;gap:12px}.note-actions{display:flex;justify-content:flex-end;gap:10px;margin-top:14px}.note-pending{padding:12px 15px;background:#fff7e7;border:1px solid #f2ddac;border-radius:8px;margin-bottom:15px;color:#8f641c;font-size:13px}.text-conflict{border:1px solid #f0c8bd;border-radius:10px;margin-bottom:16px;padding:18px;background:#fffaf7}.text-conflict.resolved{background:#f7fcfa;border-color:#c5dfd4}.text-conflict>header{display:flex;align-items:center;justify-content:space-between;gap:15px;font-size:14px;margin-bottom:15px}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:12px}.comparison>div{display:grid;gap:7px;padding:14px;background:white;border-radius:8px;border:1px solid var(--line)}.comparison span,.comparison small,.comparison a{font-size:12px;color:var(--muted);overflow-wrap:anywhere}.comparison strong{font-size:16px}.text-conflict blockquote{margin:14px 0;font-size:14px;padding:8px 12px;border-left:3px solid #d9987d;color:var(--text-soft)}.resolution-form{display:flex;gap:10px;flex-wrap:wrap}.resolution-form .select{width:185px}.resolution-form input{flex:1;min-width:160px}.resolved-reason{font-size:13px;color:var(--green)}.note-record{border:1px solid var(--line);border-radius:10px;margin-bottom:14px}.note-record summary{cursor:pointer;padding:17px;display:flex;align-items:center;gap:15px;flex-wrap:wrap}.note-record summary>strong{font-size:14px}.note-record summary>span{font-size:12px;color:var(--muted)}.note-content{border-top:1px solid var(--line);padding:18px}.note-content>p{font-size:14px;line-height:1.9;scroll-margin-top:90px;margin-bottom:12px}.note-content>p>small{display:block;color:var(--dim);font-size:11px}.note-extraction{background:var(--panel-2);padding:15px;border-radius:8px;margin-top:16px;font-size:13px;line-height:1.8}.note-extraction>strong{font-size:12px;color:var(--blue)}.note-extraction q{display:block;color:var(--muted)}.note-extraction ul{padding-left:20px}.uncertainty,.excluded-text{font-size:12px;color:var(--muted)}.excluded-text{margin-bottom:14px}.notes-empty{text-align:center;padding:30px;color:var(--muted)}@media(max-width:700px){.note-fields{grid-template-columns:1fr}.resolution-form .select{width:100%}.note-record summary{gap:8px}}
</style>
