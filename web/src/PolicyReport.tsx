import { useState } from 'react'
import type { AutoOutcome, AutoReviewItem, AutoReviewResult, CheckResult, Rec } from './api'
import { Icon } from './Icon'

const OUTCOME = {
  cleared: { label: 'Cleared', colour: 'green', icon: 'check' },
  escalated: { label: 'Escalated', colour: 'red', icon: 'arrow-up' },
  review: { label: 'Left for human review', colour: 'amber', icon: 'user' },
} as const
const CHECK_ICON = { pass: 'check', review: 'alert', flag: 'x' } as const
const CHECK_CLASS = { pass: 'green', review: 'amber', flag: 'red' } as const

function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  return String(v)
}

function rule(r: CheckResult['rule']): string {
  return Object.entries(r).map(([f, cond]) => {
    if (f === 'any' && Array.isArray(cond)) return cond.map(sub => `(${rule(sub as CheckResult['rule'])})`).join(' or ')
    if (Array.isArray(cond)) return `${f} in [${cond.join(', ')}]`
    if (cond && typeof cond === 'object') return Object.entries(cond as Record<string, unknown>).map(([op, x]) => `${f} ${op} ${fmt(x)}`).join(' and ')
    return `${f} = ${fmt(cond)}`
  }).join(' and ')
}

export function Check({ c }: { c: CheckResult }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`chk ${CHECK_CLASS[c.outcome]}`}>
      <div className="chk-row" onClick={() => setOpen(o => !o)} title={c.passed ? 'Passed' : 'Failed'}>
        <Icon name={CHECK_ICON[c.outcome]} className={CHECK_CLASS[c.outcome]} />
        <span className="chk-title">{c.title}</span>
        <span className="clause">{c.clause}</span>
        <Icon name="chevron" size={12} className={`chev ${open ? 'open' : ''}`} />
      </div>
      {(open || !c.passed) && <div className="chk-detail">{c.detail}</div>}
      {open && (
        <>
          <div className="chk-detail">
            <span className="ev-vals">{Object.entries(c.evidence).map(([k, v]) => <code key={k}>{k}={fmt(v)}</code>)}</span>
            <span className="ev-rule">rule: {rule(c.rule)}</span>
          </div>
          <div className="clause-text"><b>{c.clause} {c.clause_title}</b> <span className="src-doc">{c.policy}</span><br />{c.clause_text}</div>
        </>
      )}
    </div>
  )
}

function Item({ item, onOpen }: { item: AutoReviewItem; onOpen: (id: number) => void }) {
  const o = OUTCOME[item.outcome]
  const decisive = item.checks.filter(c => item.outcome === 'cleared' ? c.passed : !c.passed)
  return (
    <div className={`rep-item ${o.colour}`}>
      <div className="rep-row" onClick={() => onOpen(item.record_id)} title="Open the record to see every check, the values it was judged on and the clause text">
        <Icon name={o.icon} className={o.colour} />
        <b className="rep-title">{item.title}</b>
        <span className="rep-why">
          {o.label}
          {item.action && <> · <code>{item.action}</code></>}
          {' · '}{decisive.map(c => c.clause).join(', ')}
        </span>
        <button type="button" className="link" onClick={e => { e.stopPropagation(); onOpen(item.record_id) }}>open</button>
      </div>
    </div>
  )
}

export function PolicyReport({ result, rows, onOpen, onClose, onResetAll }: {
  result: AutoReviewResult; rows: Rec[]; onOpen: (r: Rec | null, id: number) => void; onClose: () => void
  onResetAll: (() => Promise<void>) | null
}) {
  const [filter, setFilter] = useState<AutoOutcome | null>(null)
  const [resetting, setResetting] = useState(false)
  const counts = { cleared: result.cleared.length, escalated: result.flagged.length, review: result.review.length }
  const items = result.items.filter(i => !filter || i.outcome === filter)
  const acted = result.items.filter(i => i.action).length
  return (
    <section className="report">
      <div className="ai-head">
        <Icon name="sparkle" />
        <span>Devin AI policy review</span>
        <span className="src">{result.policy_title}</span>
        <span className="spacer" />
        <span className="sub">{result.items.length} records · decisions are in the audit trail as <code>devin-ai</code></span>
        <button className="iconbtn" onClick={onClose} title="Dismiss"><Icon name="x" size={13} /></button>
      </div>
      <div className="rep-tabs">
        {(Object.keys(OUTCOME) as AutoOutcome[]).map(k => (
          <button key={k} className={`rep-tab ${OUTCOME[k].colour} ${filter === k ? 'on' : ''}`} onClick={() => setFilter(filter === k ? null : k)}>
            <b>{counts[k]}</b> {OUTCOME[k].label.toLowerCase()}
          </button>
        ))}
        <span className="spacer" />
        {onResetAll && acted > 0 && (
          <button className="btn small secondary" disabled={resetting} title="Undo every automated decision still in force on this tool"
            onClick={async () => { setResetting(true); try { await onResetAll() } finally { setResetting(false) } }}>
            <Icon name="undo" />Reset all AI decisions
          </button>
        )}
      </div>
      {items.length === 0 && <div className="sub">Nothing in this bucket.</div>}
      {items.map(i => <Item key={i.record_id} item={i} onOpen={id => onOpen(rows.find(r => r.id === id) ?? null, id)} />)}
    </section>
  )
}
