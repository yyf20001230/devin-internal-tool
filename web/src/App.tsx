import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ActionSpec, IntegrationEntry, Me, Rec, TileSpec, ToolSpec, User } from './api'
import { api, fmt, getUser, setUser } from './api'
import { Cell, isNumeric } from './Cell'
import { Dashboard } from './Dashboard'
import { RecordPane } from './RecordPane'

const ICONS: Record<string, string> = { kyc: '🛡', refunds: '↩', flags: '⚑', chargebacks: '⚖' }

type Pending = { action: ActionSpec; record: Rec; comment: string }

export default function App() {
  const [users, setUsers] = useState<User[]>([])
  const [me, setMe] = useState<Me | null>(null)
  const [toolId, setToolId] = useState<string>(localStorage.getItem('tool') || '')
  const [tool, setTool] = useState<ToolSpec | null>(null)
  const [viewId, setViewId] = useState('')
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<Rec[]>([])
  const [tiles, setTiles] = useState<TileSpec[]>([])
  const [integrations, setIntegrations] = useState<IntegrationEntry[]>([])
  const [sel, setSel] = useState<Rec | null>(null)
  const [paneOpen, setPaneOpen] = useState(false)
  const [tab, setTab] = useState<'dashboard' | 'grid'>('dashboard')
  const [pending, setPending] = useState<Pending | null>(null)
  const [toastMsg, setToastMsg] = useState<{ msg: string; err: boolean } | null>(null)

  const toast = useCallback((msg: string, err = false) => {
    setToastMsg({ msg, err }); setTimeout(() => setToastMsg(null), 2500)
  }, [])

  useEffect(() => { api.users().then(setUsers) }, [])

  const loadMe = useCallback(async () => {
    const m = await api.me(); setMe(m)
    if (!m.tools.find(t => t.id === toolId)) setToolId(m.tools[0]?.id ?? '')
  }, [toolId])
  useEffect(() => { loadMe() }, [loadMe])

  useEffect(() => {
    if (!toolId) { setTool(null); return }
    localStorage.setItem('tool', toolId)
    api.tool(toolId).then(t => {
      setTool(t); setViewId(t.views[0]?.id ?? ''); setSel(null); setPaneOpen(false)
      setTab(t.dashboard.length ? 'dashboard' : 'grid')
    }).catch(e => toast(e.message, true))
  }, [toolId, toast])

  const refresh = useCallback(async () => {
    if (!tool || !viewId) return
    const [r, d, i] = await Promise.all([api.records(tool.id, viewId, q), api.dashboard(tool.id), api.integrations(tool.id)])
    setRows(r); setTiles(d); setIntegrations(i)
    if (sel) setSel(r.find(x => x.id === sel.id) ?? sel)
  }, [tool, viewId, q, sel])
  useEffect(() => { refresh() }, [tool, viewId, q]) // eslint-disable-line react-hooks/exhaustive-deps

  const view = tool?.views.find(v => v.id === viewId)
  const columns = useMemo(() => tool && view ? view.columns.map(c => tool.fields.find(f => f.name === c)!) : [], [tool, view])

  function switchUser(id: string) { setUser(id); setSel(null); setPaneOpen(false); loadMe() }

  function actionEnabled(a: ActionSpec) {
    if (!a.allowed || !sel) return false
    return Object.entries(a.only_when).every(([k, cond]) => {
      const v = sel[k]
      if (Array.isArray(cond)) return cond.includes(v)
      if (cond && typeof cond === 'object') {
        return Object.entries(cond as Record<string, unknown>).every(([op, x]) => {
          const n = Number(v), m = Number(x)
          return op === 'lt' ? n < m : op === 'lte' ? n <= m : op === 'gt' ? n > m : op === 'gte' ? n >= m : op === 'ne' ? v !== x : v === x
        })
      }
      return typeof cond === 'boolean' ? Boolean(v) === cond : v === cond
    })
  }

  function startAction(a: ActionSpec) {
    if (!sel) return
    if (a.requires_comment || a.confirm) setPending({ action: a, record: sel, comment: '' })
    else runAction(a, sel, null)
  }

  async function runAction(a: ActionSpec, r: Rec, comment: string | null) {
    if (!tool) return
    try {
      const updated = await api.action(tool.id, a.id, r.id, comment)
      setSel(updated); setPending(null)
      toast(`${a.label} → ${String(updated[tool.title_field])}${a.webhook ? ' · webhook queued' : ''}`)
      refresh()
    } catch (e) { toast((e as Error).message, true) }
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

  const initials = me?.user.name.split(' ').map(s => s[0]).join('') ?? ''

  return (
    <div className="shell">
      <header className="appbar">
        <div className="brand"><span className="waffle">⋮⋮⋮</span><b>Internal Tools</b><span style={{ opacity: .8 }}>| {tool?.app ?? 'Home'}</span></div>
        <div className="search">🔍<input placeholder="Search" value={q} onChange={e => setQ(e.target.value)} /></div>
        <div className="right">
          <span className="env">Environment: <b>Prototype (Devin)</b></span>
          <span title="Sign in as – stands in for Entra ID">
            <select value={getUser()} onChange={e => switchUser(e.target.value)}>
              {users.map(u => <option key={u.id} value={u.id}>{u.name} · {u.roles.join(', ')}</option>)}
            </select>
          </span>
          <span className="avatar">{initials}</span>
        </div>
      </header>

      <div className="body">
        <nav className="nav">
          {Object.entries(apps).map(([app, ts]) => (
            <div key={app}>
              <div className="group">{app}</div>
              {ts.map(t => (
                <a key={t.id} className={t.id === toolId ? 'active' : ''} onClick={() => setToolId(t.id)}>
                  <span className="ico">{ICONS[t.id] ?? '▦'}</span>{t.name}
                </a>
              ))}
            </div>
          ))}
          {me && me.tools.length === 0 && <div className="foot">No tools are shared with your role.</div>}
          <div className="foot">
            Every tool here is one YAML file in <code>tools/</code>.<br />
            Roles: {me?.user.roles.join(', ')}
          </div>
        </nav>

        <main className="main">
          <div className="cmdbar">
            <button disabled={!tool?.can.create} onClick={() => { setSel(null); setPaneOpen(true) }}><span className="ico">＋</span>New</button>
            <button onClick={refresh}><span className="ico">↻</span>Refresh</button>
            <div className="sep" />
            {tool?.actions.map(a => (
              <button key={a.id} className={a.destructive ? 'danger' : ''} disabled={!actionEnabled(a)} onClick={() => startAction(a)}
                title={!a.allowed ? `Requires role: ${a.roles.join(' or ')}` : !sel ? 'Select a row first' : ''}>
                <span className="ico">{a.destructive ? '⊘' : a.webhook ? '⚡' : '✓'}</span>{a.label}
              </button>
            ))}
            <div className="spacer" />
            <button disabled={!tool?.can.export} onClick={exportCsv} title={tool?.can.export ? '' : 'Export privilege not granted to your role'}>
              <span className="ico">⇩</span>Export to Excel
            </button>
          </div>

          {tool && (
            <div className="titlebar">
              <h1>
                <span className="chev">▾</span>
                <select value={viewId} onChange={e => { setViewId(e.target.value); setSel(null) }}>
                  {tool.views.map(v => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </h1>
              <span className="desc">{tool.description}</span>
              <div className="spacer" />
              <div className="tabs">
                <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => setTab('dashboard')}>Dashboard + grid</button>
                <button className={tab === 'grid' ? 'active' : ''} onClick={() => setTab('grid')}>Grid only</button>
              </div>
            </div>
          )}

          <div className={`content ${paneOpen ? '' : 'no-pane'}`}>
            <div>
              {tool && tab === 'dashboard' && <Dashboard tiles={tiles} />}
              {tool?.id === 'flags' && (tiles.find(t => t.title.startsWith('PROD on without'))?.value ?? 0) > 0 && (
                <div className="banner">⚠ {tiles.find(t => t.title.startsWith('PROD on without'))?.value} flag(s) are on in PROD without an approved change request. Policy requires a CR before PROD enablement.</div>
              )}
              <div className="grid-wrap">
                <div className="grid-head">
                  <input className="filter" placeholder="Filter by keyword" value={q} onChange={e => setQ(e.target.value)} />
                  {view?.mine && <span className="pill purple">My records</span>}
                  <span className="count">{rows.length} rows</span>
                </div>
                <table>
                  <thead><tr>{columns.map(f => <th key={f.name} style={f.width ? { width: f.width } : {}}>{f.label}{f.masked ? ' 🔒' : ''}</th>)}</tr></thead>
                  <tbody>
                    {rows.map(r => (
                      <tr key={r.id} className={`row ${sel?.id === r.id ? 'sel' : ''}`}
                        onClick={() => setSel(r)} onDoubleClick={() => { setSel(r); setPaneOpen(true) }}>
                        {columns.map(f => <td key={f.name} className={isNumeric(f) ? 'num' : ''}><Cell f={f} r={r} isTitle={f.name === tool?.title_field} /></td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {rows.length === 0 && <div className="empty">No records in this view.</div>}
              </div>
              {integrations.length > 0 && (
                <div className="tile" style={{ marginTop: 12 }}>
                  <div className="h"><span>Outbound integrations (simulated Power Automate)</span></div>
                  {integrations.slice(0, 5).map(i => (
                    <div key={i.id} style={{ fontSize: 12, padding: '3px 0' }}>
                      <span className="pill green">sent</span> {fmt.dt(i.ts)} · <code>{i.webhook.replace('https://hooks.internal', '')}</code> · {String(i.payload.action)} on <b>{String(i.payload.title)}</b> by {String(i.payload.by)}
                    </div>
                  ))}
                </div>
              )}
              {sel && !paneOpen && <div className="sub" style={{ color: '#8b8b90', marginTop: 8 }}>Selected {String(sel[tool!.title_field])} — double-click to open, or use the command bar.</div>}
            </div>
            {paneOpen && tool && (
              <RecordPane tool={tool} record={sel} toast={toast} onClose={() => setPaneOpen(false)}
                onSaved={r => { setSel(r); refresh() }} />
            )}
          </div>
        </main>
      </div>

      {pending && (
        <div className="modal-bg" onClick={() => setPending(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h3>{pending.action.label} — {String(pending.record[tool!.title_field])}</h3>
            {pending.action.confirm && <div>{pending.action.confirm}</div>}
            {pending.action.requires_comment && (
              <textarea placeholder="Comment (required, written to the audit trail)" value={pending.comment}
                onChange={e => setPending({ ...pending, comment: e.target.value })} />
            )}
            <div className="acts">
              <button className="btn secondary" onClick={() => setPending(null)}>Cancel</button>
              <button className="btn" disabled={pending.action.requires_comment && !pending.comment.trim()}
                onClick={() => runAction(pending.action, pending.record, pending.comment || null)}>{pending.action.label}</button>
            </div>
          </div>
        </div>
      )}
      {toastMsg && <div className={`toast ${toastMsg.err ? 'err' : ''}`}>{toastMsg.msg}</div>}
    </div>
  )
}
