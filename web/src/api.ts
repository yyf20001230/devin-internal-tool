export type FieldType = 'text' | 'multiline' | 'number' | 'money' | 'boolean' | 'choice' | 'date' | 'datetime' | 'percent'
export type Filter = Record<string, unknown>

export interface FieldSpec {
  name: string; label: string; type: FieldType; required: boolean; options: string[]
  default: unknown; visible_to: string[] | null; mask: 'full' | 'last4'; readonly: boolean; width: number | null
  masked: boolean
}
export interface ViewSpec { id: string; name: string; filter: Filter; columns: string[]; sort: string | null; mine: boolean }
export interface ActionSpec {
  id: string; label: string; roles: string[]; set: Record<string, unknown>; only_when: Filter
  requires_comment: boolean; confirm: string | null; webhook: string | null; destructive: boolean; allowed: boolean
}
export interface TileSpec {
  type: 'kpi' | 'group' | 'series'; title: string; metric: 'count' | 'sum' | 'avg'; field: string | null
  chart: 'bar' | 'donut' | 'hbar'; format: 'number' | 'money' | 'percent' | 'hours'
  value?: number; data?: { label: string; value: number }[]
}
export interface Can { read: boolean; create: boolean; update: boolean; export: boolean }
export interface ToolSpec {
  id: string; name: string; app: string; description: string; entity: string; title_field: string
  assignee_field: string | null; fields: FieldSpec[]; views: ViewSpec[]; actions: ActionSpec[]; dashboard: TileSpec[]
  can: Can
}
export interface ToolSummary { id: string; name: string; app: string; description: string; can: Can }
export interface User { id: string; name: string; roles: string[] }
export interface Me { user: User; roles: Record<string, string>; tools: ToolSummary[] }
export type Rec = Record<string, unknown> & { id: number }
export interface AuditEntry {
  id: number; ts: string; record_id: number | null; user_id: string; action: string; comment: string | null
  before: Record<string, unknown> | null; after: Record<string, unknown> | null
}
export interface IntegrationEntry { id: number; ts: string; record_id: number; webhook: string; payload: Record<string, unknown> }

export class ApiError extends Error {
  status: number
  constructor(status: number, msg: string) { super(msg); this.status = status }
}

let currentUser = localStorage.getItem('user') || 'priya'
export const getUser = () => currentUser
export const setUser = (u: string) => { currentUser = u; localStorage.setItem('user', u) }

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', 'X-User': currentUser, ...(init.headers || {}) } })
  if (!r.ok) {
    let msg = r.statusText
    try { msg = (await r.json()).detail ?? msg } catch { /* ignore */ }
    throw new ApiError(r.status, msg)
  }
  if (r.headers.get('content-type')?.includes('text/plain')) return (await r.text()) as unknown as T
  return r.json()
}

export const api = {
  users: () => req<User[]>('/api/users'),
  me: () => req<Me>('/api/me'),
  tool: (id: string) => req<ToolSpec>(`/api/tools/${id}`),
  records: (id: string, view: string, q: string) => req<Rec[]>(`/api/tools/${id}/records?view=${view}&q=${encodeURIComponent(q)}`),
  create: (id: string, values: Record<string, unknown>) => req<Rec>(`/api/tools/${id}/records`, { method: 'POST', body: JSON.stringify(values) }),
  update: (id: string, rid: number, values: Record<string, unknown>) => req<Rec>(`/api/tools/${id}/records/${rid}`, { method: 'PATCH', body: JSON.stringify(values) }),
  action: (id: string, action: string, rid: number, comment: string | null) =>
    req<Rec>(`/api/tools/${id}/actions/${action}`, { method: 'POST', body: JSON.stringify({ record_id: rid, comment }) }),
  dashboard: (id: string) => req<TileSpec[]>(`/api/tools/${id}/dashboard`),
  audit: (id: string, rid?: number) => req<AuditEntry[]>(`/api/tools/${id}/audit${rid ? `?record_id=${rid}` : ''}`),
  integrations: (id: string) => req<IntegrationEntry[]>(`/api/tools/${id}/integrations`),
  exportCsv: (id: string, view: string) => req<string>(`/api/tools/${id}/records.csv?view=${view}`),
}

export const fmt = {
  money: (v: number, ccy = 'GBP') => new Intl.NumberFormat('en-GB', { style: 'currency', currency: ccy, maximumFractionDigits: v >= 1000 ? 0 : 2 }).format(v),
  num: (v: number) => new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 }).format(v),
  dt: (v: string) => { const d = new Date(v); return isNaN(+d) ? v : d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) },
  date: (v: string) => { const d = new Date(v); return isNaN(+d) ? v : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) },
  rel: (v: string) => {
    const ms = new Date(v).getTime() - Date.now(); const h = Math.round(Math.abs(ms) / 36e5)
    const s = h >= 48 ? `${Math.round(h / 24)}d` : `${h}h`
    return ms < 0 ? `${s} overdue` : `in ${s}`
  },
}
