import {reactive} from 'vue'
export const accessState=reactive({required:false})
export class ApiError extends Error {
  status: number
  code: string
  details: any

  constructor(status: number, code: string, message: string, details: any = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

const BASE = '/api'

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    if(response.status===401)accessState.required=true
    let payload: any = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    const error = payload?.error
    throw new ApiError(
      response.status,
      error?.code || `http_${response.status}`,
      error?.message || `请求失败（HTTP ${response.status}）`,
      error?.details ?? payload,
    )
  }
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return (await response.json()) as T
  }
  return (await response.text()) as unknown as T
}

export const api = {
  async signIn(token:string):Promise<void>{
    const response=await fetch(`${BASE}/access/session`,{headers:{Authorization:'Bearer '+token},credentials:'same-origin'})
    if(!response.ok){const value=await response.json();throw new Error(value.error?.message || '访问令牌无效')}
    accessState.required=false
  },
  get<T>(path: string): Promise<T> {
    return request<T>(path)
  },
  post<T>(path: string, body?: any): Promise<T> {
    return request<T>(path, {
      method: 'POST',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  },
  postForm<T>(path: string, body: FormData): Promise<T> {
    return request<T>(path, { method: 'POST', body })
  },
  put<T>(path: string, body: any): Promise<T> {
    return request<T>(path, {method:'PUT',body:JSON.stringify(body)})
  },
  async download(path: string, filename: string): Promise<void> {
    const response = await fetch(`${BASE}${path}`)
    if (!response.ok) {
      throw new ApiError(response.status, 'download_failed', '导出失败')
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  },
}

export function apiFile(path: string): string {
  return `${BASE}${path}`
}
