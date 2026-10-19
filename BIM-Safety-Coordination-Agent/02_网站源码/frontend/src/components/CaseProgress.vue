<script setup lang="ts">
import { computed } from 'vue'
import { Check, ChevronRight } from 'lucide-vue-next'
const props = withDefaults(defineProps<{ status?: string; interactive?: boolean; noRectification?: boolean }>(), { status: 'draft', interactive: false, noRectification: false })
const emit = defineEmits<{ select: [tab: string] }>()
const steps = [
  { name: '发起任务', tab: 'overview' },
  { name: 'AI 分析', tab: 'overview' },
  { name: '审核措施', tab: 'review' },
  { name: '隐患整改', tab: 'verify' },
  { name: '复核关闭', tab: 'verify' },
]
const current = computed(() => ({ draft: 0, analyzing: 1, needs_evidence: 1, pending_review: 2, rejected: 2, approved: 3, rectifying: 3, pending_verification: 4, closed: 4, reopened: 1 }[props.status] ?? 0))
</script>
<template>
  <div class="case-progress card" aria-label="安全检查业务流程">
    <button v-for="(step, index) in steps" :key="step.name" :class="{ current: index === current, done: (index < current || status === 'closed') && !(noRectification && (index===3)), skipped: noRectification && (index===3) }" :disabled="!interactive || index > current" :aria-current="index === current ? 'step' : undefined" @click="emit('select', step.tab)">
      <span class="phase-number"><template v-if="noRectification && (index===3)">—</template><Check v-else-if="index < current || status === 'closed'" :size="14" /><template v-else>{{ index + 1 }}</template></span>
      <span class="phase-text"><strong>{{ step.name }}</strong></span><ChevronRight v-if="index < 4" :size="14" class="phase-arrow" />
    </button>
  </div>
</template>
<style scoped>
.case-progress{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));padding:17px 18px;margin-bottom:22px;gap:8px;box-shadow:none}.case-progress button{display:flex;align-items:center;gap:9px;min-width:0;border:0;background:none;color:var(--dim);padding:4px 0;text-align:left;font:inherit}.case-progress button:disabled{cursor:default}.phase-number{display:grid;place-items:center;width:29px;height:29px;flex-shrink:0;border-radius:50%;border:1px solid var(--line);font-size:12px;font-weight:700;background:var(--panel-2)}.phase-text strong,.phase-text small{display:block;white-space:nowrap}.phase-text strong{font-size:14px;font-weight:650}.phase-text small{font-size:10px;margin-top:4px;color:var(--dim)}.phase-arrow{margin-left:auto;flex-shrink:0;color:#b7c4d4}.current .phase-number{background:var(--blue);color:white;border-color:var(--blue);box-shadow:0 3px 9px #2563eb26}.current .phase-text strong{color:var(--blue)}.done .phase-number{background:#e9f7f0;border-color:#b8dfce;color:var(--green)}.done .phase-text strong{color:var(--text-soft)}
@media(max-width:1250px){.phase-text small{display:none}.phase-arrow{display:none}.case-progress{padding:15px 12px;gap:6px}.phase-text strong{font-size:14px}}
@media(max-width:760px){.case-progress{grid-template-columns:repeat(3,minmax(0,1fr));gap:15px 8px}.phase-text strong{font-size:14px}}
</style>
