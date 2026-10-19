<script setup lang="ts">
import {
  ArrowUpRight,
  BookOpen,
  Box,
  CheckCircle2,
  Database,
  Download,
  ExternalLink,
  FileText,
  GitBranch,
  Info,
  Layers,
  Lock,
  Scale,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-vue-next'
import FlowDiagram from '../components/FlowDiagram.vue'
import { store } from '../store'

const facts = [
  { k: '主模型', v: 'S1 bSDD_references_example.ifc', mono: true },
  { k: '模型版本', v: '4075c44a6e47', mono: true },
  { k: 'Schema', v: 'IFC2X3', mono: true },
  { k: '模型构件', v: '16,372 IfcElement / 19 楼层', mono: false },
  { k: '案例楼层', v: '05 vijfde verdieping · 1,247 构件', mono: false },
  { k: '整栋总览', v: '16,372 构件 / 154 渲染批次', mono: false },
  { k: '板边区域', v: '35 对象（4 Slab + 31 Wall）', mono: false },
  { k: '主构件', v: '0FOHK4aT910wgskSbVHn0U', mono: true },
  { k: '世界 Z', v: '17.300 m（不是坠落高度）', mono: false },
  { k: '演示坠落高度', v: '2.5 m（模拟假设）', mono: false },
  { k: '规范', v: 'GB 55034-2022 / JGJ 80-2016', mono: false },
  { k: 'active 规则', v: '7 条人工核对释义', mono: false },
  { k: '证据', v: '12 张预置示意图 + 上传现场照片', mono: false },
]

const roles = [
  ['Safety Coordinator', '维护案例状态、拆解任务、协调节点', '状态机 / 全部工具'],
  ['Knowledge', '检索现行有效条款，保留 PDF 页码', 'rule_retrieval / FTS5'],
  ['Inspection', '形成结构化观察，标记缺失字段', 'evidence_check'],
  ['Risk', '综合几何、活动、证据与规则', 'spatial_check / risk_assessment'],
  ['Intervention', '生成可审核措施、责任人、验证要求', 'control_template'],
  ['Verification', '检查实施后证据与残余风险', 'verification_check'],
]

const tree = `BIM-Safety-Coordination-Agent/
├─ 00_执行计划与自检/      执行计划、自检、合规矩阵
├─ 01_资料与依据/          原始方案、截图、S1、规范、论文、验收
├─ 02_网站源码/            FastAPI + Vue3 + Three.js
├─ 03_测试与验收/          测试报告、结果 JSON、截图
└─ 04_演示与截图/          演示手册、页面截图`
</script>

<template>
  <div class="page about-page">
    <div class="page-head">
      <div>
        
        <h1>方案与边界</h1>
      </div>
      <div class="head-actions">
        <a class="btn btn-sm" href="/api/files/plan"><Download :size="13" /> 执行计划</a>
        <a class="btn btn-sm" href="/api/docs" target="_blank"><FileText :size="13" /> API 文档</a>
        <span class="badge tone-teal"><ShieldCheck :size="12" /> v1.0</span>
      </div>
    </div>

    <section class="about-hero card">
      <div class="about-hero-copy">
        <div class="caption">THESIS</div>
        <h2>不是“让 LLM 操作 BIM”，<br />而是让 Agent 把任务、空间、进度、证据和规范连接起来。</h2>
        <p>
          BIM 提供真实的空间与实体上下文；施工任务与时间给出“正在发生什么”；现场证据给出“看到了什么”；
          规范知识给出“依据是什么”。Agent 的价值在于组织这些异构信息，形成可审核、可实施、可复核、可重新打开的
          Safety Case，而不是替代工程计算或现场判断。
        </p>
        <div class="thesis-pills">
          <span class="badge tone-teal">BIM as context</span>
          <span class="badge tone-cyan">LLM orchestrates</span>
          <span class="badge tone-violet">tools compute</span>
          <span class="badge tone-green">human authorizes</span>
        </div>
      </div>
      <div class="about-hero-diagram">
        <FlowDiagram compact />
      </div>
    </section>

    <div class="about-grid">
      <section class="card">
        <div class="card-head"><div class="card-title"><Box :size="15" /> 数据事实</div><span class="badge tone-teal">VERIFIED</span></div>
        <div class="card-body">
          <div class="fact-list">
            <div v-for="fact in facts" :key="fact.k" class="fact-row">
              <span class="k">{{ fact.k }}</span>
              <span class="v" :class="{ mono: fact.mono }">{{ fact.v }}</span>
            </div>
          </div>
          <div class="notice warn" style="margin-top: 13px">
            <TriangleAlert :size="13" />
            <span>该 IFC 无显式 IfcOpeningElement、IfcTask、IfcWorkSchedule；不能据此声称取得真实洞口或真实 4D 计划。</span>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head"><div class="card-title"><GitBranch :size="15" /> 六类职责</div><span class="badge tone-cyan">LANGGRAPH</span></div>
        <div class="card-body">
          <div class="role-table">
            <div v-for="role in roles" :key="role[0]" class="role-row">
              <div class="role-name">{{ role[0] }}</div>
              <div class="role-duty">{{ role[1] }}</div>
              <div class="role-tool mono">{{ role[2] }}</div>
            </div>
          </div>
          <div class="notice" style="margin-top: 12px">
            <Info :size="13" />
            <span>截图目录中的 bim_agent.py 映射为 BIM 工具与三维工作台，不作为第七个 LLM 节点；几何与距离由确定性代码执行。</span>
          </div>
        </div>
      </section>
    </div>

    <section class="card">
      <div class="card-head"><div class="card-title"><Scale :size="15" /> 真实 / 模拟 / 不宣称</div><span class="badge tone-amber">BOUNDARY</span></div>
      <div class="card-body">
        <div class="boundary-grid">
          <div class="boundary-box real">
            <div class="caption">REAL SOURCE</div>
            <h3>真实、可追溯</h3>
            <ul>
              <li>S1 IFC 板 / 墙几何与 GUID</li>
              <li>16,372 构件、19 楼层、1,247 个 05 层索引</li>
              <li>GB 55034 与 JGJ 80 官方 PDF、页码、公告</li>
              <li>12 张证据图的几何底图来自真实 IFC</li>
            </ul>
          </div>
          <div class="boundary-box sim">
            <div class="caption">SIMULATED</div>
            <h3>演示输入，持续标注</h3>
            <ul>
              <li>人员位置、防护状态、施工活动</li>
              <li>2.5 m 坠落高度假设</li>
              <li>1.0 m 暴露距离（项目策略，不是国标）</li>
              <li>12 张证据图 = 真实几何 + 模拟标记</li>
            </ul>
          </div>
          <div class="boundary-box never">
            <div class="caption">NOT CLAIMED</div>
            <h3>明确不宣称</h3>
            <ul>
              <li>真实事故概率或校准风险等级</li>
              <li>现场合规、无隐患或已整改</li>
              <li>全项目自动安全检查</li>
              <li>识别出真实 MEP 任务或真实洞口</li>
            </ul>
          </div>
        </div>
      </div>
    </section>

    <div class="about-grid">
      <section class="card">
        <div class="card-head"><div class="card-title"><Layers :size="15" /> 资料整合包</div><span class="badge tone-slate">FINDER</span></div>
        <div class="card-body">
          <pre class="tree">{{ tree }}</pre>
          <p class="small muted" style="margin-top: 10px">
            原始资料在 <span class="mono">01_资料与依据</span> 中保持原目录结构；网站运行只读这些输入，数据库写入 runtime。
          </p>
        </div>
      </section>

      <section class="card">
        <div class="card-head"><div class="card-title"><Database :size="15" /> 运行与验证</div><span class="badge tone-green">TESTED</span></div>
        <div class="card-body">
          <div class="run-line">
            <span class="dot teal" />
            <div>
              <strong>{{ store.health?.mode === 'live' ? '当前：真实模型模式' : '当前：规则演示模式' }}</strong>
              <div class="small muted">DeepSeek 任务分析 · Qwen 图像观察 · 人工确认</div>
            </div>
          </div>
          <div class="run-line">
            <span class="dot cyan" />
            <div>
              <strong>真实模型模式</strong>
              <div class="small muted">显式配置 MODEL_BASE_URL / KEY / NAME；不完整则返回可操作错误，不静默降级。</div>
            </div>
          </div>
          <div class="run-line">
            <span class="dot amber" />
            <div>
              <strong>启动</strong>
              <div class="small muted mono">Start-Demo.cmd · http://127.0.0.1:8001</div>
            </div>
          </div>
          <div class="run-line">
            <span class="dot green" />
            <div>
              <strong>验收</strong>
              <div class="small muted">12/12 通过；T07 复核失败与 T08 复核通过均保留前后证据。</div>
            </div>
          </div>
          <a class="btn btn-sm" href="/acceptance" style="margin-top: 10px">打开验收实验室 <ArrowUpRight :size="12" /></a>
        </div>
      </section>
    </div>

    <section class="card quote-card">
      <div class="card-body">
        <div class="caption">LITERATURE REVIEW / 可直接改写的案例表述</div>
        <blockquote>
          本案例构建了一个 BIM 驱动的施工安全协同 Agent（BIM-Safety Coordination Agent）。与“由大语言模型直接操作 BIM”不同，
          该案例将 IFC 构件查询、空间距离与时间匹配封装为确定性工具，由六类职责节点完成规范检索、证据检查、风险判定、
          控制建议与复核验证。案例以 S1 公开 IFC 的五层板边为空间对象，将真实构件 GUID、模拟现场观察、施工活动与现行规范
          关联为 Safety Case，并通过人工审批、实施记录、实施后证据和复核形成闭环。该案例用于展示 BIM 如何作为施工安全
          Agent 的空间与实体上下文，以及 Agent 如何组织多源证据而不是替代工程判断。
        </blockquote>
        <div class="quote-note">
          写作时请保留“模拟观察”“演示假设”“不构成现场合规结论”等限定语；不要把 17.3 m 世界高程写成坠落高度。
        </div>
      </div>
    </section>

    <div class="about-foot">
      <div class="row"><BookOpen :size="13" /> 原始方案：BIM-Safety_Coordination_Agent_方案 (1).docx</div>
      <div class="row"><FileText :size="13" /> 任务书：06_Astra任务书/一次性完成Demo任务书.md</div>
      <div class="row"><Lock :size="13" /> 不提交密钥；不修改资料原件</div>
      <a class="row" href="https://github.com/yangguotao/height-work-safety-agent" target="_blank" rel="noopener">
        <ExternalLink :size="13" /> 参考项目（仅形式参考，未复用代码）
      </a>
    </div>
  </div>
</template>

<style scoped>
.about-page {
  max-width: 1600px;
}
.about-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 24px;
  padding: 24px;
  margin-bottom: 14px;
  background:
    radial-gradient(600px 300px at 0% 0%, rgba(45, 212, 191, 0.07), transparent 70%),
    linear-gradient(180deg, rgba(17, 31, 51, 0.92), rgba(10, 20, 34, 0.92));
}
.about-hero h2 {
  margin-top: 11px;
  font-size: 24px;
  line-height: 1.45;
  letter-spacing: -0.02em;
}
.about-hero p {
  margin-top: 13px;
  color: var(--muted);
  font-size: 12.5px;
  line-height: 1.85;
  max-width: 720px;
}
.thesis-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 15px;
}
.about-hero-diagram {
  align-self: center;
  min-width: 0;
}
.about-hero-diagram :deep(.flow) {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.about-hero-diagram :deep(.flow-arrow) {
  display: none;
}
.about-hero-diagram :deep(.flow-node) {
  min-height: 102px;
  padding: 9px;
}
.about-hero-diagram :deep(.node-note) {
  display: none;
}
.about-hero-diagram :deep(.node-tools span) {
  font-size: 11px;
}
.about-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  margin-bottom: 14px;
}
.fact-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}
.fact-row {
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: 10px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(124, 160, 196, 0.07);
  font-size: 11px;
}
.fact-row:last-child {
  border-bottom: none;
}
.fact-row .k {
  color: var(--dim);
}
.fact-row .v {
  color: var(--text-soft);
  word-break: break-word;
}
.role-table {
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}
.role-row {
  display: grid;
  grid-template-columns: 130px minmax(0, 1fr) 170px;
  gap: 10px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(124, 160, 196, 0.08);
  font-size: 11px;
}
.role-row:last-child {
  border-bottom: none;
}
.role-name {
  font-weight: 600;
  color: var(--text-soft);
}
.role-duty {
  color: var(--muted);
}
.role-tool {
  color: var(--teal);
  font-size: 11px;
  text-align: right;
}
.boundary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.boundary-box {
  padding: 14px;
  border-radius: 9px;
  border: 1px solid var(--line);
  background: var(--panel-2);
}
.boundary-box.real {
  border-color: rgba(45, 212, 191, 0.2);
  background: rgba(45, 212, 191, 0.035);
}
.boundary-box.sim {
  border-color: rgba(251, 191, 36, 0.2);
  background: rgba(251, 191, 36, 0.03);
}
.boundary-box.never {
  border-color: rgba(251, 113, 133, 0.2);
  background: rgba(251, 113, 133, 0.03);
}
.boundary-box h3 {
  margin-top: 7px;
  font-size: 13px;
}
.boundary-box ul {
  margin: 9px 0 0;
  padding-left: 15px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.8;
}
.tree {
  margin: 0;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel-2);
  color: #9fb6cd;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.75;
  overflow: auto;
}
.run-line {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  padding: 8px 0;
  border-bottom: 1px solid rgba(124, 160, 196, 0.07);
}
.run-line:last-of-type {
  border-bottom: none;
}
.run-line strong {
  font-size: 11px;
  font-weight: 600;
}
.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: 5px;
  flex: none;
}
.dot.teal { background: var(--teal); box-shadow: 0 0 7px var(--teal); }
.dot.cyan { background: var(--cyan); box-shadow: 0 0 7px var(--cyan); }
.dot.amber { background: var(--amber); box-shadow: 0 0 7px var(--amber); }
.dot.green { background: var(--green); box-shadow: 0 0 7px var(--green); }
.quote-card {
  margin-bottom: 14px;
  background:
    radial-gradient(600px 300px at 100% 0%, rgba(167, 139, 250, 0.06), transparent 70%),
    linear-gradient(180deg, rgba(17, 31, 51, 0.92), rgba(10, 20, 34, 0.92));
}
.quote-card blockquote {
  margin: 11px 0 0;
  padding-left: 15px;
  border-left: 2px solid var(--violet);
  color: var(--text-soft);
  font-size: 12.5px;
  line-height: 1.95;
}
.quote-note {
  margin-top: 11px;
  font-size: 11px;
  color: var(--dim);
}
.about-foot {
  display: flex;
  flex-wrap: wrap;
  gap: 14px 24px;
  padding: 13px 4px;
  border-top: 1px solid var(--line);
  color: var(--dim);
  font-size: 11px;
}
.about-foot .row {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
@media (max-width: 1100px) {
  .about-hero,
  .about-grid {
    grid-template-columns: 1fr;
  }
  .boundary-grid {
    grid-template-columns: 1fr;
  }
  .role-row {
    grid-template-columns: 1fr;
  }
  .role-tool {
    text-align: left;
  }
}
</style>
