import { useEffect, useState } from 'react'
import type { AuditEntry, FieldSpec, Rec, ToolSpec } from './api'
import { api, fmt } from './api'

interface Props {
  tool: ToolSpec
  record: Rec | null   // null = new record
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

export function RecordPane({ tool, record, onClose, onSaved, toast }: Props) {
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const isNew = record === null

  useEffect(() => {
    setErr('')
    if (record) {
      setValues({ ...record })
      api.audit(tool.id, record.id).then(setAudit).catch(() => setAudit([]))
    } else {
      const d: Record<string, unknown> = {}
      tool.fields.forEach(f => { if (f.default != null) d[f.name] = f.default })
      setValues(d); setAudit([])
    }
  }, [tool, record])

  const dirty = record ? tool.fields.some(f => !f.masked && (values[f.name] ?? '') !== (record[f.name] ?? '')) : true
  const editable = isNew ? tool.can.create : tool.can.update

  async function save() {
    setSaving(true); setErr('')
    try {
      const payload: Record<string, unknown> = {}
      tool.fields.forEach(f => { if (!f.masked && f.name in values) payload[f.name] = values[f.name] })
      const r = record ? await api.update(tool.id, record.id, payload) : await api.create(tool.id, payload)
      toast(record ? 'Saved' : 'Created'); onSaved(r)
    } catch (e) { setErr((e as Error).message) } finally { setSaving(false) }
  }

  const title = record ? String(record[tool.title_field]) : `New ${tool.entity.replace('_', ' ')}`
  return (
    <aside className="pane">
      <h3>{title}<button onClick={onClose} title="Close">✕</button></h3>
      <div className="sub">{record ? `Last updated ${fmt.dt(String(record.updated_at))}` : 'Fill in the required fields'}</div>
      <div className="form">
        {tool.fields.map(f => (
          <div className="f" key={f.name}>
            <label>{f.label}{f.required ? ' *' : ''}{f.visible_to && <span title={`Visible to: ${f.visible_to.join(', ')}`}> 🔒</span>}</label>
            <Input f={f} v={values[f.name]} disabled={!editable || f.readonly} onChange={v => setValues(s => ({ ...s, [f.name]: v }))} />
          </div>
        ))}
        {err && <div className="err">{err}</div>}
        {editable && <button className="btn" disabled={!dirty || saving} onClick={save}>{isNew ? 'Create' : 'Save'}</button>}
        {!editable && <div className="sub">Read-only for your role.</div>}
      </div>
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
