import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AIStatus, ActionSpec, AutoReviewResult, FieldSpec, IntegrationEntry, Me, QueryResult, Rec, TileSpec, ToolSpec, User } from './api'
import { ApiError, api, fmt, getUser, signIn, signOut } from './api'
import { Cell, isNumeric } from './Cell'
import { Dashboard } from './Dashboard'
import { Icon, actionIcon } from './Icon'
import { PolicyReport } from './PolicyReport'
import { RecordPane } from './RecordPane'

type Pending = { action: ActionSpec; record: Rec; comment: string }
type Sort = { field: string; dir: 'asc' | 'desc' } | null

const APP_BLURB: Record<string, string> = {
  'Compliance Operations': 'KYC review, sanctions screening and onboarding decisions.',
  'Payments Operations': 'Refund approvals, holds and payout release.',
  'Release Control': 'Feature-flag changes gated by change requests.',
}

function matches(cond: unknown, v: unknown): boolean {
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

function compare(f: FieldSpec | undefined, a: unknown, b: unknown): number {
  if (a == null || a === '') return 1
  if (b == null || b === '') return -1
  if (f?.type === 'choice' && f.options.length) return f.options.indexOf(String(a)) - f.options.indexOf(String(b))
  if (f && (isNumeric(f) || f.type === 'boolean')) return Number(a) - Number(b)
  if (f && (f.type === 'date' || f.type === 'datetime')) return new Date(String(a)).getTime() - new Date(String(b)).getTime()
  return String(a).localeCompare(String(b))
}

// ---- sign-in page (stands in for Entra ID / OIDC) -----------------------------------------
function SignIn({ users, onSignIn }: { users: User[]; onSignIn: (id: string) => void }) {
  return (
    <div className="signin">
      <div className="signin-card">
        <div className="signin-brand"><Icon name="grid" size={20} /><b>Internal Tools</b></div>
        <h2>Sign in</h2>
        <p className="sub">Single sign-on would normally happen here. Pick a demo identity — each one only sees the boards its roles grant.</p>
        <div className="signin-list">
          {users.map(u => (
            <button key={u.id} className="signin-user" onClick={() => onSignIn(u.id)}>
              <span className="avatar">{u.name.split(' ').map(s => s[0]).join('').slice(0, 2)}</span>
              <span className="who"><b>{u.name}</b><span className="sub">{u.title || u.roles.join(', ')}</span></span>
              <Icon name="login" className="dim" />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [users, setUsers] = useState<User[]>([])
  const [me, setMe] = useState<Me | null>(null)
  const [authed, setAuthed] = useState(Boolean(getUser()))
  const [toolId, setToolId] = useState<string>(localStorage.getItem('tool') || '')
  const [tool, setTool] = useState<ToolSpec | null>(null)
  const [viewId, setViewId] = useState('')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<Rec[]>([])
  const [tiles, setTiles] = useState<TileSpec[]>([])
  const [integrations, setIntegrations] = useState<IntegrationEntry[]>([])
  const [sel, setSel] = useState<Rec | null>(null)
  const [paneOpen, setPaneOpen] = useState(false)
  const [pending, setPending] = useState<Pending | null>(null)
  const [toastMsg, setToastMsg] = useState<{ msg: string; err: boolean } | null>(null)
  const [sort, setSort] = useState<Sort>(null)
  const [menu, setMenu] = useState(false)
  const [ask, setAsk] = useState('')
  const [asking, setAsking] = useState(false)
  const [nl, setNl] = useState<QueryResult | null>(null)
  const [ai, setAi] = useState<AIStatus | null>(null)
  const [autoResult, setAutoResult] = useState<AutoReviewResult | null>(null)
  const [autoRunning, setAutoRunning] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  const toast = useCallback((msg: string, err = false) => {
    setToastMsg({ msg, err }); setTimeout(() => setToastMsg(null), 3000)
  }, [])

  useEffect(() => { api.users().then(setUsers) }, [])

  const doSignOut = useCallback(() => {
    signOut(); setAuthed(false); setMe(null); setTool(null); setToolId(''); setRows([]); setSel(null); setPaneOpen(false); setMenu(false)
  }, [])

  const loadMe = useCallback(async () => {
    if (!getUser()) return
    try {
      const m = await api.me(); setMe(m)
      if (!m.tools.find(t => t.id === toolId)) setToolId(m.tools[0]?.id ?? '')
      api.aiStatus().then(setAi).catch(() => setAi(null))
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) doSignOut()
    }
  }, [toolId, doSignOut])
  useEffect(() => { if (authed) loadMe() }, [authed, loadMe])

  useEffect(() => {
    const close = (e: MouseEvent) => { if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenu(false) }
    document.addEventListener('mousedown', close); return () => document.removeEventListener('mousedown', close)
  }, [])

  useEffect(() => {
    if (!toolId || !authed) { setTool(null); return }
    localStorage.setItem('tool', toolId)
    api.tool(toolId).then(t => {
      setTool(t); setViewId(t.views[0]?.id ?? ''); setSel(null); setPaneOpen(false); setSort(null); setNl(null); setAsk(''); setAutoResult(null)
    }).catch(e => toast(e.message, true))
  }, [toolId, authed, toast])

  const refresh = useCallback(async () => {
    if (!tool || !viewId) return
    const [r, d, i] = await Promise.all([api.records(tool.id, viewId, q), api.dashboard(tool.id), api.integrations(tool.id)])
    setRows(r); setTiles(d); setIntegrations(i)
    if (sel) {
      const still = r.find(x => x.id === sel.id)
      if (still) setSel(still)
      else if (!paneOpen) setSel(null)
    }
    if (nl && ask.trim()) api.query(tool.id, ask, viewId).then(setNl).catch(() => setNl(null))
  }, [tool, viewId, q, sel, paneOpen, nl, ask])
  useEffect(() => { refresh() }, [tool, viewId, q]) // eslint-disable-line react-hooks/exhaustive-deps

  const view = tool?.views.find(v => v.id === viewId)
  const columns = useMemo(() => tool && view ? view.columns.map(c => tool.fields.find(f => f.name === c)!) : [], [tool, view])

  const shown = useMemo(() => {
    const base = nl ? nl.rows : rows
    if (!sort) return base
    const f = tool?.fields.find(x => x.name === sort.field)
    const out = [...base].sort((a, b) => compare(f, a[sort.field], b[sort.field]))
    return sort.dir === 'desc' ? out.reverse() : out
  }, [rows, nl, sort, tool])

  const defaultSort = useMemo<Sort>(() => {
    const s = nl?.sort ?? view?.sort
    if (!s) return null
    const [field, dir] = s.split(' ')
    return { field, dir: dir?.toLowerCase() === 'desc' ? 'desc' : 'asc' }
  }, [view, nl])
  const activeSort = sort ?? defaultSort

  function toggleSort(f: FieldSpec) {
    if (f.masked) return
    setSort(s => {
      const cur = s ?? defaultSort
      if (cur?.field === f.name) return { field: f.name, dir: cur.dir === 'desc' ? 'asc' : 'desc' }
      return { field: f.name, dir: isNumeric(f) || f.type === 'choice' || f.type === 'boolean' ? 'desc' : 'asc' }
    })
  }

  const actionEnabled = useCallback((a: ActionSpec, r: Rec) =>
    a.allowed && Object.entries(a.only_when).every(([k, cond]) => matches(cond, r[k])), [])

  function startAction(a: ActionSpec, r: Rec) {
    if (a.requires_comment || a.confirm) setPending({ action: a, record: r, comment: '' })
    else runAction(a, r, null)
  }

  async function runAction(a: ActionSpec, r: Rec, comment: string | null) {
    if (!tool) return
    try {
      const updated = await api.action(tool.id, a.id, r.id, comment)
      setPending(null)
      const leaves = view && !Object.entries(view.filter).every(([k, cond]) => matches(cond, updated[k]))
      toast(`${a.label} → ${String(updated[tool.title_field])}${leaves ? ' · left this queue' : ''}${a.webhook ? ' · webhook queued' : ''}`)
      if (leaves) { setPaneOpen(false); setSel(null) } else setSel(updated)
      refresh()
    } catch (e) { toast((e as Error).message, true) }
  }

  async function runAutoReview() {
    if (!tool || !viewId) return
    setAutoRunning(true)
    try {
      const r = await api.autoReview(tool.id, viewId); setAutoResult(r)
      toast(`Devin AI: ${r.cleared.length} cleared, ${r.flagged.length} escalated, ${r.review.length} left for you`)
      refresh()
    } catch (e) { toast((e as Error).message, true) } finally { setAutoRunning(false) }
  }

  async function runAsk(e?: React.FormEvent) {
    e?.preventDefault()
    if (!tool || !ask.trim()) { setNl(null); return }
    setAsking(true)
    try { setNl(await api.query(tool.id, ask, viewId)); setSort(null) }
    catch (err) { toast((err as Error).message, true) } finally { setAsking(false) }
  }

  async function exportCsv() {
    if (!tool) return
    try {
      const csv = await api.exportCsv(tool.id, viewId)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = `${tool.id}-${viewId}.csv`; a.click()
      toast('Export logged to audit trail')
    } catch (e) { toast((e as Error).message, true) }
  }

  const apps = useMemo(() => {
    const g: Record<string, Me['tools']> = {}
    me?.tools.forEach(t => { (g[t.app] ??= []).push(t) })
    return g
  }, [me])

  if (!authed) return <SignIn users={users} onSignIn={id => { signIn(id); setAuthed(true) }} />

  const initials = me?.user.name.split(' ').map(s => s[0]).join('').slice(0, 2) ?? ''
  const prodWarn = tool?.id === 'flags' ? tiles.find(t => t.title.startsWith('PROD on without'))?.value ?? 0 : 0

  return (
    <div className="shell">
      <header className="appbar">
        <div className="brand"><Icon name="grid" size={18} /><b>Internal Tools</b>{tool && <span className="crumb">/ {tool.app}</span>}</div>
        <div className="search"><Icon name="search" size={14} /><input placeholder="Search this board" value={q} onChange={e => setQ(e.target.value)} /></div>
        <div className="right" ref={menuRef}>
          <span className="env">Prototype</span>
          <button className="avatar-btn" onClick={() => setMenu(m => !m)} title={me?.user.name}><span className="avatar">{initials}</span></button>
          {menu && me && (
            <div className="menu">
              <div className="menu-head">
                <span className="avatar lg">{initials}</span>
                <div><b>{me.user.name}</b><div className="sub">{me.user.title}</div></div>
              </div>
              <div className="menu-roles">{me.user.roles.map(r => <span key={r} className="pill" title={me.roles[r]}>{r}</span>)}</div>
              <div className="menu-sec">Boards</div>
              {Object.keys(apps).map(a => <div key={a} className="menu-item static"><Icon name="check" size={13} className="green" />{a}</div>)}
              {ai && <><div className="menu-sec">Embedded AI</div>
                <div className="menu-item static"><Icon name="sparkle" size={13} />{ai.provider === 'openai' ? `OpenAI ${ai.model}` : 'Offline rules engine'}{ai.last_error ? ' · falling back' : ''}</div></>}
              <div className="menu-div" />
              <button className="menu-item" onClick={doSignOut}><Icon name="logout" size={14} />Sign out</button>
            </div>
          )}
        </div>
      </header>

      <div className="body">
        <nav className="nav">
          {Object.entries(apps).map(([app, ts]) => (
            <div key={app}>
              <div className="group">{app}</div>
              <div className="group-blurb">{APP_BLURB[app]}</div>
              {ts.map(t => (
                <a key={t.id} className={t.id === toolId ? 'active' : ''} onClick={() => setToolId(t.id)}>
                  <Icon name={t.icon} />{t.name}
                </a>
              ))}
            </div>
          ))}
          {me && me.tools.length === 0 && <div className="foot">No boards are shared with your role.</div>}
        </nav>

        <main className="main">
          {tool && (
            <div className="titlebar">
              <h1>
                <Icon name={tool.icon} size={18} />
                {tool.name}
              </h1>
              <span className="desc">{tool.description}</span>
            </div>
          )}

          <div className="cmdbar">
            <div className="spacer" />
            {tool?.auto_review && (
              <button className="btn ai-btn" disabled={autoRunning} onClick={runAutoReview} title={`Run ${tool.auto_review.policy.replace(/_/g, ' ')} checks over this queue; clears or escalates what the policy settles, as the Devin AI service account`}>
                <Icon name="sparkle" />{autoRunning ? 'Reviewing…' : 'Run policy checks'}
              </button>
            )}
            <button className="btn secondary" disabled={!tool?.can.create} onClick={() => { setSel(null); setPaneOpen(true) }}><Icon name="plus" />New</button>
            <button className="btn secondary" onClick={refresh}><Icon name="refresh" />Refresh</button>
            <button className="btn secondary" disabled={!tool?.can.export} onClick={exportCsv} title={tool?.can.export ? 'Logged to the audit trail' : 'Export privilege not granted to your role'}>
              <Icon name="download" />Export
            </button>
          </div>

          <div className={`content ${paneOpen ? '' : 'no-pane'}`}>
            <div>
              {tool && <Dashboard tiles={tiles} />}
              {prodWarn > 0 && (
                <div className="banner"><Icon name="alert" />{prodWarn} flag(s) are on in PROD without an approved change request. Policy requires a CR before PROD enablement.</div>
              )}
              {autoResult && tool && (
                <PolicyReport result={autoResult} rows={rows} onClose={() => setAutoResult(null)}
                  onOpen={async (r, id) => {
                    try { setSel(r ?? await api.record(tool.id, id)); setPaneOpen(true) }
                    catch (e) { toast((e as Error).message, true) }
                  }} />
              )}
              <div className="grid-wrap">
                <div className="views">
                  {tool?.views.map(v => (
                    <button key={v.id} className={`view ${v.id === viewId ? 'active' : ''}`} onClick={() => { setViewId(v.id); setSel(null); setSort(null); setNl(null); setAsk(''); setAutoResult(null) }}>
                      {v.name}
                    </button>
                  ))}
                </div>
                <form className="grid-head" onSubmit={runAsk}>
                  <div className={`ask ${nl ? 'on' : ''}`}>
                    <Icon name="sparkle" size={14} />
                    <input placeholder={tool?.id === 'refunds' ? 'Ask: refunds over 500 in the last 7 days, largest first' : tool?.id === 'kyc' ? 'Ask: high risk cases missing proof of address' : 'Ask in plain English'}
                      value={ask} onChange={e => setAsk(e.target.value)} />
                    {nl && <button type="button" className="iconbtn" title="Clear" onClick={() => { setNl(null); setAsk(''); setSort(null) }}><Icon name="x" size={13} /></button>}
                    <button type="submit" className="btn small" disabled={asking || !ask.trim()}>{asking ? '…' : 'Ask'}</button>
                  </div>
                  {view?.mine && <span className="pill purple">My records</span>}
                  <span className="count">{shown.length} {shown.length === 1 ? 'row' : 'rows'}</span>
                </form>
                {nl && (
                  <div className="nl-explain">
                    <Icon name="info" size={13} />
                    <span>Filter: <b>{nl.explanation}</b> · compiled to <code>{JSON.stringify(nl.filter)}</code>{nl.sort ? <> · sort <code>{nl.sort}</code></> : null} · applied on top of “{view?.name}” with your column permissions · {nl.source === 'openai' ? 'LLM' : 'rules engine'}</span>
                  </div>
                )}
                <table>
                  <thead><tr>
                    {columns.map(f => {
                      const on = activeSort?.field === f.name
                      return (
                        <th key={f.name} style={f.width ? { width: f.width } : {}} className={`${f.masked ? '' : 'sortable'} ${on ? 'sorted' : ''}`}
                          onClick={() => toggleSort(f)} title={f.masked ? 'Hidden by column-level security' : `Sort by ${f.label}`}>
                          <span>{f.label}</span>
                          {f.masked ? <Icon name="lock" size={11} className="dim" /> : <Icon name={on ? (activeSort!.dir === 'desc' ? 'sortDesc' : 'sortAsc') : 'sort'} size={12} className={on ? '' : 'dim'} />}
                        </th>
                      )
                    })}
                  </tr></thead>
                  <tbody>
                    {shown.map(r => (
                      <tr key={r.id} className={`row ${sel?.id === r.id ? 'sel' : ''}`} onClick={() => { setSel(r); setPaneOpen(true) }}>
                        {columns.map(f => <td key={f.name} className={isNumeric(f) ? 'num' : ''}><Cell f={f} r={r} isTitle={f.name === tool?.title_field} /></td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {shown.length === 0 && <div className="empty">{nl ? 'Nothing matches that question in this view.' : 'Queue is clear.'}</div>}
              </div>
              {integrations.length > 0 && (
                <div className="tile" style={{ marginTop: 12 }}>
                  <div className="h"><span>Outbound integrations</span></div>
                  {integrations.slice(0, 5).map(i => (
                    <div key={i.id} style={{ fontSize: 12, padding: '3px 0' }}>
                      <span className="pill green">sent</span> {fmt.dt(i.ts)} · <code>{i.webhook.replace('https://hooks.internal', '')}</code> · {String(i.payload.action)} on <b>{String(i.payload.title)}</b> by {String(i.payload.by)}
                    </div>
                  ))}
                </div>
              )}
            </div>
            {paneOpen && tool && (
              <RecordPane tool={tool} record={sel} actions={tool.actions} actionEnabled={actionEnabled} onAction={startAction}
                toast={toast} onClose={() => setPaneOpen(false)} onSaved={r => { setSel(r); refresh() }} />
            )}
          </div>
        </main>
      </div>

      {pending && (
        <div className="modal-bg" onClick={() => setPending(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3><Icon name={actionIcon(pending.action.id, pending.action.icon, pending.action.destructive)} />{pending.action.label} — {String(pending.record[tool!.title_field])}</h3>
            {pending.action.confirm && <div>{pending.action.confirm}</div>}
            {pending.action.requires_comment && (
              <textarea placeholder="Comment (required, written to the audit trail)" value={pending.comment} autoFocus
                onChange={e => setPending({ ...pending, comment: e.target.value })} />
            )}
            <div className="acts">
              <button className="btn secondary" onClick={() => setPending(null)}>Cancel</button>
              <button className={`btn ${pending.action.destructive ? 'danger' : ''}`} disabled={pending.action.requires_comment && !pending.comment.trim()}
                onClick={() => runAction(pending.action, pending.record, pending.comment || null)}>{pending.action.label}</button>
            </div>
          </div>
        </div>
      )}
      {toastMsg && <div className={`toast ${toastMsg.err ? 'err' : ''}`}>{toastMsg.msg}</div>}
    </div>
  )
}
