import { useState, type FormEvent } from 'react'
import { Activity, Camera, Check, Clock, CloudRain, Construction, Send, Users } from 'lucide-react'
import type { Access, EvidenceState, Observation, Road, Task } from '../types'
import {
  accessChip, ageLabel, clock, communityNames, freshnessChip, fullTime, guidance, latestDirect, roadEvidence, sourceShort,
} from './derive'
import s from './ops.module.css'

export type Act = (path: string, body: unknown, success: string) => Promise<void>

interface Props {
  state: EvidenceState
  road: Road
  task?: Task
  now: number
  busy: boolean
  onAction: Act
}

function localNow() {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

const KIND_ICON = { report: Users, warning: CloudRain, alert: CloudRain, closure: Construction, gauge: Activity, inspection: Camera, drone: Camera }

export function RoadDetail({ state, road, task, now, busy, onAction }: Props) {
  const [showReport, setShowReport] = useState(false)
  const chip = accessChip(road)
  const fresh = freshnessChip(road)
  const evidence = roadEvidence(state, road, task)
  const latest = latestDirect(state, road)
  const communities = task ? communityNames(state, task.affected_communities) : []
  const latestAge = ageLabel(latest?.observed_at, now)

  return (
    <section className={`${s.panel} ${s.detail}`} aria-labelledby="detail-heading">
      <h2 id="detail-heading" className={s.detailTitle}>{road.name || road.id}</h2>
      <div className={s.chips}>
        <span className={`${s.chip} ${s[`chip_${chip.tone}`]}`}>{chip.label}</span>
        {fresh && <span className={`${s.chip} ${s.chip_caution}`}><Clock size={14} aria-hidden />{fresh.label}</span>}
      </div>
      <p className={s.guidance}>{guidance(road)}</p>

      <h3 className={s.subhead}>{task ? 'Why this is prioritized' : 'Current picture'}</h3>
      <table className={s.why}>
        <tbody>
          {communities.map((c) => (
            <tr key={c.id}>
              <th scope="row">{c.name.replace(/\s*\(synthetic\)$/i, '')}</th>
              <td>{c.remaining_exits != null ? `${c.remaining_exits} modeled exit${c.remaining_exits === 1 ? '' : 's'} remaining` : c.conservative_access ? 'Modeled access' : 'Access uncertain'}</td>
            </tr>
          ))}
          <tr>
            <th scope="row">Current observation</th>
            <td>{latestAge ? `${latestAge === 'just now' ? 'Just now' : `${latestAge} old`} · ${sourceShort(latest?.source_id ?? '')}` : 'None on this road'}</td>
          </tr>
          {task && <tr><th scope="row">Inspection</th><td className={s.cap}>{task.status}</td></tr>}
        </tbody>
      </table>
      {task && task.reasons.length > 0 && (
        <ul className={s.reasons}>{task.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      )}

      <h3 className={s.subhead}>Evidence timeline</h3>
      {evidence.length ? (
        <ol className={s.timeline}>{evidence.map((o) => <TimelineItem key={o.id} o={o} />)}</ol>
      ) : (
        <p className={s.muted}>No observations yet. Missing information is treated as unknown.</p>
      )}

      <div className={s.detailActions}>
        {task && (task.status === 'queued' || task.status === 'inconclusive') && (
          <button type="button" className={s.primary} disabled={busy}
            onClick={() => void onAction(`/tasks/${encodeURIComponent(task.id)}/assign`, {}, 'Inspection assigned. Awaiting fresh evidence.')}>
            <Send size={17} aria-hidden />Assign inspection
          </button>
        )}
        {task?.status === 'assigned' && <InspectionForm task={task} simulated={state.dataset.simulated} busy={busy} onAction={onAction} />}
        <button type="button" className={s.linkButton} aria-expanded={showReport} onClick={() => setShowReport((v) => !v)}>
          {showReport ? 'Cancel field report' : 'Add field report'}
        </button>
        {showReport && <ReportForm road={road} simulated={state.dataset.simulated} busy={busy} onAction={onAction} onDone={() => setShowReport(false)} />}
        <p className={s.footnote}>Assignment does not launch a physical drone.</p>
      </div>
    </section>
  )
}

function TimelineItem({ o }: { o: Observation }) {
  const Icon = KIND_ICON[o.kind as keyof typeof KIND_ICON] ?? Users
  const description = typeof o.raw.description === 'string' ? o.raw.description : `Reported access: ${o.access}`
  const KIND_LABEL: Record<string, string> = { warning: 'weather warning', alert: 'weather alert', drone: 'inspection', inspection: 'inspection' }
  const kind = KIND_LABEL[o.kind] ?? o.kind
  return (
    <li className={s.tlItem}>
      <span className={s.tlIcon} aria-hidden><Icon size={18} /></span>
      <div className={s.tlBody}>
        <p className={s.tlTitle}><time dateTime={o.observed_at ?? undefined}>{clock(o.observed_at)}</time> · {sourceShort(o.source_id)} {kind}</p>
        <p className={s.tlText}>{description}</p>
        <p className={s.tlMeta}>Observed {fullTime(o.observed_at)} · received {fullTime(o.ingested_at)}</p>
      </div>
      <span className={s.tlTags}>
        <span className={`${s.chip} ${s.chip_neutral}`}>{o.quality === 'unverified' ? 'Unverified' : o.quality}</span>
        {o.simulated && <span className={`${s.chip} ${s.chip_sim}`}>Simulated</span>}
      </span>
    </li>
  )
}

function InspectionForm({ task, simulated, busy, onAction }: { task: Task; simulated: boolean; busy: boolean; onAction: Act }) {
  const [outcome, setOutcome] = useState('closed')
  const [observedAt, setObservedAt] = useState(localNow)
  const [image, setImage] = useState('')
  const submit = (e: FormEvent) => {
    e.preventDefault()
    void onAction(`/tasks/${encodeURIComponent(task.id)}/complete`,
      { outcome, observed_at: new Date(observedAt).toISOString(), ...(image ? { image_url: image } : {}) },
      'Inspection recorded. Road evidence and priorities recomputed.')
  }
  return (
    <form className={s.form} onSubmit={submit}>
      <label>Inspection finding
        <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="closed">Closed / flooding observed</option>
          <option value="open">Open / no obstruction observed</option>
          <option value="inconclusive">Inconclusive / unable to verify</option>
        </select>
      </label>
      <label>Captured at (your local time)
        <input type="datetime-local" required value={observedAt} onChange={(e) => setObservedAt(e.target.value)} />
      </label>
      {!simulated && <label>Image path (optional)<input value={image} onChange={(e) => setImage(e.target.value)} placeholder="/static/drone/inspection.jpg" /></label>}
      <button className={s.primary} disabled={busy} type="submit"><Check size={17} aria-hidden />{simulated ? 'Record simulated inspection' : 'Record inspection evidence'}</button>
    </form>
  )
}

interface ReportProps { road: Road; simulated: boolean; busy: boolean; onAction: Act; onDone: () => void }

function ReportForm({ road, simulated, busy, onAction, onDone }: ReportProps) {
  const [access, setAccess] = useState<Access>('unknown')
  const [text, setText] = useState('')
  const [at, setAt] = useState(localNow)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    await onAction('/reports', {
      source_id: 'local_reports', kind: 'report', road_id: road.id, access, observed_at: new Date(at).toISOString(),
      quality: 'unverified', simulated, raw: { description: text },
    }, 'Field report stored as unverified evidence with its observation time.')
    onDone()
  }
  return (
    <form className={s.form} onSubmit={(e) => void submit(e)}>
      <label>Observed access
        <select value={access} onChange={(e) => setAccess(e.target.value as Access)}>
          <option value="unknown">Unknown / unable to verify</option>
          <option value="closed">Closed / blocked</option>
          <option value="restricted">Restricted</option>
          <option value="open">Reported open</option>
        </select>
      </label>
      <label>Observed at (your local time)<input type="datetime-local" required value={at} onChange={(e) => setAt(e.target.value)} /></label>
      <label>What did you observe?
        <textarea required maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} placeholder="Water coverage, visible obstructions, exact location…" />
      </label>
      <button className={s.secondary} type="submit" disabled={busy || !text.trim()}>Save field report{simulated ? ' (simulated)' : ''}</button>
    </form>
  )
}
