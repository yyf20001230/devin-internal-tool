export type FieldType = 'text' | 'multiline' | 'number' | 'money' | 'boolean' | 'choice' | 'date' | 'datetime' | 'percent'
export type Filter = Record<string, unknown>

export interface FieldSpec {
  name: string; label: string; type: FieldType; required: boolean; options: string[]
  default: unknown; visible_to: string[] | null; mask: 'full' | 'last4'; readonly: boolean; width: number | null
  computed: boolean; masked: boolean
}
export interface ViewSpec { id: string; name: string; filter: Filter; columns: string[]; sort: string | null; mine: boolean }
export interface ActionSpec {
  id: string; label: string; roles: string[]; set: Record<string, unknown>; only_when: Filter
  requires_comment: boolean; confirm: string | null; webhook: string | null; destructive: boolean; icon: string | null
  decision: 'approve' | 'reject' | 'info' | null; allowed: boolean
}

// Client-side mirror of the server's filter evaluation, used for view membership and action guards.
export function matches(cond: unknown, v: unknown): boolean {
  if (Array.isArray(cond)) return cond.includes(v)
  if (cond && typeof cond === 'object') {
    return Object.entries(cond as Record<string, unknown>).every(([op, x]) => {
      if (typeof x === 'string' && x.startsWith('now')) {
        const m = /^now([+-]\d+)([hdm])$/.exec(x)
        const ms = m ? Number(m[1]) * { h: 36e5, d: 864e5, m: 6e4 }[m[2] as 'h' | 'd' | 'm'] : 0
        const t = Date.now() + ms, tv = new Date(String(v)).getTime()
        return op === 'lt' ? tv < t : op === 'lte' ? tv <= t : op === 'gt' ? tv > t : op === 'gte' ? tv >= t : op === 'ne' ? tv !== t : tv === t
      }
      const n = Number(v), m = Number(x)
      return op === 'lt' ? n < m : op === 'lte' ? n <= m : op === 'gt' ? n > m : op === 'gte' ? n >= m : op === 'ne' ? v !== x : op === 'contains' ? String(v).includes(String(x)) : v === x
    })
  }
  return typeof cond === 'boolean' ? Boolean(v) === cond : v === cond
}

/** The record is in a state where this action applies (ignores the caller's role). */
export const stateAllows = (a: ActionSpec, r: Rec) => Object.entries(a.only_when).every(([k, cond]) => matches(cond, r[k]))
export interface CheckSpec { id: string; clause: string; title: string; on_fail: 'flag' | 'review' }
export interface AutoReviewSpec { policy: string; scope: Filter; clear_action: string | null; flag_action: string | null; actor: string }
export interface TileSpec {
  type: 'kpi' | 'group' | 'series'; title: string; metric: 'count' | 'sum' | 'avg'; field: string | null
  chart: 'bar' | 'donut' | 'hbar'; format: 'number' | 'money' | 'percent' | 'hours'
  value?: number; data?: { label: string; value: number }[]
}
export interface Can { read: boolean; create: boolean; update: boolean; export: boolean }
export interface ToolSpec {
  id: string; name: string; app: string; description: string; icon: string; entity: string; title_field: string
  assignee_field: string | null; fields: FieldSpec[]; views: ViewSpec[]; actions: ActionSpec[]; dashboard: TileSpec[]
  checks: CheckSpec[]; auto_review: AutoReviewSpec | null
  can: Can
}
export interface ToolSummary { id: string; name: string; app: string; description: string; icon: string; can: Can }
export interface User { id: string; name: string; roles: string[]; title: string }
export type Verdict = 'Cleared' | 'Needs review' | 'Flagged'
export interface CheckResult {
  id: string; clause: string; title: string; passed: boolean; outcome: 'pass' | 'review' | 'flag'; detail: string
  rule: Filter; evidence: Record<string, unknown>
  clause_title: string; clause_text: string; policy: string
}
export interface AIDecision {
  audit_id: number; action: string; actor: string; ts: string; reason: string | null
  before: Record<string, unknown>; after: Record<string, unknown>
}
export interface Review { verdict: Verdict; policy: string | null; checks: CheckResult[]; ai_decision: AIDecision | null }
export type AutoOutcome = 'cleared' | 'escalated' | 'review'
export interface AutoReviewItem {
  record_id: number; title: string; outcome: AutoOutcome; verdict: Verdict; action: string | null; reason: string
  checks: CheckResult[]
}
export interface AutoReviewResult {
  policy: string; policy_title: string; actor: string; view: string | null; items: AutoReviewItem[]
  cleared: string[]; flagged: string[]; review: string[]
}
export interface KnowledgeSummary { id: string; title: string; summary: string; clauses: number }
export interface Clause { code: string; title: string; text: string; doc: string }
export interface KnowledgeDoc { id: string; title: string; summary: string; body: string; clauses: Clause[] }
export interface Me { user: User; roles: Record<string, string>; tools: ToolSummary[] }
export interface Source { clause: string | null; title: string; doc: string; doc_title: string; text: string; score: number | null; why: string }
export interface Summary { headline: string; bullets: string[]; recommendation: string; source: string; sources: Source[] }
export interface Answer { answer: string; cites: string[]; sources: Source[]; source: string }
export interface KBStatus { backend: string; model: string; configured: string; chunks: number; docs: string[]; indexed_at: string | null; last_error: string | null }
export interface QueryResult { filter: Filter; sort: string | null; explanation: string; source: string; rows: Rec[] }
export interface AIStatus { provider: string; model: string | null; last_error: string | null }
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

// Prototype session: the signed-in user id travels as a header. Production swaps this for an OIDC/Entra ID token.
let currentUser = localStorage.getItem('user') || ''
export const getUser = () => currentUser
export const signIn = (u: string) => { currentUser = u; localStorage.setItem('user', u) }
export const signOut = () => { currentUser = ''; localStorage.removeItem('user'); localStorage.removeItem('tool') }

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
  record: (id: string, rid: number) => req<Rec>(`/api/tools/${id}/records/${rid}`),
  update: (id: string, rid: number, values: Record<string, unknown>) => req<Rec>(`/api/tools/${id}/records/${rid}`, { method: 'PATCH', body: JSON.stringify(values) }),
  action: (id: string, action: string, rid: number, comment: string | null) =>
    req<Rec>(`/api/tools/${id}/actions/${action}`, { method: 'POST', body: JSON.stringify({ record_id: rid, comment }) }),
  dashboard: (id: string) => req<TileSpec[]>(`/api/tools/${id}/dashboard`),
  audit: (id: string, rid?: number) => req<AuditEntry[]>(`/api/tools/${id}/audit${rid ? `?record_id=${rid}` : ''}`),
  integrations: (id: string) => req<IntegrationEntry[]>(`/api/tools/${id}/integrations`),
  exportCsv: (id: string, view: string) => req<string>(`/api/tools/${id}/records.csv?view=${view}`),
  review: (id: string, rid: number) => req<Review>(`/api/tools/${id}/records/${rid}/review`),
  autoReview: (id: string, view: string) => req<AutoReviewResult>(`/api/tools/${id}/auto-review?view=${view}`, { method: 'POST' }),
  aiDecisions: (id: string) => req<{ records: number[] }>(`/api/tools/${id}/ai-decisions`),
  aiReset: (id: string, rid: number | null, comment: string | null) =>
    req<{ reset: number[]; record?: Rec }>(`/api/tools/${id}/ai-reset`, { method: 'POST', body: JSON.stringify({ record_id: rid, comment }) }),
  knowledge: () => req<KnowledgeSummary[]>('/api/knowledge'),
  knowledgeDoc: (id: string) => req<KnowledgeDoc>(`/api/knowledge/${id}`),
  summary: (id: string, rid: number) => req<Summary>(`/api/tools/${id}/ai/summary`, { method: 'POST', body: JSON.stringify({ record_id: rid }) }),
  ask: (id: string, question: string, rid: number | null) =>
    req<Answer>(`/api/tools/${id}/ai/ask`, { method: 'POST', body: JSON.stringify({ question, record_id: rid }) }),
  kbStatus: () => req<KBStatus>('/api/knowledge/status'),
  query: (id: string, question: string, view: string) =>
    req<QueryResult>(`/api/tools/${id}/ai/query`, { method: 'POST', body: JSON.stringify({ question, view }) }),
  aiStatus: () => req<AIStatus>('/api/ai'),
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
