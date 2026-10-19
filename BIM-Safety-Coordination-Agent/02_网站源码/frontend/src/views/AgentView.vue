<script setup lang="ts">
import { t } from '../i18n'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleDashed,
  Clock,
  Cpu,
  GitBranch,
  Layers,
  Loader2,
  RefreshCw,
  ShieldCheck,
  Terminal,
  XCircle,
} from 'lucide-vue-next'
import FlowDiagram from '../components/FlowDiagram.vue'
import EmptyState from '../components/EmptyState.vue'
import ModelCalls from '../components/ModelCalls.vue'
import { api } from '../api'
import { errorMessage, toast } from '../store'
import type { AgentEvent, Run } from '../types'
import { formatDateTime, formatTime, statusLabel } from '../utils'

const route = useRoute()
const router = useRouter()
const architecture = ref<any>(null)
const runs = ref<Run[]>([])
const selected = ref<Run | null>(null)
const loading = ref(true)
const loadingRun = ref(false)
const expanded = ref<Record<number, boolean>>({})
const poll = ref<number | undefined>(undefined)

const selectedCaseId = computed(() => (typeof route.query.case === 'string' ? route.query.case : ''))
const filteredRuns = computed(() =>
  selectedCaseId.value ? runs.value.filter((item) => item.case_id === selectedCaseId.value) : runs.value,
)
const roleTone: Record<string, string> = {
  'Safety Coordinator': 'teal',
  'BIM Tool': 'cyan',
  'Schedule Tool': 'blue',
  Inspection: 'amber',
  Knowledge: 'violet',
  Risk: 'red',
  Intervention: 'violet',
  Verification: 'green',
}

async function loadRuns() {
  try {
    const response = await api.get<{ rows: Run[] }>('/agent/runs?limit=40')
    runs.value = response.rows
    const wanted = typeof route.query.run === 'string' ? route.query.run : ''
    const target = wanted ? runs.value.find((item) => item.run_id === wanted) : filteredRuns.value[0]
    if (target) await loadRun(target.run_id)
    else selected.value = null
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

async function loadRun(runId: string) {
  loadingRun.value = true
  try {
    const response = await api.get<{ run: Run }>(`/runs/${runId}`)
    selected.value = response.run
    if (response.run.status === 'running' || response.run.status === 'queued') startPoll()
    else stopPoll()
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    loadingRun.value = false
  }
}

function startPoll() {
  if (poll.value) return
  poll.value = window.setInterval(async () => {
    if (!selected.value) return
    try {
      const response = await api.get<{ run: Run }>(`/runs/${selected.value.run_id}`)
      selected.value = response.run
      if (!['running', 'queued'].includes(response.run.status)) stopPoll()
    } catch {
      stopPoll()
    }
  }, 1500)
}

function stopPoll() {
  if (poll.value) {
    window.clearInterval(poll.value)
    poll.value = undefined
  }
}

function chooseRun(run: Run) {
  router.replace({ query: { ...route.query, run: run.run_id } })
  loadRun(run.run_id)
}

function toggle(seq: number) {
  expanded.value[seq] = !expanded.value[seq]
}

function statusIcon(status: string) {
  if (['succeeded','succeeded_after_retry','cached'].includes(status)) return CheckCircle2
  if (status === 'failed') return XCircle
  if (status === 'retrying') return RefreshCw
  return CircleDashed
}

const stats = computed(() => {
  const events = selected.value?.events || []
  return {
    nodes: new Set(events.map((item) => item.node)).size,
    tools: new Set(events.map((item) => item.tool).filter(Boolean)).size,
    failed: events.filter((item) => item.status === 'failed').length,
    retries: events.filter((item) => item.status === 'retrying').length,
  }
})

watch(
  () => route.query.run,
  (id) => {
    if (typeof id === 'string' && id) loadRun(id)
  },
)

onMounted(async () => {
  try {
    architecture.value = await api.get('/agent/architecture')
  } catch {
    architecture.value = null
  }
  await loadRuns()
})
onBeforeUnmount(stopPoll)
</script>

<template>
  <div class="page agent-page">
    <div class="page-head">
      <div>
        
        <h1>{{ t('Agent 工作流') }}</h1>
      </div>
      <div class="head-actions">
        <span class="badge tone-teal"><Cpu :size="12" /> LangGraph</span>
        <span v-if="selected" class="badge tone-slate">{{ selected.mode==='live' ? t('真实模型调用') : t('规则回放') }}</span>
        <button class="btn btn-sm" @click="loadRuns"><RefreshCw :size="13" /> {{ t('刷新') }}</button>
      </div>
    </div>

    <div class="agent-grid">
      <aside class="card run-list">
        <div class="card-head">
          <div class="card-title"><Terminal :size="15" /> {{ t('运行记录') }}</div>
          <span class="badge tone-slate">{{ filteredRuns.length }}</span>
        </div>
        <div class="run-list-body">
          <button
            v-for="run in filteredRuns"
            :key="run.run_id"
            class="run-item"
            :class="{ active: selected?.run_id === run.run_id }"
            @click="chooseRun(run)"
          >
            <div class="run-top">
              <span class="mono tiny">{{ run.run_id.slice(-12) }}</span>
              <span class="badge" :class="run.status === 'failed' ? 'tone-red' : run.status === 'running' ? 'tone-cyan' : 'tone-green'">{{ run.status }}</span>
            </div>
            <div class="run-case mono">{{ run.case_id }}</div>
            <div class="run-time">{{ formatDateTime(run.created_at) }}</div>
          </button>
          <EmptyState v-if="!filteredRuns.length" :title="t('还没有运行')" :detail="t('在案例详情中点击“开始分析”，会产生真实 LangGraph run。')" />
        </div>
      </aside>

      <main class="agent-main">
        <section class="card flow-section">
          <div class="card-head">
            <div class="card-title"><GitBranch :size="15" /> {{ t('职责与工具') }}</div>
            <span class="badge tone-cyan">LLM orchestrates · tools compute</span>
          </div>
          <div class="card-body">
            <FlowDiagram />
            <div class="tool-strip">
              <span class="caption">DETERMINISTIC TOOLS</span>
              <span v-for="tool in ['bim_query', 'spatial_check', 'schedule_query', 'evidence_check', 'rule_retrieval', 'risk_assessment', 'verification_check']" :key="tool" class="mono tool-pill">{{ tool }}</span>
            </div>
          </div>
        </section>

        <section v-if="selected" class="card trace-card">
          <div class="card-head">
            <div class="card-title">
              <Terminal :size="15" /> {{ t('实际执行记录') }}
              <span class="badge" :class="selected.status === 'failed' ? 'tone-red' : selected.status === 'running' ? 'tone-cyan' : 'tone-green'">{{ selected.status }}</span>
            </div>
            <div class="row">
              <span class="mono tiny dim">{{ selected.run_id }}</span>
              <router-link v-if="selected.case_id" class="btn btn-sm" :to="`/cases/${selected.case_id}`">
                {{ t('打开案例') }} <ArrowUpRight :size="12" />
              </router-link>
            </div>
          </div>
          <div class="card-body">
            <div class="run-stats">
              <div><strong>{{ selected.events?.length || 0 }}</strong><span>events</span></div>
              <div><strong>{{ stats.nodes }}</strong><span>nodes</span></div>
              <div><strong>{{ stats.tools }}</strong><span>tools</span></div>
              <div><strong>{{ stats.retries }}</strong><span>retries</span></div>
              <div><strong class="fail">{{ stats.failed }}</strong><span>failed</span></div>
              <div><strong>{{ selected.finished_at ? Math.max(1, Math.round((new Date(selected.finished_at).getTime() - new Date(selected.started_at || selected.created_at).getTime()) / 1000)) + 's' : '—' }}</strong><span>duration</span></div>
            </div>
            <div v-if="selected.error" class="notice danger" style="margin-bottom: 12px">
              <XCircle :size="13" />
              <span>{{ selected.error }}</span>
            </div>

            <ModelCalls :calls="selected.model_calls || []" />
            <div class="trace-list">
              <div v-for="event in selected.events" :key="event.seq" class="trace-row">
                <div class="trace-line">
                  <span class="trace-seq mono">{{ String(event.seq).padStart(2, '0') }}</span>
                  <div class="trace-dot" :class="`tone-${roleTone[event.role] || 'slate'}`">
                    <component :is="statusIcon(event.status)" :size="12" />
                  </div>
                  <div class="trace-content">
                    <div class="trace-top">
                      <strong>{{ event.node }}</strong>
                      <span class="badge" :class="`tone-${roleTone[event.role] || 'slate'}`">{{ event.role }}</span>
                      <span v-if="event.tool" class="mono tool-name">{{ event.tool }}</span>
                      <span class="badge" :class="event.status === 'failed' ? 'tone-red' : event.status === 'retrying' ? 'tone-amber' : 'tone-green'">{{ event.status }}</span>
                      <span class="mono tiny dim" style="margin-left: auto">{{ formatTime(event.at) }}</span>
                    </div>
                    <div v-if="event.input_summary" class="trace-input mono">{{ event.input_summary }}</div>
                    <div v-if="event.rationale" class="trace-rationale">{{ event.rationale }}</div>
                    <div v-if="event.error" class="trace-error">{{ event.error }}</div>
                    <button class="detail-toggle" @click="toggle(event.seq)">
                      <ChevronDown :size="12" :class="{ rotated: expanded[event.seq] }" />
                      {{ expanded[event.seq] ? t('收起') : t('展开') }}{{ t('工具返回') }}
                    </button>
                    <pre v-if="expanded[event.seq]" class="trace-output">{{ JSON.stringify(event.output, null, 2) }}</pre>
                  </div>
                </div>
              </div>
            </div>
            <EmptyState v-if="!selected.events?.length" :title="t('暂无 trace 事件')" :detail="t('运行刚创建时可能还没有节点写入。')" />
          </div>
        </section>

        <section v-else class="card">
          <EmptyState :title="t('选择一个 run')" :detail="t('从左侧选择实际运行，查看节点、工具和返回数据。')" />
        </section>
      </main>
    </div>

    <div v-if="architecture" class="arch-grid">
      <div class="arch-note card">
        <div class="card-body">
          <div class="caption">PRINCIPLE</div>
          <p>{{ architecture.principle }}</p>
        </div>
      </div>
      <div class="arch-note card">
        <div class="card-body">
          <div class="caption">BOUNDARY</div>
          <p>{{ architecture.boundary }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-grid {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}
.run-list {
  position: sticky;
  top: 78px;
  overflow: hidden;
}
.run-list-body {
  max-height: 640px;
  overflow-y: auto;
  padding: 7px;
}
.run-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 9px 10px;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-soft);
  margin-bottom: 3px;
}
.run-item:hover {
  background: rgba(148, 163, 184, 0.05);
}
.run-item.active {
  border-color: rgba(45, 212, 191, 0.25);
  background: rgba(45, 212, 191, 0.07);
}
.run-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
}
.run-case {
  font-size: 11px;
  color: var(--dim);
  margin-top: 5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-time {
  font-size: 11px;
  color: var(--dim);
  margin-top: 3px;
}
.agent-main {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.flow-section .card-body {
  padding-top: 17px;
}
.tool-strip {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 17px;
  padding-top: 13px;
  border-top: 1px solid var(--line);
}
.tool-pill {
  font-size: 11px;
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 3px 6px;
  color: var(--muted);
  background: var(--panel-2);
}
.run-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
  background: var(--line);
  margin-bottom: 15px;
}
.run-stats > div {
  background: var(--panel-2);
  padding: 9px 11px;
  display: flex;
  align-items: baseline;
  gap: 5px;
}
.run-stats strong {
  font-family: var(--mono);
  font-size: 15px;
}
.run-stats strong.fail {
  color: var(--red);
}
.run-stats span {
  font-size: 11px;
  color: var(--dim);
}
.trace-list {
  display: flex;
  flex-direction: column;
}
.trace-row {
  position: relative;
}
.trace-line {
  display: flex;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px solid rgba(124, 160, 196, 0.075);
}
.trace-line::before {
  content: "";
  position: absolute;
  left: 36px;
  top: 34px;
  bottom: -8px;
  width: 1px;
  background: var(--line);
}
.trace-row:last-child .trace-line::before {
  display: none;
}
.trace-seq {
  width: 22px;
  flex: none;
  text-align: right;
  font-size: 11px;
  color: var(--dim);
  padding-top: 6px;
}
.trace-dot {
  width: 23px;
  height: 23px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex: none;
  border: 1px solid currentColor;
  background: var(--panel-2);
  z-index: 1;
}
.trace-content {
  flex: 1;
  min-width: 0;
}
.trace-top {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.trace-top strong {
  font-size: 11.5px;
  font-weight: 600;
}
.tool-name {
  font-size: 11px;
  color: var(--teal);
  background: rgba(45, 212, 191, 0.07);
  border: 1px solid rgba(45, 212, 191, 0.17);
  padding: 2px 5px;
  border-radius: 4px;
}
.trace-input {
  margin-top: 5px;
  font-size: 11px;
  color: var(--dim);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 5px;
  padding: 5px 7px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.trace-rationale {
  margin-top: 5px;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.55;
}
.trace-error {
  margin-top: 5px;
  font-size: 11px;
  color: var(--red);
  font-family: var(--mono);
}
.detail-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: transparent;
  color: var(--dim);
  font-size: 11px;
  padding: 4px 0 0;
}
.detail-toggle:hover {
  color: var(--teal);
}
.detail-toggle .rotated {
  transform: rotate(180deg);
}
.trace-output {
  margin: 6px 0 0;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel-2);
  color: #9fb6cd;
  font-size: 11px;
  line-height: 1.55;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.arch-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-top: 14px;
}
.arch-note p {
  margin-top: 7px;
  font-size: 11.5px;
  color: var(--muted);
  line-height: 1.7;
}
@media (max-width: 1100px) {
  .agent-grid {
    grid-template-columns: 1fr;
  }
  .run-list {
    position: static;
  }
  .run-list-body {
    max-height: 220px;
  }
  .arch-grid {
    grid-template-columns: 1fr;
  }
  .run-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
