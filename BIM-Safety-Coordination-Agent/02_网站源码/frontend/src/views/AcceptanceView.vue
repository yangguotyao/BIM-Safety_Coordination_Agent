<script setup lang="ts">
import { t } from '../i18n'
import { computed, onMounted, ref } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  Download,
  FlaskConical,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  XCircle,
} from 'lucide-vue-next'
import Modal from '../components/Modal.vue'
import { api } from '../api'
import { errorMessage, refreshSummary, store, toast } from '../store'
import type { AcceptanceResult, AcceptanceSummary } from '../types'
import { formatDateTime } from '../utils'

const tests = [
  { id: 'T01', name: t('正常样例'), expected: 'no_issue_in_checked_items', input: t('EV-007 · 防护 1.2m、人员与时段匹配') },
  { id: 'T02', name: t('无防护风险'), expected: 'risk_candidate', input: t('EV-001 · 模拟防护缺失且有人员暴露') },
  { id: 'T03', name: t('栏杆高度不足'), expected: 'risk_candidate', input: t('EV-003 · 栏杆 1.0m、已标注临边') },
  { id: 'T04', name: t('证据不足'), expected: 'needs_evidence', input: t('EV-004 · 人员字段 unknown') },
  { id: 'T05', name: t('时间不匹配'), expected: 'needs_evidence', input: t('EV-005 · 证据属于前一天') },
  { id: 'T06', name: t('失效条款'), expected: 'retired_rule_excluded', input: t('检索 JGJ 4.1.1 历史强条') },
  { id: 'T07', name: t('整改复核失败'), expected: 'reopened', input: t('EV-001 + EV-006 · 实施后仍缺失') },
  { id: 'T08', name: t('整改复核通过'), expected: 'closed', input: t('EV-001 + EV-010 · 人工确认') },
  { id: 'T09', name: t('无效构件GUID'), expected: 'validation_error', input: t('不存在的 GUID 创建案例') },
  { id: 'T10', name: t('单位与标高'), expected: 'unit_normalized', input: t('17300 mm → 17.3m；坠落 2.5m') },
  { id: 'T11', name: t('未经审批'), expected: 'transition_rejected', input: t('pending_review 直接提交复核') },
  { id: 'T12', name: t('关闭后条件变化'), expected: 'reopened', input: t('EV-010 关闭 + EV-011 条件变化') },
]

const results = ref<AcceptanceResult[]>([])
const loading = ref(true)
const running = ref('')
const resetOpen = ref(false)
const expanded = ref<Record<string, boolean>>({})
const lastRunAt = ref('')

const resultMap = computed(() => {
  const map: Record<string, AcceptanceResult> = {}
  for (const item of results.value) map[item.test_id] = item
  return map
})
const passed = computed(() => results.value.filter((item) => item.passed).length)
const executed = computed(() => results.value.length)
const percent = computed(() => Math.round((passed.value / 12) * 100))
const allPassed = computed(() => passed.value === 12)

const expectedLabel: Record<string, string> = {
  no_issue_in_checked_items: t('已检查项无问题'),
  risk_candidate: t('风险候选'),
  needs_evidence: t('需补证'),
  retired_rule_excluded: t('已排除废止条款'),
  reopened: t('重新打开'),
  closed: t('关闭'),
  validation_error: t('422 校验失败'),
  unit_normalized: t('单位归一'),
  transition_rejected: t('409 状态拒绝'),
}

async function load() {
  loading.value = true
  try {
    const response = await api.get<AcceptanceSummary>('/demo/acceptance/latest')
    results.value = response.results || []
    const timestamps = results.value.map((item) => item.run_at).filter(Boolean) as string[]
    lastRunAt.value = timestamps.sort().slice(-1)[0] || ''
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

async function runOne(testId: string) {
  if (running.value) return
  running.value = testId
  try {
    await api.post(`/demo/acceptance/${testId}`)
    await load()
    await refreshSummary()
    const result = resultMap.value[testId]
    toast(result?.passed ? t('{id} 通过：{actual}',{id:testId,actual:String(result.actual)}) : t('{id} 未通过：{actual}',{id:testId,actual:String(result?.actual || t('未知'))}), result?.passed ? 'success' : 'error', 5500)
  } catch (error: any) {
    toast(errorMessage(error), 'error', 8000)
  } finally {
    running.value = ''
  }
}

async function runAll() {
  if (running.value) return
  running.value = 'ALL'
  try {
    await api.post('/demo/acceptance/run-all')
    await load()
    await refreshSummary()
    toast(t('12 项验收执行完成：{passed}/12 通过。',{passed:passed.value}), allPassed.value ? 'success' : 'warning', 6000)
  } catch (error: any) {
    toast(errorMessage(error), 'error', 9000)
  } finally {
    running.value = ''
  }
}

async function reset() {
  if (running.value) return
  running.value = 'RESET'
  try {
    await api.post('/demo/reset')
    results.value = []
    resetOpen.value = false
    await refreshSummary()
    toast(t('已重置 runtime 演示数据库与上传件；原始资料未改动。'), 'success', 6000)
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    running.value = ''
  }
}

function toggle(testId: string) {
  expanded.value[testId] = !expanded.value[testId]
}

function downloadReport() {
  const payload = {
    exported_at: new Date().toISOString(),
    passed: passed.value,
    total: 12,
    results: results.value,
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'acceptance-results.json'
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(load)
</script>

<template>
  <div class="page acceptance-page">
    <div class="page-head">
      <div>
        
        <h1>{{ t('验收实验室') }}</h1>
      </div>
      <div class="head-actions">
        <button class="btn btn-sm" :disabled="!!running" @click="runAll">
          <Loader2 v-if="running === 'ALL'" :size="13" class="spin" />
          <Play v-else :size="13" />
          {{ t('运行全部 12 项') }}
        </button>
        <button class="btn btn-sm" :disabled="!results.length" @click="downloadReport"><Download :size="13" /> {{ t('下载 JSON') }}</button>
        <button class="btn btn-sm btn-danger" :disabled="!!running" @click="resetOpen = true"><RotateCcw :size="13" /> {{ t('重置夹具') }}</button>
      </div>
    </div>

    <div class="acceptance-hero card">
      <div class="score-ring" :style="{ '--pct': `${percent}%` }">
        <div class="score-inner">
          <strong>{{ passed }}</strong>
          <span>/ 12</span>
        </div>
      </div>
      <div class="score-copy">
        <div class="row">
          <span class="badge" :class="allPassed ? 'tone-green' : executed ? 'tone-amber' : 'tone-slate'">
            {{ executed ? (allPassed ? t('全部通过') : t('存在失败')) : t('尚未执行') }}
          </span>
          <span class="badge tone-slate">{{ executed }}{{ t('/12 已执行') }}</span>
          <span v-if="lastRunAt" class="badge tone-cyan">{{ t('最近') }} {{ formatDateTime(lastRunAt) }}</span>
        </div>
        <h2>{{ executed ? (allPassed ? t('验收夹具全部符合期望') : t('仍有验收项不符合期望')) : t('运行 12 项验收场景') }}</h2>
        <p>
          {{ t('覆盖正常、无防护、栏杆不足、证据不足、时间不匹配、废止条款、复核失败 / 通过、无效 GUID、单位标高、未审批与关闭后重开。') }}
        </p>
      </div>
      <div class="score-grid">
        <div v-for="test in tests" :key="test.id" class="score-cell" :class="{ pass: resultMap[test.id]?.passed, fail: resultMap[test.id] && !resultMap[test.id]?.passed }">
          <span class="mono">{{ test.id }}</span>
          <CheckCircle2 v-if="resultMap[test.id]?.passed" :size="11" />
          <XCircle v-else-if="resultMap[test.id]" :size="11" />
        </div>
      </div>
    </div>

    <div class="acceptance-note">
      <ShieldCheck :size="13" />
      <span>{{ t('验收执行会创建独立案例；可随时重置 runtime 数据。原始 IFC、规范 PDF、证据图和资料包不会被修改。') }}</span>
      <span v-if="running" class="running-tag"><Loader2 :size="11" class="spin" /> {{ t('正在执行') }} {{ running === 'ALL' ? t('12 项') : running }}…</span>
    </div>

    <div v-if="loading" class="loading-state card"><Loader2 :size="18" class="spin" /> {{ t('读取最近验收结果…') }}</div>

    <div v-else class="test-grid">
      <article v-for="test in tests" :key="test.id" class="test-card card" :class="{ pass: resultMap[test.id]?.passed, fail: resultMap[test.id] && !resultMap[test.id]?.passed }">
        <div class="test-head">
          <div class="test-id mono">{{ test.id }}</div>
          <span v-if="resultMap[test.id]" class="badge" :class="resultMap[test.id]?.passed ? 'tone-green' : 'tone-red'">
            {{ resultMap[test.id]?.passed ? 'PASS' : 'FAIL' }}
          </span>
          <span v-else class="badge tone-slate">NOT RUN</span>
        </div>
        <h3>{{ test.name }}</h3>
        <div class="test-input">{{ test.input }}</div>

        <div class="expected-row">
          <span class="k">EXPECTED</span>
          <span class="mono expected">{{ expectedLabel[test.expected] || test.expected }}</span>
        </div>
        <div class="expected-row">
          <span class="k">ACTUAL</span>
          <span v-if="resultMap[test.id]" class="mono actual" :class="resultMap[test.id]?.passed ? 'ok' : 'bad'">{{ resultMap[test.id]?.actual }}</span>
          <span v-else class="mono actual dim">—</span>
        </div>

        <div v-if="resultMap[test.id]" class="test-result-meta">
          <span class="mono tiny dim">{{ resultMap[test.id]?.case_id || 'no case' }}</span>
          <span class="tiny dim">{{ resultMap[test.id]?.run_at ? formatDateTime(resultMap[test.id]?.run_at) : '' }}</span>
        </div>

        <div v-if="resultMap[test.id]" class="test-actions">
          <button class="detail-toggle" @click="toggle(test.id)">
            <ChevronDown :size="12" :class="{ rotated: expanded[test.id] }" />
            {{ expanded[test.id] ? t('收起实际返回') : t('查看实际返回') }}
          </button>
          <button class="btn btn-sm" :disabled="!!running" @click="runOne(test.id)">
            <Loader2 v-if="running === test.id" :size="12" class="spin" />
            <RefreshCw v-else :size="12" />
            {{ t('重跑') }}
          </button>
        </div>
        <div v-else class="test-actions">
          <button class="btn btn-sm btn-primary" :disabled="!!running" @click="runOne(test.id)">
            <Loader2 v-if="running === test.id" :size="12" class="spin" />
            <Play v-else :size="12" />
            {{ t('运行') }}
          </button>
        </div>

        <pre v-if="expanded[test.id]" class="test-output">{{ JSON.stringify(resultMap[test.id]?.details, null, 2) }}</pre>
      </article>
    </div>

    <div class="acceptance-footer">
      <div class="card">
        <div class="card-body">
          <div class="caption">HOW IT RUNS</div>
          <p>{{ t('每项测试创建独立案例 → 启动真实 run → 执行 LangGraph → 校验状态与结果 → 写入 acceptance_results。失败也会保存错误与状态码。') }}</p>
        </div>
      </div>
      <div class="card">
        <div class="card-body">
          <div class="caption">ORACLE</div>
          <p>{{ t('期望值来自资料包') }} <span class="mono">{{ t('验收用例.json') }}</span>{{ t('，不是页面硬编码的“通过”。result / status / 错误码分别校验。') }}</p>
        </div>
      </div>
      <div class="card">
        <div class="card-body">
          <div class="caption">DATA SAFETY</div>
          <p>{{ t('重置只删除 runtime/app.db 和 runtime/uploads，不触碰 01_资料与依据中的任何原件。') }}</p>
        </div>
      </div>
    </div>

    <Modal :open="resetOpen" :title="t('重置演示夹具？')" :subtitle="t('只影响 runtime 数据库与上传件；原始资料不会改动。')" width="480px" @close="resetOpen = false">
      <div class="notice danger">
        <AlertTriangle :size="14" />
        <span>{{ t('将删除所有案例、run、trace、验收结果和上传件，并恢复预置案例。此操作不可撤销。') }}</span>
      </div>
      <template #footer>
        <button class="btn" @click="resetOpen = false">{{ t('取消') }}</button>
        <button class="btn btn-danger" :disabled="running === 'RESET'" @click="reset">
          <Loader2 v-if="running === 'RESET'" :size="13" class="spin" />
          <RotateCcw v-else :size="13" />
          {{ t('确认重置') }}
        </button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.acceptance-page {
  max-width: 1680px;
}
.acceptance-hero {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr) 250px;
  gap: 24px;
  align-items: center;
  padding: 22px 24px;
  margin-bottom: 12px;
}
.score-ring {
  width: 104px;
  height: 104px;
  border-radius: 50%;
  background: conic-gradient(var(--teal) var(--pct), rgba(124, 160, 196, 0.13) 0);
  display: grid;
  place-items: center;
  position: relative;
}
.score-ring::after {
  content: "";
  position: absolute;
  inset: 7px;
  border-radius: 50%;
  background: var(--panel-2);
}
.score-inner {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: baseline;
  gap: 2px;
}
.score-inner strong {
  font-family: var(--mono);
  font-size: 27px;
}
.score-inner span {
  font-size: 11px;
  color: var(--dim);
}
.score-copy h2 {
  margin-top: 9px;
  font-size: 20px;
}
.score-copy p {
  margin-top: 7px;
  color: var(--muted);
  font-size: 11.5px;
  line-height: 1.65;
  max-width: 700px;
}
.score-grid {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 4px;
}
.score-cell {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 4px 5px;
  border: 1px solid var(--line);
  border-radius: 4px;
  font-size: 11px;
  color: var(--dim);
  background: var(--panel-2);
}
.score-cell.pass {
  color: var(--green);
  border-color: rgba(52, 211, 153, 0.28);
  background: rgba(52, 211, 153, 0.06);
}
.score-cell.fail {
  color: var(--red);
  border-color: rgba(251, 113, 133, 0.28);
  background: rgba(251, 113, 133, 0.06);
}
.acceptance-note {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 13px;
  padding: 0 3px;
  color: var(--dim);
  font-size: 11px;
}
.acceptance-note svg {
  color: var(--teal);
}
.running-tag {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--cyan);
}
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 50px;
  color: var(--muted);
}
.test-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
.test-card {
  padding: 14px;
  display: flex;
  flex-direction: column;
  transition: 150ms ease;
  border-top: 2px solid var(--line);
}
.test-card.pass {
  border-top-color: rgba(52, 211, 153, 0.6);
}
.test-card.fail {
  border-top-color: rgba(251, 113, 133, 0.65);
}
.test-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.test-id {
  font-size: 11px;
  color: var(--teal);
  letter-spacing: 0.08em;
}
.test-card h3 {
  margin-top: 9px;
  font-size: 14px;
}
.test-input {
  margin-top: 4px;
  font-size: 11px;
  color: var(--dim);
  min-height: 28px;
}
.expected-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 5px;
  background: var(--panel-2);
  border: 1px solid var(--line);
}
.expected-row .k {
  width: 58px;
  flex: none;
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.1em;
  color: var(--dim);
}
.expected {
  font-size: 11px;
  color: var(--text-soft);
}
.actual.ok { color: var(--green); }
.actual.bad { color: var(--red); }
.actual.dim { color: var(--dim); }
.test-result-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}
.test-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 10px;
}
.detail-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: transparent;
  color: var(--dim);
  font-size: 11px;
  padding: 0;
}
.detail-toggle:hover {
  color: var(--teal);
}
.detail-toggle .rotated {
  transform: rotate(180deg);
}
.test-output {
  margin: 8px 0 0;
  padding: 9px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: var(--panel-2);
  color: #9fb6cd;
  font-size: 11px;
  line-height: 1.5;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
.acceptance-footer {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}
.acceptance-footer p {
  margin-top: 7px;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.65;
}
@media (max-width: 1280px) {
  .test-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .acceptance-hero {
    grid-template-columns: 110px minmax(0, 1fr);
  }
  .score-grid {
    grid-column: span 2;
    grid-template-columns: repeat(12, 1fr);
  }
}
@media (max-width: 820px) {
  .test-grid,
  .acceptance-footer {
    grid-template-columns: 1fr;
  }
  .acceptance-hero {
    grid-template-columns: 1fr;
  }
  .score-grid {
    grid-column: auto;
    grid-template-columns: repeat(6, 1fr);
  }
}
</style>
