<script setup lang="ts">
import type { ModelCall } from '../types'
import { t } from '../i18n'
defineProps<{calls:ModelCall[]}>()
function purposeLabel(value:string):string{
  const key=`model.purpose.${value}`
  const text=t(key)
  return text===key ? value : text
}
</script>
<template><section v-if="calls.length" class="model-calls card"><h3>{{ t('model.title') }}</h3><article v-for="call in calls.slice(0,8)" :key="call.id"><div><strong>{{ purposeLabel(call.purpose) }}</strong><span :class="call.status==='succeeded' ? 'success' : 'failed'">{{ call.status==='succeeded' ? t('model.returned') : t('model.failed') }}</span></div><p>{{ call.model }}</p><small>{{ (call.elapsed_ms/1000).toFixed(1) }} s · {{ call.usage.total_tokens ?? '—' }} tokens<span v-if="call.error"> · {{ call.error }}</span></small></article></section></template>
<style scoped>.model-calls{padding:18px}.model-calls h3{font-size:14px;margin-bottom:12px}.model-calls article{padding:11px 0;border-top:1px solid var(--line)}.model-calls article>div{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px}.model-calls article>div>span{font-size:11px}.model-calls p{font-size:12px;margin:5px 0;overflow-wrap:anywhere;color:var(--text-soft)}.model-calls small{font-size:11px;color:var(--muted)}.success{color:var(--green)}.failed{color:var(--red)}</style>
