<script setup lang="ts">
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  ClipboardCheck,
  Hammer,
  ScanLine,
  ShieldCheck,
} from 'lucide-vue-next'

withDefaults(defineProps<{ compact?: boolean; activeRole?: string }>(), {
  compact: false,
  activeRole: '',
})

const roles = [
  {
    key: 'Safety Coordinator',
    label: 'Safety Coordinator',
    cn: '协调与状态',
    icon: ShieldCheck,
    tone: 'teal',
    tools: ['状态机', '任务拆解'],
    note: '维护 Safety Case，决定下一步',
  },
  {
    key: 'Knowledge',
    label: 'Knowledge',
    cn: '规范检索',
    icon: BookOpen,
    tone: 'blue',
    tools: ['FTS5', 'top-k=3'],
    note: '只检索 active 释义',
  },
  {
    key: 'Inspection',
    label: 'Inspection',
    cn: '证据观察',
    icon: ScanLine,
    tone: 'amber',
    tools: ['evidence_check'],
    note: '结构化观察与缺失字段',
  },
  {
    key: 'Risk',
    label: 'Risk',
    cn: '风险判定',
    icon: AlertTriangle,
    tone: 'red',
    tools: ['spatial_check', 'risk_assessment'],
    note: '确定性检查表',
  },
  {
    key: 'Intervention',
    label: 'Intervention',
    cn: '候选控制',
    icon: Hammer,
    tone: 'violet',
    tools: ['control_template'],
    note: '措施、责任人、验证要求',
  },
  {
    key: 'Verification',
    label: 'Verification',
    cn: '复核闭环',
    icon: ClipboardCheck,
    tone: 'green',
    tools: ['verification_check'],
    note: '实施后证据与残余风险',
  },
]
</script>

<template>
  <div class="flow" :class="{ compact }">
    <div
      v-for="(role, index) in roles"
      :key="role.key"
      class="flow-node"
      :class="[`tone-${role.tone}`, { active: activeRole === role.key }]"
    >
      <div class="node-top">
        <span class="node-index mono">0{{ index + 1 }}</span>
        <component :is="role.icon" :size="16" />
      </div>
      <div class="node-label">{{ role.label }}</div>
      <div class="node-cn">{{ role.cn }}</div>
      <div v-if="!compact" class="node-note">{{ role.note }}</div>
      <div class="node-tools">
        <span v-for="tool in role.tools" :key="tool" class="mono">{{ tool }}</span>
      </div>
      <ArrowRight v-if="index < roles.length - 1" :size="14" class="flow-arrow" />
    </div>
  </div>
</template>

<style scoped>
.flow {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 12px;
}
.flow-node {
  position: relative;
  padding: 13px 12px 11px;
  border: 1px solid var(--line);
  border-radius: 11px;
  background: var(--panel-2);
  min-height: 142px;
  transition: 160ms ease;
}
.flow-node:hover {
  transform: translateY(-2px);
  border-color: var(--line-strong);
}
.flow-node.active {
  border-color: currentColor;
  box-shadow: 0 0 0 1px currentColor, 0 10px 30px rgba(0, 0, 0, 0.25);
}
.node-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  color: inherit;
  opacity: 0.9;
}
.node-index {
  font-size: 9px;
  color: var(--dim);
  letter-spacing: 0.1em;
}
.node-label {
  font-size: 11.5px;
  font-weight: 650;
  letter-spacing: 0.01em;
  color: var(--text);
}
.node-cn {
  font-size: 10.5px;
  color: inherit;
  margin-top: 2px;
}
.node-note {
  font-size: 9.5px;
  color: var(--dim);
  line-height: 1.45;
  margin-top: 6px;
  min-height: 26px;
}
.node-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 9px;
}
.node-tools span {
  font-size: 8px;
  padding: 2px 5px;
  border-radius: 4px;
  border: 1px solid var(--line);
  color: var(--dim);
  background: rgba(5, 13, 24, 0.5);
}
.flow-arrow {
  position: absolute;
  right: -14px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--dim);
  z-index: 2;
  background: var(--bg);
  border-radius: 50%;
  padding: 2px;
}
.compact .flow-node {
  min-height: 108px;
  padding: 10px;
}
.compact .node-note {
  display: none;
}
.compact .node-top {
  margin-bottom: 8px;
}
@media (max-width: 1280px) {
  .flow {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .flow-arrow {
    display: none;
  }
}
@media (max-width: 760px) {
  .flow {
    grid-template-columns: 1fr;
  }
}
</style>
