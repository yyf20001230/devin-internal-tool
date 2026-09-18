import { useEffect, useState } from 'react'
import type { ActionSpec, Answer, AuditEntry, FieldSpec, Rec, Review, Source, Summary, ToolSpec } from './api'
import { api, fmt, stateAllows } from './api'
import { pillColour } from './Cell'
import { Icon, actionIcon } from './Icon'
import { Check } from './PolicyReport'

interface Props {
  tool: ToolSpec
  record: Rec | null   // null = new record
  actions: ActionSpec[]
  actionEnabled: (a: ActionSpec, r: Rec) => boolean
  onAction: (a: ActionSpec, r: Rec) => void
  onClose: () => void
  onSaved: (r: Rec) => void
  toast: (msg: string, err?: boolean) => void
}

function Input({ f, v, onChange, disabled }: { f: FieldSpec; v: unknown; onChange: (v: unknown) => void; disabled: boolean }) {
  const s = v == null ? '' : String(v)
  if (f.masked) return <div className="ro masked" title="Hidden by column-level security">{s || '••••••'}</div>
  switch (f.type) {
    case 'choice':
      return <select value={s} disabled={disabled} onChange={e => onChange(e.target.value)}>
        <option value="">—</option>{f.options.map(o => <option key={o}>{o}</option>)}
      </select>
    case 'boolean':
      return <select value={v ? '1' : '0'} disabled={disabled} onChange={e => onChange(e.target.value === '1')}>
        <option value="0">No</option><option value="1">Yes</option>
      </select>
    case 'multiline': return <textarea rows={3} value={s} disabled={disabled} onChange={e => onChange(e.target.value)} />
    case 'number': case 'money': case 'percent':
      return <input type="number" step="any" value={s} disabled={disabled} onChange={e => onChange(e.target.value)} />
    case 'date': return <input type="date" value={s} disabled={disabled} onChange={e => onChange(e.target.value)} />
    case 'datetime':
      return <input type="datetime-local" value={s.slice(0, 16)} disabled={disabled}
        onChange={e => onChange(e.target.value ? new Date(e.target.value).toISOString().slice(0, 19) + '+00:00' : '')} />
    default: return <input value={s} disabled={disabled} onChange={e => onChange(e.target.value)} />
  }
}

function Sources({ sources, cites }: { sources: Source[]; cites?: string[] }) {
  const [open, setOpen] = useState<string | null>(null)
  if (!sources.length) return null
  return (
    <div className="kb-sources">
      <div className="sub">From the knowledge base</div>
      <div className="kb-chips">
        {sources.map(s => {
          const key = s.clause ?? s.title
          const cited = cites?.includes(key)
          return (
            <button key={key} className={`kb-chip${open === key ? ' on' : ''}${cited ? ' cited' : ''}`}
              title={`${s.doc_title} · ${s.why}${s.score != null ? ` · similarity ${s.score.toFixed(2)}` : ''}`}
              onClick={() => setOpen(open === key ? null : key)}>
              {key}
            </button>
          )
        })}
      </div>
      {sources.filter(s => (s.clause ?? s.title) === open).map(s => (
        <div key={s.clause ?? s.title} className="clause-text">
          <b>{s.clause ? `${s.clause} ${s.title}` : s.title}</b>
          <div className="sub">{s.doc_title} · {s.why}{s.score != null ? ` · similarity ${s.score.toFixed(2)}` : ''}</div>
          <p>{s.text}</p>
        </div>
      ))}
    </div>
  )
}

function AskPolicy({ tool, record }: { tool: ToolSpec; record: Rec }) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [ans, setAns] = useState<Answer | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { setAns(null); setErr(''); setQ('') }, [record.id])

  async function ask() {
    if (!q.trim()) return
    setBusy(true); setErr('')
    try { setAns(await api.ask(tool.id, q, record.id)) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  return (
    <section className="ai">
      <div className="ai-head">
        <Icon name="search" />
        <span>Ask the policy</span>
        {ans && <span className="src" title={ans.source === 'openai' ? 'Answered by the configured LLM from retrieved clauses' : 'Extractive answer from retrieved clauses (LLM unavailable)'}>{ans.source === 'openai' ? 'LLM' : 'rules'}</span>}
      </div>
      <form className="ask-row" onSubmit={e => { e.preventDefault(); void ask() }}>
        <input value={q} placeholder="e.g. can I approve this without the missing document?" onChange={e => setQ(e.target.value)} disabled={busy} />
        <button className="btn small secondary" type="submit" disabled={busy || !q.trim()}>{busy ? '…' : 'Ask'}</button>
      </form>
      {err && <div className="err">{err}</div>}
      {ans && (
        <>
          <div className="ai-answer">{ans.answer}</div>
          <Sources sources={ans.sources} cites={ans.cites} />
        </>
      )}
    </section>
  )
}


type Tab = 'summary' | 'policy' | 'details'
const DECISIONS: { kind: NonNullable<ActionSpec['decision']>; cls: string }[] = [
  { kind: 'approve', cls: 'approve' }, { kind: 'reject', cls: 'danger' }, { kind: 'info', cls: 'secondary' },
]

// A boolean field becomes a switch when some action flips it on and/or off (e.g. uat/prod on flags).
// Which action runs is looked up from the actions' `set`, so the guards, confirm and comment rules still apply.
function Switches({ tool, actions, record, actionEnabled, onAction }: { tool: ToolSpec; actions: ActionSpec[]; record: Rec; actionEnabled: (a: ActionSpec, r: Rec) => boolean; onAction: (a: ActionSpec, r: Rec) => void }) {
  const rows = tool.fields.filter(f => f.type === 'boolean' && !f.computed).map(f => {
    const on = Boolean(record[f.name])
    const flip = actions.filter(a => !a.decision && typeof a.set[f.name] === 'boolean' && a.set[f.name] === !on)
    if (!actions.some(a => typeof a.set[f.name] === 'boolean')) return null
    const a = flip.find(x => actionEnabled(x, record)) ?? flip.find(x => x.allowed) ?? flip[0] ?? null
    const enabled = a !== null && actionEnabled(a, record)
    const why = !a ? `No action turns ${f.label} ${on ? 'off' : 'on'}` : enabled ? a.label : !a.allowed ? `${a.label}: requires role ${a.roles.join(' / ')}` : 'Not available in the current state'
    return { f, on, a, enabled, why }
  }).filter((s): s is NonNullable<typeof s> => s !== null)
  if (!rows.length) return null
  return (
    <div className="switches">
      {rows.map(s => (
        <button key={s.f.name} className="switch" disabled={!s.enabled} title={s.why} onClick={() => s.a && onAction(s.a, record)}>
          <span className={`tgl ${s.on ? 'on' : ''}`} />
          <span>{s.f.label}</span>
          <span className={`sub ${s.on ? 'green' : ''}`}>{s.on ? 'On' : 'Off'}</span>
        </button>
      ))}
    </div>
  )
}

function Decisions({ tool, actions, record, actionEnabled, onAction }: { tool: ToolSpec; actions: ActionSpec[]; record: Rec; actionEnabled: (a: ActionSpec, r: Rec) => boolean; onAction: (a: ActionSpec, r: Rec) => void }) {
  // A slot shows when the record is in a state where that decision applies. Policy (four-eyes role,
  // failing checks) does not grey the button - the action flow warns first and audits the override.
  // Only a role with no right to act at all (e.g. read-only) sees it disabled.
  const slots = DECISIONS.map(d => {
    const all = actions.filter(a => a.decision === d.kind && stateAllows(a, record))
    if (!all.length) return null
    const a = all.find(x => x.allowed) ?? all[0]
    const enabled = actionEnabled(a, record)
    const why = enabled ? '' : `Read-only for your role (${a.roles.join(' / ')} may decide)`
    return { ...d, a, enabled, why }
  }).filter((s): s is NonNullable<typeof s> => s !== null)
  const switched = new Set(actions.flatMap(a => Object.entries(a.set).filter(([k, v]) => typeof v === 'boolean' && tool.fields.some(f => f.name === k && f.type === 'boolean')).map(([k]) => k)))
  const others = actions.filter(a => !a.decision && a.allowed && actionEnabled(a, record) && !Object.keys(a.set).some(k => switched.has(k)))
  const switches = <Switches tool={tool} actions={actions} record={record} actionEnabled={actionEnabled} onAction={onAction} />
  if (!slots.length && !others.length && !switched.size) return <div className="sub">No actions available in the current state.</div>
  return (
    <div className="decisions">
      {switches}
      {slots.length > 0 && (
        <div className="decision-row">
          {slots.map(s => (
            <button key={s.kind} className={`btn ${s.cls}`} disabled={!s.enabled} title={s.why || s.a.label} onClick={() => onAction(s.a, record)}>
              <Icon name={actionIcon(s.a.id, s.a.icon, s.a.destructive)} />{s.a.label}
            </button>
          ))}
        </div>
      )}
      {others.length > 0 && (
        <div className="pane-actions">
          {others.map(a => (
            <button key={a.id} className={`btn small ${a.destructive ? 'danger' : 'secondary'}`} onClick={() => onAction(a, record)}>
              <Icon name={actionIcon(a.id, a.icon, a.destructive)} />{a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export function RecordPane({ tool, record, actions, actionEnabled, onAction, onClose, onSaved, toast }: Props) {
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [tab, setTab] = useState<Tab>('summary')
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [review, setReview] = useState<Review | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [resetting, setResetting] = useState(false)
  const isNew = record === null
  const hasPolicy = tool.checks.length > 0

  useEffect(() => {
    let live = true  // drop responses that land after the user has moved to another record
    setErr(''); setReview(null); setSummary(null)
    if (!hasPolicy) setTab(t => (t === 'policy' ? 'summary' : t))
    if (record) {
      setValues({ ...record }); setShowForm(false)
      api.audit(tool.id, record.id).then(a => live && setAudit(a)).catch(() => live && setAudit([]))
      if (hasPolicy) {
        api.review(tool.id, record.id).then(r => live && setReview(r)).catch(() => live && setReview(null))
        api.summary(tool.id, record.id).then(s => live && setSummary(s)).catch(() => live && setSummary(null))
      }
    } else {
      const d: Record<string, unknown> = {}
      tool.fields.forEach(f => { if (f.default != null) d[f.name] = f.default })
      setValues(d); setAudit([]); setShowForm(true)
    }
    return () => { live = false }
  }, [tool, record, hasPolicy])

  const dirty = record ? tool.fields.some(f => !f.masked && !f.computed && (values[f.name] ?? '') !== (record[f.name] ?? '')) : true
  const editable = isNew ? tool.can.create : tool.can.update

  async function save() {
    setSaving(true); setErr('')
    try {
      const payload: Record<string, unknown> = {}
      tool.fields.forEach(f => { if (!f.masked && !f.computed && f.name in values) payload[f.name] = values[f.name] })
      const r = record ? await api.update(tool.id, record.id, payload) : await api.create(tool.id, payload)
      toast(record ? 'Saved' : 'Created'); onSaved(r)
    } catch (e) { setErr((e as Error).message) } finally { setSaving(false) }
  }

  async function resetAI() {
    if (!record || !review?.ai_decision) return
    const note = window.prompt(`Undo Devin AI's '${review.ai_decision.action}' on this record? Optional reason:`, '')
    if (note === null) return
    setResetting(true)
    try {
      const res = await api.aiReset(tool.id, record.id, note || null)
      toast('AI decision reset'); if (res.record) onSaved(res.record)
    } catch (e) { toast((e as Error).message, true) } finally { setResetting(false) }
  }

  const title = record ? String(record[tool.title_field]) : `New ${tool.entity.replace('_', ' ')}`
  const status = record && typeof record.status === 'string' ? record.status : null
  const keyFields = tool.fields.filter(f => !f.computed && f.name !== tool.title_field && f.name !== 'status' && !['created_at', 'updated_at'].includes(f.name))

  return (
    <aside className="pane">
      <div className="pane-head">
        <div>
          <h3>{title}</h3>
          <div className="sub">
            {status && <span className={`pill ${pillColour(status)}`}>{status}</span>}
            {record && <span> Updated {fmt.dt(String(record.updated_at))}</span>}
            {!record && 'Fill in the required fields'}
          </div>
        </div>
        <button className="iconbtn" onClick={onClose} title="Close"><Icon name="x" /></button>
      </div>

      {record && (
        <div className="pane-tabs">
          {([['summary', 'Summary'], ['policy', 'Policy check'], ['details', 'Details']] as [Tab, string][])
            .filter(([id]) => id !== 'policy' || hasPolicy)
            .map(([id, label]) => (
              <button key={id} className={`view ${tab === id ? 'active' : ''}`} onClick={() => setTab(id)}>
                {label}
                {id === 'policy' && review && <span className={`dotted ${pillColour(review.verdict)}`}><span className="dot" /></span>}
              </button>
            ))}
        </div>
      )}

      {record && tab === 'summary' && actions.length > 0 && (
        <Decisions tool={tool} actions={actions} record={record} actionEnabled={actionEnabled} onAction={onAction} />
      )}

      {record && tab === 'summary' && review?.ai_decision && (
        <section className="ai-decision">
          <div className="ai-head">
            <Icon name="sparkle" />
            <span>Decided by {review.ai_decision.actor}</span>
            <span className="spacer" />
            <span className="sub">{review.ai_decision.action} · {fmt.dt(review.ai_decision.ts)}</span>
          </div>
          <div className="ai-diff">
            {Object.keys(review.ai_decision.after).filter(k => review.ai_decision!.before[k] !== review.ai_decision!.after[k]).map(k => (
              <span key={k} className="ev-vals">
                <code>{k}: {String(review.ai_decision!.before[k])} → {String(review.ai_decision!.after[k])}</code>
              </span>
            ))}
          </div>
          {tool.can.update ? (
            <div className="ai-reset-row">
              <button className="btn small secondary" disabled={resetting} onClick={resetAI}>
                <Icon name="undo" />Reset AI decision
              </button>
              <span className="sub">Restores the values above; logged in the audit trail under your name.</span>
            </div>
          ) : <div className="sub">Only users with update rights can reset this.</div>}
        </section>
      )}

      {record && tab === 'summary' && hasPolicy && (
        <section className="ai">
          <div className="ai-head">
            <Icon name="sparkle" />
            <span>Case summary</span>
            {summary && <span className="src" title={summary.source === 'openai' ? 'Generated by the configured LLM' : 'Deterministic summary from policy checks (LLM unavailable)'}>{summary.source === 'openai' ? 'LLM' : 'rules'}</span>}
          </div>
          {!summary && <div className="sub">Summarising…</div>}
          {summary && (
            <>
              <div className="ai-headline">{summary.headline}</div>
              <ul>{summary.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>
              <div className="ai-rec"><Icon name="arrowUpRight" />{summary.recommendation}</div>
              <Sources sources={summary.sources} />
            </>
          )}
        </section>
      )}

      {record && tab === 'policy' && hasPolicy && <AskPolicy tool={tool} record={record} />}

      {record && tab === 'policy' && hasPolicy && (
        <section className="policy">
          <div className="ai-head">
            <Icon name="book" />
            <span>Policy checks</span>
            {review && <span className={`pill ${pillColour(review.verdict)}`}>{review.verdict}</span>}
            <span className="spacer" />
            {review && <span className="sub">{review.checks.filter(c => c.passed).length}/{review.checks.length} passed</span>}
          </div>
          {!review && <div className="sub">Running checks…</div>}
          {review?.checks.map(c => <Check key={c.id} c={c} />)}
          {review && <div className="sub" style={{ marginTop: 6 }}>Click a check for the values it was judged on and the clause text.</div>}
        </section>
      )}

      {record && tab === 'details' && !showForm && (
        <section className="details">
          <div className="ai-head"><Icon name="grid" /><span>Details</span>
            <span className="spacer" />
            {editable && <button className="linkbtn" onClick={() => setShowForm(true)}>Edit</button>}
          </div>
          <dl>
            {keyFields.map(f => (
              <div key={f.name} className="kv">
                <dt>{f.label}{f.visible_to && <Icon name="lock" size={11} className="dim" />}</dt>
                <dd className={f.masked ? 'masked' : ''}>{record[f.name] == null || record[f.name] === '' ? '—' : String(
                  f.type === 'boolean' ? (record[f.name] ? 'Yes' : 'No')
                    : f.type === 'money' ? fmt.money(Number(record[f.name]), typeof record.currency === 'string' ? record.currency : 'GBP')
                    : f.type === 'datetime' ? fmt.dt(String(record[f.name]))
                    : f.type === 'date' ? fmt.date(String(record[f.name]))
                    : record[f.name])}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {(isNew || tab === 'details') && showForm && (
        <div className="form">
          {tool.fields.filter(f => !f.computed).map(f => (
            <div className="f" key={f.name}>
              <label>{f.label}{f.required ? ' *' : ''}{f.visible_to && <span title={`Visible to: ${f.visible_to.join(', ')}`}> <Icon name="lock" size={11} className="dim" /></span>}</label>
              <Input f={f} v={values[f.name]} disabled={!editable || f.readonly} onChange={v => setValues(s => ({ ...s, [f.name]: v }))} />
            </div>
          ))}
          {err && <div className="err">{err}</div>}
          <div className="acts">
            {record && <button className="btn secondary" onClick={() => { setShowForm(false); setValues({ ...record }) }}>Cancel</button>}
            {editable && <button className="btn" disabled={!dirty || saving} onClick={save}>{isNew ? 'Create' : 'Save changes'}</button>}
          </div>
          {!editable && <div className="sub">Read-only for your role.</div>}
        </div>
      )}

      {record && tab === 'details' && (
        <div className="audit">
          <h4>Audit trail</h4>
          {audit.length === 0 && <div className="sub">No changes recorded yet.</div>}
          {audit.map(e => (
            <div className="e" key={e.id}>
              <div><span className="who">{e.user_id}</span> · {e.action.replace('action:', '')} <span className="when">{fmt.dt(e.ts)}</span></div>
              {e.after && Object.keys(e.after).length > 0 && (
                <div className="diff">{Object.entries(e.after).map(([k, v]) => `${k}: ${e.before?.[k] ?? '—'} → ${v}`).join(', ')}</div>
              )}
              {e.comment && <div className="cmt">“{e.comment}”</div>}
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}
