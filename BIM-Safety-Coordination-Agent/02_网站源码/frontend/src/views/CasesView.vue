<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowRight, CalendarClock, ClipboardList, Loader2, Plus, RefreshCw, Search } from 'lucide-vue-next'
import StatusBadge from '../components/StatusBadge.vue'
import { api } from '../api'
import { errorMessage, toast } from '../store'
import { formatDateTime, statusLabel } from '../utils'
import type { CaseRecord } from '../types'
import { t } from '../i18n'
const route = useRoute()
const cases = ref<CaseRecord[]>([])
const loading = ref(true)
const statusFilter = ref('')
const search = ref('')
const statusChoices = ['', 'pending_review', 'approved', 'rectifying', 'pending_verification', 'closed', 'needs_evidence', 'reopened', 'rejected', 'draft', 'analyzing']
const businessCases = computed(() => cases.value.filter(item => !item.title.startsWith('验收 ')))
const counts = computed(() => {
  const result: Record<string,number> = {}
  for (const item of businessCases.value) result[item.status] = (result[item.status] || 0) + 1
  return result
})
const filtered = computed(() => businessCases.value.filter(item => (!statusFilter.value || item.status === statusFilter.value) &&
  (!search.value.trim() || (item.title + item.case_id + item.evidence_ids.join(' ')).toLowerCase().includes(search.value.trim().toLowerCase()))))
const action = (status:string) => {
  const key = `cases.action.${status}`
  const text = t(key)
  return text === key ? t('cases.action.default') : text
}
watch(() => route.query.status, value => { statusFilter.value = typeof value === 'string' ? value : '' }, {immediate:true})
async function load() {
  loading.value = true
  try { cases.value = (await api.get<{rows:CaseRecord[]}>('/cases')).rows }
  catch (cause) { toast(errorMessage(cause),'error') }
  finally { loading.value = false }
}
onMounted(load)
</script>
<template>
  <div class="page cases-page">
    <header class="page-head"><div><h1>{{ t('route.cases') }}</h1></div><div class="head-actions"><button class="btn" @click="load"><RefreshCw :size="14" /> {{ t('common.refresh') }}</button><router-link to="/inspection" class="btn btn-primary"><Plus :size="16" /> {{ t('nav.inspection') }}</router-link></div></header>
    <div class="case-summary card"><div><strong>{{ businessCases.length }}</strong><span>{{ t('cases.all') }}</span></div><div><strong>{{ counts.pending_review || 0 }}</strong><span>{{ t('dashboard.metric.pendingReview') }}</span></div><div><strong>{{ (counts.approved || 0) + (counts.rectifying || 0) }}</strong><span>{{ t('cases.inProgress') }}</span></div><div><strong>{{ counts.pending_verification || 0 }}</strong><span>{{ t('dashboard.metric.pendingVerification') }}</span></div><div><strong>{{ counts.closed || 0 }}</strong><span>{{ t('cases.closedLoop') }}</span></div></div>
    <div class="record-toolbar"><div class="status-filters"><button v-for="status in ['', 'pending_review','approved','rectifying','pending_verification','closed']" :key="status" :class="{active:statusFilter === status}" @click="statusFilter = status">{{ status ? statusLabel(status) : t('cases.all') }}<span v-if="status && counts[status]">{{ counts[status] }}</span></button><select v-model="statusFilter" class="select extra-filter" :aria-label="t('cases.otherStatus')"><option value="">{{ t('cases.otherStatus') }}</option><option v-for="status in statusChoices.filter(s => s && !['pending_review','approved','rectifying','pending_verification','closed'].includes(s))" :key="status" :value="status">{{ statusLabel(status) }}</option><option v-if="['pending_review','approved','rectifying','pending_verification','closed'].includes(statusFilter)" :value="statusFilter">{{ statusLabel(statusFilter) }}</option></select></div><div class="record-search"><Search :size="15" /><input v-model="search" :placeholder="t('cases.searchPlaceholder')" :aria-label="t('cases.searchAria')" /></div></div>
    <div v-if="loading" class="card records-loading"><Loader2 :size="20" class="spin" /> {{ t('cases.loading') }}</div>
    <div v-else-if="filtered.length" class="case-grid"><router-link v-for="item in filtered" :key="item.case_id" :to="`/cases/${item.case_id}`" class="case-card card"><div class="case-top"><span class="record-icon"><ClipboardList :size="20" /></span><StatusBadge :status="item.status" dot /></div><h2>{{ item.title }}</h2><div class="record-meta"><span><CalendarClock :size="13" /> {{ formatDateTime(item.as_of) }}</span><span>{{ t('cases.storeyEdge') }}</span></div><p class="record-result" :class="{'is-closed':item.status === 'closed'}">{{ item.status === 'closed' ? t('cases.closedSummary') : item.findings[0]?.hazard || t('cases.pendingSummary') }}</p><div class="record-foot"><span>{{ t('cases.evidenceCount', { count: item.evidence_ids.length }) }} · {{ formatDateTime(item.updated_at) }}</span><strong>{{ action(item.status) }} <ArrowRight :size="14" /></strong></div></router-link></div>
    <section v-else class="card records-empty"><ClipboardList :size="33" /><h2>{{ t('cases.emptyTitle') }}</h2><p>{{ t('cases.emptyHint') }}</p><router-link to="/inspection" class="btn btn-primary"><Plus :size="15" /> {{ t('nav.inspection') }}</router-link></section>
  </div>
</template>
<style scoped>
.case-summary{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));padding:22px 0;margin-bottom:24px;box-shadow:none}.case-summary>div{padding:0 24px;border-right:1px solid var(--line)}.case-summary>div:last-child{border:0}.case-summary strong,.case-summary span{display:block}.case-summary strong{font-size:27px;font-weight:750;color:#1e4165}.case-summary span{font-size:11px;color:var(--muted);margin-top:7px}.record-toolbar{display:flex;justify-content:space-between;align-items:center;gap:15px;flex-wrap:wrap;margin-bottom:20px}.status-filters{display:flex;align-items:center;flex-wrap:wrap;gap:6px}.status-filters>button{padding:9px 11px;border:1px solid transparent;border-radius:8px;background:none;color:var(--muted);font-size:12px;display:flex;gap:7px;align-items:center}.status-filters>button.active{background:white;border-color:#d2dff0;color:var(--blue);box-shadow:0 2px 5px #17385a05;font-weight:650}.status-filters>button>span{font-size:10px;opacity:.75}.extra-filter{width:112px;font-size:11px;height:33px;background-color:transparent}.record-search{display:flex;gap:9px;align-items:center;border:1px solid var(--line);background:white;padding:9px 12px;border-radius:9px;color:var(--dim)}.record-search input{border:0;outline:0;width:170px;background:none;font-size:12px;color:var(--text)}.case-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:19px}.case-card{display:block;padding:23px 24px;color:var(--text);transition:border-color .15s,transform .15s}.case-card:hover{color:var(--text);border-color:#8bb4ea;transform:translateY(-2px)}.case-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:17px}.record-icon{width:39px;height:39px;border-radius:12px;background:#ecf2fa;color:#507ba5;display:grid;place-items:center}.case-card h2{font-size:17px;font-weight:700;line-height:1.5;margin-bottom:12px}.record-meta{display:flex;gap:14px;align-items:center;color:var(--muted);font-size:11px}.record-meta>span{display:flex;align-items:center;gap:5px}.record-result{margin-top:19px;background:#f8fafc;border-left:2px solid #d4a554;padding:11px 13px;border-radius:0 8px 8px 0;font-size:12px;line-height:1.7;color:var(--text-soft)}.record-result.is-closed{border-color:#71b999;background:#f3faf6}.record-foot{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-top:21px;padding-top:15px;border-top:1px solid var(--line)}.record-foot>span{font-size:10px;color:var(--dim)}.record-foot strong{display:flex;align-items:center;gap:7px;font-size:12px;color:var(--blue);white-space:nowrap}.records-loading,.records-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:60px 20px;gap:14px;color:var(--muted)}.records-empty h2{font-size:18px;color:var(--text)}.records-empty p{font-size:13px;margin-bottom:8px}
@media(max-width:1050px){.case-grid{grid-template-columns:1fr}.record-toolbar{align-items:flex-start}.case-summary>div{padding:0 17px}}
@media(max-width:600px){.case-summary{grid-template-columns:repeat(3,minmax(0,1fr));gap:20px 0}.case-summary>div:nth-child(3){border:0}.case-summary strong{font-size:24px}.case-card{padding:20px}.record-foot{flex-wrap:wrap}.record-search{width:100%}.record-search input{width:100%}}
</style>
