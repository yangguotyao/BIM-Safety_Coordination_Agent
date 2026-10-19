import type { CaseStatus } from './types'
import { localeTag, t } from './i18n'

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

export function statusLabel(status: string): string {
  const key = `status.${status}`
  const text = t(key)
  return text === key ? status : text
}

export function statusTone(status: string): string {
  return STATUS_TONES[status] || 'slate'
}

export function resultLabel(result: string): string {
  const key = `result.${result}`
  const text = t(key)
  return text === key ? result : text
}

export function eventLabel(event: string): string {
  const key = `event.${event}`
  const text = t(key)
  return text === key ? event : text
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
  return new Intl.DateTimeFormat(localeTag(), {
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
  return new Intl.DateTimeFormat(localeTag(), {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat(localeTag()).format(value)
}

export function observationLabel(key: string): string {
  const dictKey = `observation.${key}`
  const text = t(dictKey)
  return text === dictKey ? key : text
}

export function observationValue(value: any): string {
  if (value === null || value === undefined) return 'unknown'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return `${value}`
  if (value === 'absent') return t('observation.absent')
  if (value === 'present') return t('observation.present')
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
