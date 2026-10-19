<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, Box, CheckCircle2, ClipboardCheck, FileCheck2, Play, Plus, ShieldCheck } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import StatusBadge from '../components/StatusBadge.vue'
import { refreshSummary, store } from '../store'
import { api } from '../api'
import type { CaseRecord } from '../types'
import { formatDateTime } from '../utils'
import { t } from '../i18n'
const router = useRouter()
const caseRows = ref<CaseRecord[] | null>(null)
const cases = computed(() => (caseRows.value || store.summary?.recent_cases || []).filter(item => !item.title.startsWith('验收 '))
  .slice().sort((a,b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)))
const activeCase = computed(() => cases.value.find(item => !['closed','rejected'].includes(item.status)))
const counts = computed(() => store.summary?.status_counts || {})
const metrics = computed(() => [
  { labelKey: 'dashboard.metric.pendingReview', count: counts.value.pending_review || 0, status: 'pending_review', icon: ClipboardCheck, tone: 'violet' },
  { labelKey: 'dashboard.metric.pendingImplementation', count: counts.value.approved || 0, status: 'approved', icon: ShieldCheck, tone: 'blue' },
  { labelKey: 'dashboard.metric.pendingVerification', count: counts.value.pending_verification || 0, status: 'pending_verification', icon: FileCheck2, tone: 'amber' },
  { labelKey: 'dashboard.metric.closed', count: counts.value.closed || 0, status: 'closed', icon: CheckCircle2, tone: 'green' },
])
const actionLabel = (status: string) => {
  const key = `dashboard.action.${status}`
  const text = t(key)
  return text === key ? t('dashboard.action.default') : text
}
onMounted(async () => {
  await Promise.allSettled([refreshSummary(), api.get<{rows:CaseRecord[]}>('/cases').then(result => { caseRows.value = result.rows })])
})
</script>

<template>
  <div class="page business-dashboard">
    <header class="page-head"><h1>{{ t('route.dashboard') }}</h1><div class="head-actions"><router-link v-if="activeCase" class="btn" :to="`/cases/${activeCase.case_id}`"><Play :size="17" /> {{ t('dashboard.continueInspection') }}</router-link><router-link class="btn btn-primary" to="/inspection"><Plus :size="18" /> {{ t('nav.inspection') }}</router-link></div></header>

    <div class="business-metrics"><router-link v-for="item in metrics" :key="item.status" :to="`/cases?status=${item.status}`" class="card business-metric"><div class="metric-top"><span>{{ t(item.labelKey) }}</span><span class="metric-symbol" :class="`tone-${item.tone}`"><component :is="item.icon" :size="19" /></span></div><strong>{{ item.count }}<small>{{ t('dashboard.unit') }}</small></strong><ArrowRight :size="17" class="metric-arrow" /></router-link></div>

    <div class="home-lower">
      <section class="card recent-work"><div class="section-heading"><h2>{{ t('dashboard.recent') }}</h2><router-link to="/cases">{{ t('dashboard.allRecords') }} <ArrowRight :size="15" /></router-link></div><div v-if="cases.length" class="work-list"><button v-for="item in cases.slice(0,7)" :key="item.case_id" class="work-row" @click="router.push(`/cases/${item.case_id}`)"><span class="work-icon"><ShieldCheck :size="20" /></span><span class="work-title"><strong>{{ item.title }}</strong><small>{{ formatDateTime(item.updated_at) }}</small></span><StatusBadge :status="item.status" /><span class="work-action">{{ actionLabel(item.status) }} <ArrowRight :size="16" /></span></button></div><div v-else class="first-check"><ClipboardCheck :size="30" /><h3>{{ t('dashboard.empty') }}</h3></div></section>
      <aside class="card quick-actions"><h2>{{ t('dashboard.workspace') }}</h2><router-link to="/"><Box :size="21" /><span>{{ t('dashboard.bimModel') }}</span><ArrowRight :size="17" /></router-link><router-link to="/evidence"><FileCheck2 :size="21" /><span>{{ t('nav.evidence') }}</span><ArrowRight :size="17" /></router-link><router-link to="/knowledge"><ClipboardCheck :size="21" /><span>{{ t('nav.knowledge') }}</span><ArrowRight :size="17" /></router-link></aside>
    </div>
  </div>
</template>

<style scoped>
.business-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:20px}.business-metric{position:relative;padding:24px;color:var(--text);transition:border-color .15s}.business-metric:hover{border-color:#99b9e8;color:var(--text)}.metric-top{display:flex;justify-content:space-between;align-items:center;color:var(--text-soft);font-size:15px}.metric-symbol{display:grid;place-items:center;width:36px;height:36px;border-radius:10px}.business-metric>strong{display:block;font-size:38px;font-weight:650;margin-top:14px}.business-metric>strong small{font-size:14px;color:var(--muted);font-weight:400;margin-left:10px}.metric-arrow{position:absolute;right:24px;bottom:29px;color:var(--dim)}.home-lower{display:grid;grid-template-columns:minmax(0,2.7fr) minmax(230px,1fr);gap:22px;margin-top:26px;align-items:start}.recent-work,.quick-actions{padding:26px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:20px}.section-heading>a{display:flex;align-items:center;gap:6px;font-size:14px}.work-row{display:flex;align-items:center;gap:14px;width:100%;text-align:left;padding:22px 0;border:0;border-top:1px solid var(--line);background:none;color:var(--text)}.work-icon{display:grid;place-items:center;flex-shrink:0;width:42px;height:42px;border-radius:12px;background:var(--panel-2);color:#587d9f}.work-title{flex:1;min-width:0}.work-title strong{display:block;font-size:15px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.work-title small{display:block;font-size:12px;color:var(--dim);margin-top:7px}.work-action{display:flex;align-items:center;gap:6px;font-size:14px;color:var(--blue);white-space:nowrap}.work-row:hover .work-title strong{color:var(--blue)}.quick-actions h2{margin-bottom:22px}.quick-actions>a{display:flex;align-items:center;gap:12px;border-top:1px solid var(--line);padding:22px 0;color:var(--text-soft);font-size:15px}.quick-actions>a>span{flex:1}.quick-actions>a:hover{color:var(--blue)}.first-check{text-align:center;padding:45px;color:var(--muted)}.first-check h3{margin-top:16px}@media(max-width:1150px){.business-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.home-lower{grid-template-columns:1fr}.quick-actions{display:none}}@media(max-width:600px){.business-metrics{gap:12px}.business-metric{padding:18px}.metric-top{font-size:14px}.business-metric>strong{font-size:32px}.recent-work{padding:18px}.work-action,.work-icon{display:none}.work-row{gap:10px}.metric-arrow{right:18px;bottom:24px}}
</style>
