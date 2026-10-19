import type { CaseStatus } from './types'

export const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  analyzing: '分析中',
  needs_evidence: '待补证',
  pending_review: '待审核',
  approved: '待整改',
  rectifying: '整改中',
  pending_verification: '待复核',
  closed: '已关闭',
  reopened: '已重开',
  rejected: '已拒绝',
}

export const STATUS_TONES: Record<string, string> = {
  draft: 'slate',
  analyzing: 'cyan',
  needs_evidence: 'amber',
  pending_review: 'violet',
  approved: 'blue',
  rectifying: 'orange',
  pending_verification: 'teal',
  closed: 'green',
  reopened: 'rose',
  rejected: 'red',
}

export const RESULT_LABELS: Record<string, string> = {
  risk_candidate: '风险候选',
  no_issue_in_checked_items: '已检查项无问题',
  needs_evidence: '需补充证据',
  pass_in_demo_scope: '演示范围内通过',
  fail: '未通过',
  unknown: '未知',
  pass: '通过',
}

export const EVENT_LABELS: Record<string, string> = {
  case_created: '创建案例',
  analysis_started: '开始分析',
  analysis_completed: '分析完成',
  analysis_failed: '分析失败',
  analysis_incomplete: '分析不完整',
  review_approved: '审核批准',
  review_rejected: '审核拒绝',
  controls_modified: '修改控制措施',
  implementation_recorded: '提交隐患整改',
  evidence_added: '追加证据',
  evidence_uploaded: '上传证据',
  verification_passed: '复核通过',
  verification_failed: '复核失败',
  case_reopened: '重新打开案例',
  scope_updated: '更新范围与人员标注',
  activity_plan_updated: '编制作业计划',
  activity_plan_adjusted: '调整作业计划',
  site_note_added: '保存现场记录',
  site_text_extracted: '提取文本候选',
  text_conflict_resolved: '澄清文本差异',
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] || status
}

export function statusTone(status: string): string {
  return STATUS_TONES[status] || 'slate'
}

export function resultLabel(result: string): string {
  return RESULT_LABELS[result] || result
}

export function eventLabel(event: string): string {
  return EVENT_LABELS[event] || event
}

export function shortGuid(guid: string, head = 8, tail = 4): string {
  if (!guid) return ''
  if (guid.length <= head + tail + 1) return guid
  return `${guid.slice(0, head)}…${guid.slice(-tail)}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
    .format(date)
    .replace(/\//g, '-')
}

export function localDateTime(value: string | null | undefined): string {
  if (!value) return ''
  const date=new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  const pad=(n:number)=>String(n).padStart(2,'0')
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function isoDateTime(value:string):string {
  return value ? new Date(value).toISOString() : ''
}

export function formatTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat('zh-CN').format(value)
}

export function observationLabel(key: string): string {
  const map: Record<string, string> = {
    guardrail_state: '防护状态',
    guardrail_height_m: '防护高度',
    worker_present: '人员在场',
    drop_height_m: '坠落高度',
    boundary_is_exposed: '边界暴露',
    guardrail_fixed: '固定',
    guardrail_continuous: '连续',
    ppe_confirmed: 'PPE',
    simulated: '模拟',
  }
  return map[key] || key
}

export function observationValue(value: any): string {
  if (value === null || value === undefined) return 'unknown'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return `${value}`
  if (value === 'absent') return 'absent（缺失）'
  if (value === 'present') return 'present（存在）'
  if (value === 'unknown') return 'unknown'
  return String(value)
}

export function toneForResult(result: string): string {
  if (result === 'risk_candidate') return 'red'
  if (result === 'no_issue_in_checked_items' || result === 'pass_in_demo_scope') return 'green'
  if (result === 'needs_evidence' || result === 'unknown') return 'amber'
  return 'slate'
}

export function isTerminal(status: CaseStatus | string): boolean {
  return ['closed', 'rejected'].includes(status)
}

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value))
}

export function debounce<T extends (...args: any[]) => void>(fn: T, wait = 280) {
  let timer: number | undefined
  return (...args: Parameters<T>) => {
    window.clearTimeout(timer)
    timer = window.setTimeout(() => fn(...args), wait)
  }
}

export function demoTime(base: string, minutes: number): string {
  const date = new Date(base)
  if (Number.isNaN(date.getTime())) return base
  date.setMinutes(date.getMinutes() + minutes)
  const offset = -date.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const pad = (value: number) => String(Math.abs(value)).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${sign}${pad(Math.floor(Math.abs(offset) / 60))}:${pad(Math.abs(offset) % 60)}`
}
