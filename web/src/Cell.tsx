import type { FieldSpec, Rec } from './api'
import { fmt } from './api'

const STATUS_COLOURS: Record<string, string> = {
  Approved: 'green', Paid: 'green', Low: 'green', Won: 'green', Submitted: 'green', Open: 'blue',
  Pending: 'amber', 'In review': 'blue', 'Awaiting approval': 'amber', Medium: 'amber', Gathering: 'amber',
  'Documents requested': 'amber', 'Not started': '', Draft: '', 'Not contesting': 'purple',
  Escalated: 'red', Rejected: 'red', High: 'red', Lost: 'red', 'Accepted loss': 'red', Failed: 'red', None: '',
  Cleared: 'green', 'Needs review': 'amber', Flagged: 'red', 'On hold': 'purple', 'Info requested': 'amber',
}
export const pillColour = (v: string) => STATUS_COLOURS[v] ?? ''

// Only the record's status is a pill; everything else is a dot, an icon or plain text so a
// row reads as one line of data rather than a stack of tags.
const PILL_FIELDS = new Set(['status'])

function Choice({ f, v }: { f: FieldSpec; v: string }) {
  const colour = STATUS_COLOURS[v] ?? ''
  if (PILL_FIELDS.has(f.name)) return <span className={`pill ${colour}`}>{v}</span>
  if (colour) return <span className={`dotted ${colour}`}><span className="dot" />{v}</span>
  return <>{v}</>
}

export function Cell({ f, r, isTitle }: { f: FieldSpec; r: Rec; isTitle?: boolean }) {
  const v = r[f.name]
  if (f.masked && v != null) return <span className="masked" title="Hidden by column-level security">{String(v)}</span>
  if (v == null || v === '') return <span style={{ color: '#5c5c62' }}>—</span>
  if (isTitle) return <span className="link">{String(v)}</span>
  switch (f.type) {
    case 'boolean':
      if (['dev', 'uat', 'prod'].includes(f.name)) return <span className={`tgl ${v ? 'on' : ''}`} />
      if (/verified|complete|approved|cr_|change/.test(f.name)) return v ? <span className="green">Yes</span> : <span className="amber">No</span>
      return v ? <span className="red" style={{ fontWeight: 600 }}>Yes</span> : <span style={{ color: '#5c5c62' }}>No</span>
    case 'choice': return <Choice f={f} v={String(v)} />
    case 'money': return <>{fmt.money(Number(v), typeof r.currency === 'string' ? r.currency : 'GBP')}</>
    case 'percent': return <>{fmt.num(Number(v))}%</>
    case 'number': return <>{fmt.num(Number(v))}</>
    case 'date': return <>{fmt.date(String(v))}</>
    case 'datetime': {
      const s = String(v)
      if (f.name.includes('due')) {
        const ms = new Date(s).getTime() - Date.now()
        const cls = ms < 0 ? 'overdue' : ms < 4 * 36e5 ? 'soon' : ''
        return <span className={cls}>{fmt.rel(s)}</span>
      }
      return <>{fmt.dt(s)}</>
    }
    default: return <>{String(v)}</>
  }
}

export const isNumeric = (f: FieldSpec) => ['number', 'money', 'percent'].includes(f.type)
