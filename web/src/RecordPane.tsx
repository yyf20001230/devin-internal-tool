import { useEffect, useState } from 'react'
import type { ActionSpec, AuditEntry, FieldSpec, Rec, Review, Summary, ToolSpec } from './api'
import { api, fmt } from './api'
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


export function RecordPane({ tool, record, actions, actionEnabled, onAction, onClose, onSaved, toast }: Props) {
  const [values, setValues] = useState<Record<string, unknown>>({})
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
    setErr(''); setReview(null); setSummary(null)
    if (record) {
      setValues({ ...record }); setShowForm(false)
      api.audit(tool.id, record.id).then(setAudit).catch(() => setAudit([]))
      if (hasPolicy) {
        api.review(tool.id, record.id).then(setReview).catch(() => setReview(null))
        api.summary(tool.id, record.id).then(setSummary).catch(() => setSummary(null))
      }
    } else {
      const d: Record<string, unknown> = {}
      tool.fields.forEach(f => { if (f.default != null) d[f.name] = f.default })
      setValues(d); setAudit([]); setShowForm(true)
    }
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
  const usable = record ? actions.filter(a => a.allowed && actionEnabled(a, record)) : []
  const blocked = record ? actions.filter(a => a.allowed && !actionEnabled(a, record)) : []
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

      {record && actions.length > 0 && (
        <div className="pane-actions">
          {usable.map(a => (
            <button key={a.id} className={`btn ${a.destructive ? 'danger' : 'secondary'}`} onClick={() => onAction(a, record)}>
              <Icon name={actionIcon(a.id, a.icon, a.destructive)} />{a.label}
            </button>
          ))}
          {usable.length === 0 && <div className="sub">No actions available in the current state{blocked.length ? ` (${blocked.map(b => b.label).join(', ')} need a different status)` : ''}.</div>}
        </div>
      )}

      {record && review?.ai_decision && (
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

      {record && hasPolicy && (
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
            </>
          )}
        </section>
      )}

      {record && hasPolicy && (
        <section className="policy">
          <div className="ai-head">
            <Icon name="book" />
            <span>Policy checks</span>
            {review && <span className={`pill ${pillColour(review.verdict)}`}>{review.verdict}</span>}
          </div>
          {!review && <div className="sub">Running checks…</div>}
          {review?.checks.map(c => <Check key={c.id} c={c} />)}
          {review && (
            <div className="sub" style={{ marginTop: 6 }}>
              {review.verdict === 'Cleared' && 'All checks passed — eligible for automatic clearance.'}
              {review.verdict === 'Flagged' && 'A mandatory control failed — automation escalates, a lead decides.'}
              {review.verdict === 'Needs review' && 'Automation settled everything it could; the remaining checks need a human.'}
              {' Click a check to read the clause.'}
            </div>
          )}
        </section>
      )}

      {record && !showForm && (
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

      {showForm && (
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

      {record && (
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
