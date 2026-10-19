<script setup lang="ts">
import type { ModelCall } from '../types'
defineProps<{calls:ModelCall[]}>()
const purpose:Record<string,string>={task_plan:'任务规划',risk_summary:'安全状态综合',control_draft:'控制措施组织',image_observation:'现场图像观察',text_observation:'现场文本提取'}
</script>
<template><section v-if="calls.length" class="model-calls card"><h3>本次真实模型调用</h3><article v-for="call in calls.slice(0,8)" :key="call.id"><div><strong>{{ purpose[call.purpose] || call.purpose }}</strong><span :class="call.status==='succeeded' ? 'success' : 'failed'">{{ call.status==='succeeded' ? '已返回' : '失败' }}</span></div><p>{{ call.model }}</p><small>{{ (call.elapsed_ms/1000).toFixed(1) }} s · {{ call.usage.total_tokens ?? '—' }} tokens<span v-if="call.error"> · {{ call.error }}</span></small></article></section></template>
<style scoped>.model-calls{padding:18px}.model-calls h3{font-size:14px;margin-bottom:12px}.model-calls article{padding:11px 0;border-top:1px solid var(--line)}.model-calls article>div{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px}.model-calls article>div>span{font-size:11px}.model-calls p{font-size:12px;margin:5px 0;overflow-wrap:anywhere;color:var(--text-soft)}.model-calls small{font-size:11px;color:var(--muted)}.success{color:var(--green)}.failed{color:var(--red)}</style>
