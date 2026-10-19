<script setup lang="ts">
import { computed,onBeforeUnmount,ref,watch } from 'vue'
import { Sparkles,Loader2,CheckCircle2,AlertTriangle } from 'lucide-vue-next'
import type { CaseBundle,Run } from '../types'
import { localeState, t } from '../i18n'
const props=defineProps<{bundle:CaseBundle;run:Run|null}>()
const emit=defineEmits<{completed:[]}>()
const text=ref(''),outputStatus=ref(''),phase=ref(''),doneTools=ref<string[]>([])
const running=computed(()=>props.bundle.case.status==='analyzing')
const programmed=computed(()=>props.bundle.case.findings.some(f=>(f.narrative as any)?.source==='deterministic_gap_planner'))
const model=computed(()=>programmed.value ? t('规则检查') : props.bundle.model_calls?.find(c=>c.purpose==='risk_summary')?.model || 'Agent')
const toolLabels:Record<string,string>={policy_plan:t('检查计划'),bim_query:t('模型范围'),schedule_query:t('活动时间'),evidence_check:t('现场资料'),spatial_check:t('距离校核'),rule_retrieval:t('规范依据'),activity_conflict_check:t('时空冲突'),site_text_query:t('现场文本'),openai_compatible_chat:t('分析结论'),live_control_draft:t('整改建议'),decision_audit:t('约束校核'),bounded_replan:t('定向补证')}
function toolLabel(code:string):string{const zh=toolLabels[code];return zh ? t(zh) : code}
const completedTools=computed(()=>[...new Set([...doneTools.value,...(props.run?.events || []).filter(event=>['succeeded','cached','succeeded_after_retry'].includes(event.status) && event.tool && toolLabels[event.tool]).map(event=>event.tool!)])])
let source:EventSource|null=null,frame=0,target=''
function close(){source?.close();source=null;cancelAnimationFrame(frame);frame=0}
function paint(){
  if(!target.startsWith(text.value))text.value=''
  text.value=target.slice(0,text.value.length+3)
  if(text.value.length<target.length)frame=requestAnimationFrame(paint)
  else frame=0
}
function receive(value:{text:string;status:string}){
  outputStatus.value=value.status
  if(value.status==='rejected'){target='';text.value='';cancelAnimationFrame(frame);frame=0;return}
  // 英文模式下不渲染中文增量，完成后由已翻译的 narrative 一次性呈现。
  if(localeState.locale==='en' && running.value){target='';text.value='';cancelAnimationFrame(frame);frame=0;return}
  target=value.text
  if(!running.value)text.value=target
  else if(!frame)frame=requestAnimationFrame(paint)
}
watch([()=>props.run?.run_id,()=>props.bundle.case.status],()=>{
  close();phase.value='';doneTools.value=[]
  const stale=props.bundle.case.status==='draft' && !props.bundle.case.safety_state
  const narrative=stale || running.value ? '' : props.bundle.case.findings.find(f=>f.narrative?.summary)?.narrative?.summary || ''
  text.value=narrative;target=narrative;outputStatus.value=narrative ? 'validated' : ''
  if(!running.value || !props.run?.run_id)return
  source=new EventSource(`/api/runs/${encodeURIComponent(props.run.run_id)}/stream`)
  source.addEventListener('output',event=>receive(JSON.parse((event as MessageEvent).data)))
  source.addEventListener('node',event=>{
    const node=JSON.parse((event as MessageEvent).data)
    phase.value=toolLabel(node.tool) || node.node
    if(['succeeded','cached','succeeded_after_retry'].includes(node.status) && toolLabels[node.tool] && !doneTools.value.includes(node.tool))doneTools.value.push(node.tool)
  })
  source.addEventListener('complete',()=>{source?.close();source=null;emit('completed')})
},{immediate:true})
onBeforeUnmount(close)
</script>
<template>
  <section class="card ai-analysis" :aria-label="t('AI 分析结果')">
    <header><span class="ai-symbol"><Sparkles :size="21" /></span><h2>{{ t('AI 检查分析') }}</h2><span class="analysis-status" :class="{live:running}"><Loader2 v-if="running" class="spin" :size="14" /><CheckCircle2 v-else-if="text" :size="14" />{{ running ? phase || t('正在理解检查任务') : run?.status==='failed' ? t('分析未完成') : text ? t('分析已完成') : t('等待分析') }}</span></header>
    <div class="ai-output" :class="{empty:!text}" aria-live="polite"><p v-if="text">{{ text }}<span v-if="running" class="stream-cursor" /></p><p v-else-if="running">{{ t('正在读取检查范围与现场资料') }}<span class="thinking-dots">…</span></p><p v-else-if="run?.status==='failed'"><AlertTriangle :size="16" />{{ t('本次分析未完成，可保留资料后重试。') }}</p><p v-else>{{ t('提交检查任务后，在这里查看分析结果。') }}</p></div>
    <footer v-if="text || completedTools.length"><div class="analysis-tools"><span v-for="tool in completedTools" :key="tool"><CheckCircle2 :size="12" />{{ toolLabel(tool) }}</span></div><span v-if="text" class="output-origin">{{ model }} · {{ outputStatus==='generating' ? t('生成中，待校核') : t('已校核') }}</span></footer>
  </section>
</template>
<style scoped>
.ai-analysis{margin:20px 0 22px;border-color:#d3e1f4;overflow:hidden}.ai-analysis header{display:flex;align-items:center;gap:12px;padding:21px 24px;border-bottom:1px solid #e7edf6;background:linear-gradient(110deg,#f4f8ff,#fff)}.ai-symbol{color:var(--blue);display:grid;place-items:center}.ai-analysis h2{font-size:21px}.analysis-status{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--muted);margin-left:auto}.analysis-status.live{color:var(--blue)}.ai-output{padding:22px 26px;font-size:15px;line-height:2;white-space:pre-wrap;min-height:110px}.ai-output p{margin:0}.ai-output.empty{color:var(--muted)}.ai-output.empty p{display:flex;align-items:center;gap:8px}.stream-cursor{display:inline-block;width:2px;height:17px;vertical-align:middle;background:var(--blue);margin-left:4px;animation:blink 1s steps(2) infinite}.ai-analysis footer{padding:13px 24px;background:#fbfcfe;border-top:1px solid var(--line);display:flex;align-items:center;gap:12px;flex-wrap:wrap}.analysis-tools{display:flex;gap:13px;flex-wrap:wrap}.analysis-tools span{display:flex;align-items:center;gap:5px;font-size:11px;color:#52738f}.output-origin{font-size:11px;color:var(--muted);margin-left:auto}.thinking-dots{animation:blink 1.3s infinite}@keyframes blink{50%{opacity:0}}@media(max-width:700px){.ai-analysis header{padding:18px;flex-wrap:wrap}.ai-analysis h2{font-size:20px}.ai-output{padding:18px;font-size:14px}.analysis-status{font-size:11px}.ai-analysis footer{padding:12px 18px}}
</style>
