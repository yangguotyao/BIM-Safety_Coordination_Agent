import { reactive } from 'vue'
import { api } from './api'
import type { Health, Summary } from './types'

export interface Toast {
  id: number
  message: string
  kind: 'success' | 'error' | 'info' | 'warning'
}

let toastSeed = 0
export const actorId = sessionStorage.getItem('bim-demo-actor') || crypto.randomUUID?.() || `demo-${Date.now()}-${Math.random().toString(36).slice(2)}`
sessionStorage.setItem('bim-demo-actor', actorId)

export const store = reactive({
  health: null as Health | null,
  summary: null as Summary | null,
  booting: true,
  bootError: '',
  toasts: [] as Toast[],
  sidebarCollapsed: false,
  access: null as {label:string;role:string;mode:string}|null,
})

export async function bootstrap() {
  store.booting = true
  store.bootError = ''
  try {
    const [health, summary, access] = await Promise.all([
      api.get<Health>('/health'),
      api.get<Summary>('/summary'),
      api.get<{label:string;role:string;mode:string}>('/access/session'),
    ])
    store.health = health
    store.summary = summary
    store.access = access
  } catch (error: any) {
    store.bootError = error?.message || '无法连接后端服务'
  } finally {
    store.booting = false
  }
}

export async function refreshSummary() {
  try {
    store.summary = await api.get<Summary>('/summary')
  } catch {
    /* keep last known summary */
  }
}

export function toast(message: string, kind: Toast['kind'] = 'info', duration = 4200) {
  const id = ++toastSeed
  store.toasts.push({ id, message, kind })
  window.setTimeout(() => dismissToast(id), duration)
}

export function dismissToast(id: number) {
  const index = store.toasts.findIndex((item) => item.id === id)
  if (index >= 0) store.toasts.splice(index, 1)
}

export function errorMessage(error: any): string {
  if (!error) return '未知错误'
  if (error.code && error.message) return `[${error.code}] ${error.message}`
  return error.message || String(error)
}
