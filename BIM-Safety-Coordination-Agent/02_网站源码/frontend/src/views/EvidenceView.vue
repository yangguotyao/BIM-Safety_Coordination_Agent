<script setup lang="ts">
import { t } from '../i18n'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { AlertTriangle, CalendarClock, Database, Image, Loader2, MapPin, Search } from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import { api } from '../api'
import { errorMessage, toast } from '../store'
import type { Evidence } from '../types'
import { formatDateTime, observationLabel, observationValue } from '../utils'

const router = useRouter()
const rows = ref<Evidence[]>([])
const loading = ref(true)
const stage = ref('')
const search = ref('')

const filtered = computed(() => {
  let items = rows.value
  if (stage.value) items = items.filter((item) => item.stage === stage.value)
  if (search.value.trim()) {
    const q = search.value.trim().toLowerCase()
    items = items.filter(
      (item) =>
        item.evidence_id.toLowerCase().includes(q) ||
        item.label.toLowerCase().includes(q) ||
        item.observation.guardrail_state?.toLowerCase?.().includes(q),
    )
  }
  return items
})
const beforeCount = computed(() => rows.value.filter((item) => item.stage === 'before').length)
const afterCount = computed(() => rows.value.filter((item) => item.stage === 'after').length)

async function load() {
  loading.value = true
  try {
    const response = await api.get<{ rows: Evidence[] }>('/evidence')
    rows.value = response.rows
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

function locate(evidenceId: string) {
  router.push({ path: '/bim', query: { evidence: evidenceId } })
}

onMounted(load)
</script>

<template>
  <div class="page evidence-page">
    <div class="page-head">
      <div>
        
        <h1>{{ t('证据库') }}</h1>
      </div>
      <div class="head-actions">
        <span class="badge tone-teal"><Database :size="12" /> {{ rows.length }} 条证据</span>
        
        <button class="btn btn-sm" @click="load"><Loader2 v-if="loading" :size="13" class="spin" /><Image v-else :size="13" /> {{ t('刷新') }}</button>
      </div>
    </div>

    <div class="evidence-summary card">
      <div class="ev-stat">
        <span class="stat">{{ rows.length }}</span>
        <span class="stat-label">{{ t('全部证据') }}</span>
      </div>
      <div class="ev-stat">
        <span class="stat">{{ beforeCount }}</span>
        <span class="stat-label">{{ t('检查时 before') }}</span>
      </div>
      <div class="ev-stat">
        <span class="stat">{{ afterCount }}</span>
        <span class="stat-label">{{ t('实施后 after') }}</span>
      </div>
      <div class="ev-stat">
        <span class="stat">{{ rows.filter(item=>item.source==='upload').length }}</span>
        <span class="stat-label">{{ t('新上传资料') }}</span>
      </div>
      <div class="ev-stat">
        <span class="stat">{{ rows.filter(item=>item.perception?.model).length }}</span>
        <span class="stat-label">{{ t('已生成视觉候选') }}</span>
      </div>
    </div>

    <div class="evidence-toolbar card">
      <div class="stage-tabs">
        <button :class="{ active: stage === '' }" @click="stage = ''">{{ t('全部') }} <span>{{ rows.length }}</span></button>
        <button :class="{ active: stage === 'before' }" @click="stage = 'before'">{{ t('检查时') }} <span>{{ beforeCount }}</span></button>
        <button :class="{ active: stage === 'after' }" @click="stage = 'after'">{{ t('实施后') }} <span>{{ afterCount }}</span></button>
      </div>
      <div class="search-box">
        <Search :size="14" class="dim" />
        <input v-model="search" class="input" :placeholder="t('搜索证据 ID / 标签 / 防护状态')" />
      </div>
    </div>

    <div v-if="loading" class="loading-state card"><Loader2 :size="18" class="spin" /> {{ t('读取证据库…') }}</div>

    <div v-else-if="filtered.length" class="evidence-gallery">
      <article v-for="item in filtered" :key="item.evidence_id" class="evidence-card card">
        <div class="evidence-image" @click="locate(item.evidence_id)">
          <img v-if="!item.file_path?.toLowerCase().endsWith('.pdf')" :src="item.image_url" :alt="item.label" loading="lazy" />
          <span v-else>{{ t('PDF 证据') }}</span>
          <span class="badge" :class="item.stage === 'after' ? 'tone-teal' : 'tone-cyan'" style="position: absolute; right: 8px; top: 8px">
            {{ item.stage === 'after' ? 'after' : 'before' }}
          </span>
        </div>
        <div class="evidence-body">
          <div class="demo-flag"><span class="badge tone-amber">{{ item.source==='upload' ? item.perception?.confirmed ? t('人工确认观察') : t('上传资料 · 待核对') : t('演示示意图 · 非现场照片') }}</span></div>
          <div class="evidence-head">
            <div>
              <div class="mono evidence-id">{{ item.evidence_id }}</div>
              <h3>{{ item.label }}</h3>
            </div>
            <button class="btn btn-icon btn-sm" :title="t('在 BIM 中定位')" @click="locate(item.evidence_id)"><MapPin :size="14" /></button>
          </div>
          <div class="evidence-time"><CalendarClock :size="11" /> {{ formatDateTime(item.captured_at) }}</div>
          <div class="observation-grid">
            <div v-for="key in ['guardrail_state', 'guardrail_height_m', 'worker_present', 'drop_height_m', 'boundary_is_exposed', 'guardrail_fixed']" :key="key" class="obs">
              <span class="k">{{ observationLabel(key) }}</span>
              <span class="v mono" :class="{ unknown: item.observation[key] === null || item.observation[key] === 'unknown' }">{{ observationValue(item.observation[key]) }}</span>
            </div>
          </div>
          <div class="evidence-foot">
            <span class="tiny dim">{{ item.provenance }}</span>
            <span class="mono tiny dim">{{ item.bim_guids?.[0]?.slice(0, 10) }}…</span>
          </div>
        </div>
      </article>
    </div>

    <div v-else class="card">
      <EmptyState :title="t('没有匹配证据')" detail="清空搜索或切换阶段筛选。" />
    </div>

    <div class="notice warn" style="margin-top: 16px">
      <AlertTriangle :size="13" />
      <span>
        这些图只用于验证“BIM 构件 → 证据 → Finding → 人工审核 → 复核”的软件流程。
        图中模拟观察不代表 S1 现场实况，也不能作为事故或合规结论。
      </span>
    </div>
  </div>
</template>

<style scoped>
.evidence-page {
  max-width: 1680px;
}
.evidence-summary {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr)) 1.5fr;
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 14px;
}
.ev-stat {
  background: var(--panel-2);
  padding: 12px 15px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.ev-stat .stat {
  font-size: 20px;
}
.ev-stat.wide {
  flex-direction: row;
  align-items: center;
  gap: 9px;
  color: var(--cyan);
}
.evidence-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 13px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.stage-tabs {
  display: flex;
  gap: 3px;
}
.stage-tabs button {
  border: 1px solid transparent;
  background: transparent;
  color: var(--dim);
  font-size: 11px;
  padding: 6px 10px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.stage-tabs button span {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  background: rgba(148, 163, 184, 0.08);
  border-radius: 4px;
  padding: 0 4px;
}
.stage-tabs button.active {
  color: var(--teal);
  background: rgba(45, 212, 191, 0.08);
  border-color: rgba(45, 212, 191, 0.2);
}
.search-box {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0 9px;
  background: var(--panel-2);
  min-width: 280px;
}
.search-box .input {
  border: none;
  background: transparent;
  height: 32px;
  padding: 0;
  font-size: 11.5px;
}
.search-box .input:focus {
  box-shadow: none;
}
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 50px;
  color: var(--muted);
}
.evidence-gallery {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.evidence-card {
  overflow: hidden;
  transition: 160ms ease;
}
.evidence-card:hover {
  transform: translateY(-2px);
  border-color: rgba(45, 212, 191, 0.25);
}
.evidence-image {
  position: relative;
  cursor: pointer;
  overflow: hidden;
  background: #eef2f7;
}
.evidence-image img {
  width: 100%;
  aspect-ratio: 3 / 2;
  object-fit: cover;
  display: block;
  transition: 250ms ease;
}
.evidence-card:hover .evidence-image img {
  transform: scale(1.015);
}
.demo-flag {
  margin-bottom: 7px;
}
.demo-flag .badge {
  font-size: 11px;
}
.evidence-body {
  padding: 12px 13px 11px;
}
.evidence-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.evidence-id {
  font-size: 11px;
  color: var(--teal);
  letter-spacing: 0.05em;
}
.evidence-head h3 {
  margin-top: 4px;
  font-size: 13px;
}
.evidence-time {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--dim);
}
.observation-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 7px;
  overflow: hidden;
  margin-top: 10px;
}
.obs {
  background: var(--panel-2);
  padding: 6px 7px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.obs .k {
  font-size: 11px;
  color: var(--dim);
}
.obs .v {
  font-size: 11px;
  color: var(--text-soft);
}
.obs .v.unknown {
  color: var(--amber);
}
.evidence-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 9px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}
.evidence-foot .tiny {
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 1280px) {
  .evidence-gallery {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .evidence-summary {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .evidence-gallery,
  .evidence-summary {
    grid-template-columns: 1fr;
  }
}
</style>
