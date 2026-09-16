import type { TileSpec } from './api'
import { fmt } from './api'
import { Icon } from './Icon'

const PALETTE = ['#5b9cf6', '#b083f0', '#39c5bb', '#3fb950', '#d9a021', '#f0524f', '#8b8b90']

function value(t: TileSpec, v: number) {
  if (t.format === 'money') return fmt.money(v)
  if (t.format === 'percent') return `${fmt.num(v)}%`
  return fmt.num(v)
}

function Kpi({ t }: { t: TileSpec }) {
  const alert = /without|breach|stale|sanction/i.test(t.title) && (t.value ?? 0) > 0
  return (
    <div className={`tile ${alert ? 'alert' : ''}`}>
      <div className="h"><span>{t.title}</span><span className="icons"><Icon name="expand" size={13} /></span></div>
      <div className="v">{value(t, t.value ?? 0)}</div>
      <div className="sub">{t.metric === 'count' ? 'records' : `${t.metric} of ${t.field}`}</div>
    </div>
  )
}

function Bars({ t }: { t: TileSpec }) {
  const data = t.data ?? []
  const max = Math.max(1, ...data.map(d => d.value))
  return (
    <div className="bars">
      {data.map(d => (
        <div key={d.label} className="b" style={{ height: `${(d.value / max) * 100}%` }} title={`${d.label}: ${value(t, d.value)}`}>
          <span>{d.label.slice(-2)}</span>
        </div>
      ))}
    </div>
  )
}

function HBars({ t }: { t: TileSpec }) {
  const data = (t.data ?? []).slice(0, 6)
  const max = Math.max(1, ...data.map(d => d.value))
  return (
    <div className="hbars">
      {data.map(d => (
        <div className="row" key={d.label}>
          <span className="lbl" title={d.label}>{d.label || '(unassigned)'}</span>
          <div className="trk"><div className="fill" style={{ width: `${(d.value / max) * 100}%` }} /></div>
          <span className="n">{value(t, d.value)}</span>
        </div>
      ))}
    </div>
  )
}

function Donut({ t }: { t: TileSpec }) {
  const data = t.data ?? []
  const total = data.reduce((a, d) => a + d.value, 0) || 1
  let acc = 0
  const r = 40, c = 2 * Math.PI * r
  return (
    <div className="donut">
      <svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} fill="none" stroke="#262628" strokeWidth="16" />
        {data.map((d, i) => {
          const len = (d.value / total) * c
          const el = <circle key={d.label} cx="50" cy="50" r={r} fill="none" stroke={PALETTE[i % PALETTE.length]} strokeWidth="16"
            strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-acc} transform="rotate(-90 50 50)" />
          acc += len
          return el
        })}
        <text x="50" y="54" textAnchor="middle" fontSize="16" fontWeight="600" fill="#ececec">{t.metric === 'count' ? total : ''}</text>
      </svg>
      <div className="legend">
        {data.map((d, i) => <div key={d.label}><i style={{ background: PALETTE[i % PALETTE.length] }} />{d.label} <b style={{ marginLeft: 'auto' }}>{value(t, d.value)}</b></div>)}
      </div>
    </div>
  )
}

export function Dashboard({ tiles }: { tiles: TileSpec[] }) {
  return (
    <div className="tiles">
      {tiles.map((t, i) => t.type === 'kpi' ? <Kpi key={i} t={t} /> : (
        <div className="tile wide" key={i}>
          <div className="h"><span>{t.title}</span><span className="icons"><Icon name="expand" size={13} /></span></div>
          {t.chart === 'donut' ? <Donut t={t} /> : t.chart === 'hbar' ? <HBars t={t} /> : <Bars t={t} />}
        </div>
      ))}
    </div>
  )
}
