<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  ExternalLink,
  FileText,
  Filter,
  Info,
  Loader2,
  Search,
  ShieldAlert,
  Sparkles,
  XCircle,
} from 'lucide-vue-next'
import EmptyState from '../components/EmptyState.vue'
import { api } from '../api'
import { errorMessage, toast } from '../store'
import type { Rule } from '../types'
import { formatDateTime } from '../utils'

const route = useRoute()
const rules = ref<Rule[]>([])
const allRules = ref<Rule[]>([])
const selected = ref<Rule | null>(null)
const query = ref('')
const loading = ref(true)
const searched = ref(false)
const includeRetired = ref(true)
const topK = ref(3)
const searchMeta = ref<{ retired_excluded: string[]; note: string }>({ retired_excluded: [], note: '' })

const activeRules = computed(() => rules.value.filter((item) => item.status === 'active'))
const retiredRules = computed(() => rules.value.filter((item) => item.status === 'retired'))
const visibleRules = computed(() => {
  const rows = includeRetired.value ? rules.value : activeRules.value
  if (!searched.value) return rows
  return rows
})

async function loadAll() {
  loading.value = true
  try {
    const response = await api.get<any>('/rules?include_retired=true&q=')
    allRules.value = response.results || []
    rules.value = allRules.value
    const wanted = typeof route.query.rule === 'string' ? route.query.rule : ''
    selected.value = allRules.value.find((item) => item.rule_id === wanted) || allRules.value.find((item) => item.status === 'active') || null
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

async function search() {
  if (!query.value.trim()) {
    rules.value = allRules.value
    searched.value = false
    searchMeta.value = { retired_excluded: [], note: '' }
    return
  }
  loading.value = true
  try {
    const response = await api.get<any>(`/rules?q=${encodeURIComponent(query.value.trim())}&top_k=${topK.value}`)
    const active = response.results || []
    const retired = allRules.value.filter((item) => response.retired_excluded?.includes(item.rule_id))
    rules.value = [...active, ...retired]
    if (!selected.value || !rules.value.some((item) => item.rule_id === selected.value?.rule_id)) {
      selected.value = active[0] || retired[0] || null
    }
    searched.value = true
    searchMeta.value = {
      retired_excluded: response.retired_excluded || [],
      note: response.note || '',
    }
  } catch (error: any) {
    toast(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

function clearSearch() {
  query.value = ''
  search()
}

function openRule(rule: Rule) {
  selected.value = rule
}

async function pdfUrl(rule: Rule): Promise<string> {
  return `/api/files/rules/${rule.rule_id}`
}

watch(
  () => route.query.rule,
  (id) => {
    if (typeof id !== 'string') return
    const found = allRules.value.find((item) => item.rule_id === id)
    if (found) selected.value = found
  },
)

onMounted(loadAll)
</script>

<template>
  <div class="page knowledge-page">
    <div class="page-head">
      <div>
        
        <h1>规范知识库</h1>
      </div>
      <div class="head-actions">
        <span class="badge tone-green"><CheckCircle2 :size="12" /> {{ activeRules.length }} 有效</span>
        <span class="badge tone-red"><XCircle :size="12" /> {{ retiredRules.length }} 历史</span>
        
      </div>
    </div>

    <div class="search-bar card">
      <div class="search-input-wrap">
        <Search :size="15" class="dim" />
        <input
          v-model="query"
          class="input"
          placeholder="输入危险源 / 工序 / 条款，例如：临边 防护 1.2m；或 JGJ 4.1.1"
          @keyup.enter="search"
        />
        <button v-if="query" class="btn btn-ghost btn-icon btn-sm" @click="clearSearch">×</button>
      </div>
      <button class="btn btn-primary" :disabled="loading" @click="search">
        <Loader2 v-if="loading" :size="14" class="spin" />
        <Search v-else :size="14" />
        检索
      </button>
      <label class="toggle-line">
        <input v-model="includeRetired" type="checkbox" />
        <span>显示已废止历史记录</span>
      </label>
    </div>

    <div v-if="searched" class="search-result-bar" :class="{ warn: searchMeta.retired_excluded.length }">
      <Info :size="13" />
      <span>
        检索到 {{ activeRules.length }} 条有效条款
        <template v-if="searchMeta.retired_excluded.length">
          ；已排除 {{ searchMeta.retired_excluded.join('、') }} 等历史条款
        </template>
        <template v-if="searchMeta.note">。{{ searchMeta.note }}</template>
      </span>
    </div>

    <div class="knowledge-grid">
      <aside class="rule-list card">
        <div class="card-head">
          <div class="card-title"><BookOpen :size="15" /> 条款</div>
          <span class="badge tone-slate">{{ visibleRules.length }}</span>
        </div>
        <div class="rule-list-body">
          <button
            v-for="rule in visibleRules"
            :key="rule.rule_id"
            class="rule-item"
            :class="{ active: selected?.rule_id === rule.rule_id, retired: rule.status === 'retired' }"
            @click="openRule(rule)"
          >
            <div class="rule-item-top">
              <span class="mono">{{ rule.rule_id }}</span>
              <span class="badge" :class="rule.status === 'active' ? 'tone-green' : 'tone-red'">{{ rule.status }}</span>
            </div>
            <div class="rule-title">{{ rule.standard }} · {{ rule.clause }}</div>
            <div class="rule-snippet">{{ rule.text }}</div>
            <div class="rule-score" v-if="rule.score !== undefined">
              <Sparkles :size="10" /> score {{ rule.score }}
            </div>
          </button>
          <EmptyState v-if="!visibleRules.length" title="没有匹配条款" detail="换一个关键词，或关闭“仅 active”限制后查看历史记录。" />
        </div>
      </aside>

      <main v-if="selected" class="rule-detail card">
        <div class="rule-detail-head">
          <div class="rule-detail-title">
            <div class="row">
              <span class="badge" :class="selected.status === 'active' ? 'tone-green' : 'tone-red'">
                {{ selected.status === 'active' ? '现行有效' : '已废止 · 历史记录' }}
              </span>
              <span class="badge tone-violet">条文释义</span>
              <span class="mono tiny dim">{{ selected.rule_id }}</span>
            </div>
            <h2>{{ selected.standard }} · 第 {{ selected.clause }} 条</h2>
            <p class="rule-standard">{{ selected.text }}</p>
          </div>
          <a class="btn" :href="`/api/files/rules/${selected.rule_id}`" target="_blank" rel="noopener">
            <FileText :size="14" /> 打开官方原文 <ArrowUpRight :size="12" />
          </a>
        </div>

        <div v-if="selected.status === 'retired'" class="retired-banner">
          <ShieldAlert :size="15" />
          <div>
            <strong>该记录不用于当前判定</strong>
            <p>{{ selected.text }}</p>
          </div>
        </div>

        <div class="rule-facts">
          <div class="fact">
            <span class="caption">SOURCE</span>
            <span>{{ selected.source_path }}</span>
          </div>
          <div class="fact">
            <span class="caption">PDF PAGE</span>
            <span class="mono">p. {{ selected.pdf_page }}</span>
          </div>
          <div class="fact">
            <span class="caption">EFFECTIVE</span>
            <span class="mono">{{ selected.effective_from || '—' }}</span>
          </div>
          <div class="fact">
            <span class="caption">CHECKED</span>
            <span class="mono">{{ selected.checked_on || '—' }}</span>
          </div>
          <div class="fact wide">
            <span class="caption">APPLICABILITY</span>
            <span>{{ selected.applicability || '—' }}</span>
          </div>
          <div class="fact wide">
            <span class="caption">JURISDICTION</span>
            <span>{{ selected.jurisdiction || '—' }}</span>
          </div>
        </div>

        <div class="rule-body">
          <div class="section-title">USAGE NOTE / 使用边界</div>
          <div class="rule-notes">
            <div class="rule-note">
              <CheckCircle2 :size="14" />
              <div>
                <strong>这是释义，不是逐字原文</strong>
                <p>界面标注“条文释义”，并保留 PDF 页码；引用时必须同时给出标准号、条款和来源。</p>
              </div>
            </div>
            <div class="rule-note">
              <Info :size="14" />
              <div>
                <strong>单一检查项不等于整体合规</strong>
                <p>1.2 m 只是一项高度检查，不证明锚固、强度、连续性和全部安全要求合格。</p>
              </div>
            </div>
            <div class="rule-note warn">
              <ShieldAlert :size="14" />
              <div>
                <strong>中国规范 + 荷兰模型 = 研究演示</strong>
                <p>把中国规范应用于国外公开模型，不能据此宣称该项目违法、不合规或存在真实事故隐患。</p>
              </div>
            </div>
          </div>
        </div>

        <div class="rule-footer">
          <a :href="selected.source_url" target="_blank" rel="noopener" class="small">
            官方发布入口 <ExternalLink :size="11" />
          </a>
          <span class="mono tiny dim">{{ selected.source_path }} · p.{{ selected.pdf_page }}</span>
        </div>
      </main>

      <main v-else class="card">
        <EmptyState title="选择一条条款" detail="左侧列表来自 9 条已归档规则：7 条有效条款，2 条 retired。" />
      </main>
    </div>

    <div class="knowledge-foot">
      <div class="foot-card card">
        <div class="caption">INDEX POLICY</div>
        <p>默认只索引 status=active 的人工核对释义；OCR 工作文本不直接进入 RAG。</p>
      </div>
      <div class="foot-card card">
        <div class="caption">RETIRED POLICY</div>
        <p>JGJ 80-2016 被公告废止的强条（4.1.1、4.2.1、5.2.3、6.4.1、8.1.2）不得作为当前依据。</p>
      </div>
      <div class="foot-card card">
        <div class="caption">RETRIEVAL</div>
        <p>SQLite FTS5 中文二元组 + 关键词重排，top-k=3；不依赖外部 Embedding 或向量库。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.knowledge-page {
  max-width: 1680px;
}
.search-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 13px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.search-input-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 280px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0 9px;
  background: var(--panel-2);
}
.search-input-wrap .input {
  border: none;
  background: transparent;
  height: 36px;
  padding: 0;
}
.search-input-wrap .input:focus {
  box-shadow: none;
}
.toggle-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--muted);
  white-space: nowrap;
}
.toggle-line input {
  accent-color: var(--teal);
}
.search-result-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 11px;
  border: 1px solid rgba(56, 189, 248, 0.2);
  background: rgba(56, 189, 248, 0.04);
  border-radius: 8px;
  color: var(--cyan);
  font-size: 11px;
  margin-bottom: 12px;
}
.search-result-bar.warn {
  color: var(--amber);
  border-color: rgba(251, 191, 36, 0.22);
  background: rgba(251, 191, 36, 0.04);
}
.knowledge-grid {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}
.rule-list {
  position: sticky;
  top: 78px;
  max-height: calc(100vh - 100px);
  overflow: hidden;
}
.rule-list-body {
  max-height: calc(100vh - 156px);
  overflow-y: auto;
  padding: 7px;
}
.rule-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-soft);
  margin-bottom: 3px;
  transition: 130ms ease;
}
.rule-item:hover {
  background: rgba(148, 163, 184, 0.05);
}
.rule-item.active {
  border-color: rgba(45, 212, 191, 0.28);
  background: rgba(45, 212, 191, 0.065);
}
.rule-item.retired {
  opacity: 0.72;
}
.rule-item-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
  font-size: 11px;
  color: var(--teal);
}
.rule-title {
  font-size: 11px;
  font-weight: 600;
  margin-top: 4px;
}
.rule-snippet {
  font-size: 11px;
  color: var(--dim);
  line-height: 1.5;
  margin-top: 4px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.rule-score {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-top: 5px;
  font-size: 11px;
  color: var(--violet);
}
.rule-detail {
  overflow: hidden;
}
.rule-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 22px 24px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(160deg, rgba(45, 212, 191, 0.045), transparent 55%);
}
.rule-detail-title h2 {
  margin-top: 11px;
  font-size: 23px;
}
.rule-standard {
  margin-top: 12px;
  color: var(--text-soft);
  font-size: 14px;
  line-height: 1.9;
  max-width: 850px;
}
.rule-detail-head .btn {
  flex: none;
}
.retired-banner {
  display: flex;
  gap: 10px;
  margin: 16px 24px 0;
  padding: 12px 13px;
  border: 1px solid rgba(251, 113, 133, 0.25);
  background: rgba(251, 113, 133, 0.05);
  border-radius: 8px;
  color: var(--red);
}
.retired-banner strong {
  font-size: 11.5px;
}
.retired-banner p {
  margin-top: 4px;
  color: var(--muted);
  font-size: 11px;
}
.rule-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--line);
  margin: 18px 24px;
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.fact {
  background: var(--panel-2);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--text-soft);
  word-break: break-word;
}
.fact.wide {
  grid-column: span 2;
}
.rule-body {
  padding: 0 24px 22px;
}
.rule-notes {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}
.rule-note {
  display: flex;
  gap: 9px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--teal);
}
.rule-note strong {
  font-size: 11px;
  color: var(--text-soft);
}
.rule-note p {
  margin-top: 3px;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.6;
}
.rule-note.warn {
  color: var(--amber);
}
.rule-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 13px 24px;
  border-top: 1px solid var(--line);
  background: var(--panel-2);
}
.rule-footer a {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.knowledge-foot {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}
.foot-card {
  padding: 13px 15px;
}
.foot-card p {
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.65;
}
@media (max-width: 1100px) {
  .knowledge-grid {
    grid-template-columns: 1fr;
  }
  .rule-list {
    position: static;
    max-height: none;
  }
  .rule-list-body {
    max-height: 300px;
  }
  .rule-facts {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 760px) {
  .knowledge-foot {
    grid-template-columns: 1fr;
  }
  .rule-detail-head {
    flex-direction: column;
  }
}
</style>
