<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Loader2, Sparkles } from 'lucide-vue-next'
import { api } from '../api'
import { actorId, errorMessage, toast } from '../store'
import type { CaseRecord } from '../types'

const props = defineProps<{ caseData: CaseRecord }>()
const emit = defineEmits<{ updated: [] }>()
const request = ref('')
const submitting = ref(false)
const messages = ref<{ role: string; content: string }[]>([])
const canAsk = computed(() => ['draft', 'needs_evidence', 'pending_review', 'rejected', 'reopened'].includes(props.caseData.status))
const labels: Record<string, string> = {
  all: '临边综合检查', guardrail_height: '栏杆高度', guardrail_integrity: '固定与连续性', worker_exposure: '人员暴露与距离',
  bim_query: '构件查询', schedule_query: '计划匹配', evidence_check: '证据校核', spatial_check: '空间距离', rule_retrieval: '规范检索', risk_assessment: '风险判断',
}
const nextAction = computed(() => ({
  draft: '提交检查任务，开始分析', analyzing: '正在执行工具，等待结果', needs_evidence: '查看缺失项，补充证据或澄清任务',
  pending_review: '审核候选措施，批准、修改或拒绝', approved: '记录责任人与实施时刻', rectifying: '追加实施后的复核证据',
  pending_verification: '选择实施后证据，由复核人确认', closed: '闭环完成，可导出或记录条件变化',
  rejected: '根据拒绝意见调整任务后重新分析', reopened: '查看重开原因，补证并重新分析',
}[props.caseData.status]))
watch(() => [props.caseData.case_id, props.caseData.version], async () => {
  try {
    const result = await api.get<{ rows: typeof messages.value }>(`/cases/${props.caseData.case_id}/messages?actor_id=${encodeURIComponent(actorId)}`)
    messages.value = result.rows
  } catch { messages.value = [] }
}, { immediate: true })

async function ask() {
  if (!request.value.trim() || submitting.value || !canAsk.value) return
  submitting.value = true
  try {
    await api.post(`/cases/${props.caseData.case_id}/ask`, {
      message: request.value.trim(), actor_id: actorId, expected_case_version: props.caseData.version,
    })
    request.value = ''
    toast('任务已提交，正在按本次检查重点执行。', 'success')
    emit('updated')
  } catch (error) { toast(errorMessage(error), 'error') }
  finally { submitting.value = false }
}
</script>

<template>
  <section class="card task-workspace">
    <div class="task-top">
      <div><div class="eyebrow">SAFETY COORDINATOR</div><h2><Sparkles :size="18" /> 检查任务与决策</h2></div>
      <span class="badge tone-teal">{{ caseData.task_spec?.mode === 'live_model' ? '模型规划 + 工具校核' : '规则演示模式' }}</span>
    </div>
    <div class="next-action"><ArrowRight :size="16" /><strong>下一步</strong><span>{{ nextAction }}</span></div>
    <div v-if="caseData.request_text" class="current-request">{{ caseData.request_text }}</div>
    <form v-if="canAsk" class="task-form" @submit.prevent="ask">
      <label :for="`task-${caseData.case_id}`">{{ caseData.task_spec ? '继续本 Case 的检查' : '描述本次检查任务' }}</label>
      <textarea :id="`task-${caseData.case_id}`" v-model="request" class="textarea" maxlength="1500" placeholder="例如：只检查同一区域栏杆高度；或继续刚才的检查" required />
      <div class="task-bottom">
        <div class="suggestions"><button v-for="text in ['全面检查L05临边风险', '只检查栏杆高度', '检查防护固定与连续性']" :key="text" type="button" @click="request = text">{{ text }}</button></div>
        <button class="btn btn-primary" :disabled="submitting || !request.trim()"><Loader2 v-if="submitting" :size="14" class="spin" /><Sparkles v-else :size="14" /> 提交任务</button>
      </div>
      <p class="task-hint">待审核时提交新任务会生成新分析，需重新人工审核。范围固定为当前 Case 的区域、模型版本和时刻。</p>
    </form>
    <div v-if="caseData.task_spec" class="plan-grid">
      <div><h3>本次检查重点</h3><div class="chips"><span v-for="focus in caseData.task_spec.focus" :key="focus" class="badge tone-cyan">{{ labels[focus] || focus }}</span></div><p v-if="caseData.task_spec.context_inherited" class="task-hint">已使用本 Case 的近期上下文</p><p v-if="caseData.task_spec.needs_clarification" class="clarification">{{ caseData.task_spec.clarification }}</p></div>
      <div><h3>已选择的工具</h3><div class="chips"><span v-for="tool in caseData.task_spec.selected_tools" :key="tool" class="badge tone-slate">{{ labels[tool] || tool }}</span></div><p class="task-hint">{{ caseData.task_spec.needs_clarification ? '范围待澄清，尚未执行检查工具。' : '具体调用结果见 Agent 实际记录。' }}</p></div>
    </div>
    <details v-if="caseData.safety_state" class="task-details"><summary>检查上下文 · 模型、活动与观察</summary><p>{{ caseData.model_id }} @ {{ caseData.model_version }} · {{ caseData.zone_id }} · {{ caseData.as_of }}</p><p>构件：{{ caseData.bim_guids.join('、') }}</p><p>活动：{{ caseData.safety_state.activity || '待补充' }} · 证据：{{ caseData.safety_state.evidence_ids?.join('、') || '待补充' }}</p><p v-if="caseData.safety_state.missing_fields?.length" class="clarification">缺失字段：{{ caseData.safety_state.missing_fields.join('、') }}</p><p>规范查询：{{ caseData.task_spec?.retrieval_query }}</p><pre>{{ JSON.stringify(caseData.safety_state.observations, null, 2) }}</pre></details>
    <details v-if="messages.length" class="task-details"><summary>本会话的 Case 记忆 · {{ messages.length }} 条</summary><div v-for="(message, index) in messages" :key="index" class="message" :class="message.role"><strong>{{ message.role === 'user' ? '检查人' : 'Coordinator' }}</strong><span>{{ message.content }}</span></div><p class="task-hint">最近消息按 Case 与本浏览器会话保存；每次最多选取 6 条、正文最多 6,000 字节进入规划上下文。</p></details>
    <details v-if="caseData.decision_package" class="task-details"><summary>决策包 · 证据、依据、责任与假设</summary><div class="decision-grid-simple"><div><h3>证据引用</h3><p>{{ caseData.decision_package.evidence.join('、') || '待补充' }}</p><h3>责任分配候选</h3><p>{{ caseData.decision_package.owners.join('、') || '本次无整改措施' }}</p></div><div><h3>检索依据</h3><p v-for="rule in caseData.decision_package.governing_rules" :key="rule.rule_id">{{ rule.standard }} · {{ rule.clause }}<span class="task-hint"> · PDF 第 {{ rule.pdf_page }} 页</span></p></div></div><h3>适用边界与假设</h3><ul><li v-for="assumption in caseData.decision_package.assumptions" :key="assumption">{{ assumption }}</li></ul><p class="task-hint">{{ caseData.decision_package.scope }}。此处保留分析时的候选决策，当前批准内容见审核记录。</p></details>
  </section>
</template>

<style scoped>
.task-workspace { padding: 20px; border: 0; background: var(--panel); box-shadow: none; }
.task-top,.task-bottom { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
h2 { display: flex; align-items: center; gap: 9px; font-size: 19px; margin: 4px 0 15px; }
h3 { font-size: 13px; color: var(--text-soft); margin: 0 0 9px; }
.next-action { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 15px; background: rgba(45,212,191,.08); border-radius: 9px; font-size: 14px; }
.next-action strong { color: var(--teal); }.current-request { font-size: 15px; padding-top: 18px; white-space: pre-wrap; overflow-wrap: anywhere; }
.task-form { margin-top: 18px; }.task-form label { display: block; font-size: 13px; margin-bottom: 8px; color: var(--text-soft); }.task-form textarea { min-height: 76px; font-size: 14px; }.task-bottom { margin-top: 10px; }
.suggestions,.chips { display: flex; gap: 7px; flex-wrap: wrap; }.suggestions button { color: var(--text-soft); background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: 6px; padding: 6px 9px; cursor: pointer; font-size: 12px; }.suggestions button:hover { border-color: var(--teal); }
.task-hint { font-size: 12px; line-height: 1.65; color: var(--muted); margin: 9px 0 0; }.plan-grid,.decision-grid-simple { display: grid; grid-template-columns: 1fr 1.6fr; gap: 22px; margin-top: 20px; }.chips .badge { font-size: 12px; }.clarification { color: var(--amber); font-size: 14px; }
.task-details { margin-top: 17px; padding-top: 15px; border-top: 1px solid var(--line); font-size: 13px; }.task-details summary { cursor: pointer; color: var(--text-soft); }.task-details p { overflow-wrap: anywhere; }.task-details li { margin-bottom: 6px; color: var(--text-soft); }.message { display: grid; grid-template-columns: 90px 1fr; gap: 10px; margin-top: 12px; padding: 10px; background: var(--panel); border-radius: 8px; }.message strong { color: var(--teal); }.message span { white-space: pre-wrap; overflow-wrap: anywhere; }
@media(max-width:800px) { .task-workspace { padding: 16px; }.plan-grid,.decision-grid-simple { grid-template-columns: 1fr; }.message { grid-template-columns: 1fr; } }
</style>
