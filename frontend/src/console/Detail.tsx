import { X } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Case, OutreachEvent } from '../data/types'
import { displayName } from '../data/personas'
import { useTown } from '../hooks/useTown'
import { formatClock, formatDepth, formatRelative } from '../lib/format'
import { useNow } from '../lib/useNow'
import { caseSeverity, stepLabel } from '../state/cases'
import { useApp, useUi } from '../state/StoreContext'
import { TONE_ICON } from '../ui/status'
import { caseAgeBand, casePlace, caseVehicle, channelLabel, recipientLabel, riskSummary, timelineRows } from './caseInfo'
import { DronePanel } from './DronePanel'
import { VisionPanel } from './VisionPanel'
import s from './Detail.module.css'

const SEVERITY_LABEL = { critical: 'Critical', caution: 'Caution', safe: 'Resolved' } as const
const ACTIVITY_PREVIEW = 3

/** Case detail, right side. Only rendered while a case is selected. */
export function Detail({ onClose }: { onClose: () => void }) {
  const cases = useApp((a) => a.cases)
  const selected = useUi((u) => u.selectedCaseId)
  const c = useMemo(() => cases.find((x) => x.id === selected) ?? null, [cases, selected])
  if (!c) return null
  return (
    <aside id="case-detail" className={`${s.panel} ${s.open}`} aria-label="Case detail" tabIndex={-1}>
      <CaseDetail c={c} onClose={onClose} />
    </aside>
  )
}

interface ActivityItem {
  id: string
  ts: string
  title: string
  body?: string
}

function messageItem(o: OutreachEvent): ActivityItem {
  return { id: o.id, ts: o.ts, title: `${channelLabel(o)} to ${recipientLabel(o)}`, body: o.body }
}

function CaseDetail({ c, onClose }: { c: Case; onClose: () => void }) {
  const drones = useApp((a) => a.drones)
  const outreach = useApp((a) => a.outreach)
  const { state: town } = useTown()
  const now = useNow(15_000)
  const [showAll, setShowAll] = useState(false)
  const drone = useMemo(() => Object.values(drones).find((d) => d.case_id === c.id) ?? null, [drones, c.id])
  const place = useMemo(() => casePlace(c, outreach, town.status === 'ready' ? town.town : null), [c, outreach, town])
  const activity = useMemo(() => {
    const rows: ActivityItem[] = timelineRows(c)
      .filter((r) => r.kind !== 'outreach')
      .map((r) => ({ id: r.id, ts: r.ts, title: r.text }))
    const msgs = outreach.filter((o) => o.case_id === c.id).map(messageItem)
    return [...rows, ...msgs].sort((a, b) => Date.parse(a.ts) - Date.parse(b.ts))
  }, [c, outreach])
  const sev = caseSeverity(c)
  const SevIcon = TONE_ICON[sev]
  const band = caseAgeBand(c)
  const vehicle = caseVehicle(c)
  const summary = riskSummary(c.urgency_reasons)
  const shown = showAll ? activity : activity.slice(-ACTIVITY_PREVIEW)
  const flagged = c.responder_flag && c.state !== 'resolved'

  return (
    <div className={s.body}>
      <header className={s.header}>
        <div className={s.headTop}>
          <span className={`${s.sev} ${s[sev]}`}>
            <SevIcon className={s.sevIcon} aria-hidden="true" />
            {SEVERITY_LABEL[sev]}
          </span>
          <span className={s.stepText}>{stepLabel(c.state)}</span>
          <button type="button" className={s.collapse} onClick={onClose} aria-label="Close case detail">
            <X aria-hidden="true" />
          </button>
        </div>
        <h2 className={s.name}>
          {displayName(c.driver_id, c.driver_name)}
          {band && <span className={s.band}>, {band}</span>}
        </h2>
        <p className={s.meta}>
          {place ?? 'Locating road'}, {formatDepth(c.depth_in)} of water
          {vehicle && <><br />{vehicle}</>}
          <br />
          <span className="num">Opened {formatClock(c.opened_at)}, {formatRelative(c.opened_at, now).toLowerCase()}</span>
          {flagged && <><br />Responders notified</>}
        </p>
        {summary && <p className={s.summary}>{summary}</p>}
      </header>

      {drone && <DronePanel drone={drone} caseId={c.id} target={c.location} />}

      {c.vision && <VisionPanel vision={c.vision} />}

      <section className={s.section} aria-labelledby="act-h">
        <div className={s.sectionHead}>
          <h3 id="act-h" className={s.sectionTitle}>Activity</h3>
          {activity.length > ACTIVITY_PREVIEW && (
            <button type="button" className={s.textButton} onClick={() => setShowAll((x) => !x)} aria-expanded={showAll}>
              {showAll ? 'Show less' : `Show all ${activity.length}`}
            </button>
          )}
        </div>
        <ol className={s.log}>
          {shown.map((r) => (
            <li key={r.id} className={s.logRow}>
              <time className="num" dateTime={r.ts}>{formatClock(r.ts)}</time>
              <span className={s.logText}>
                {r.title}
                {r.body && <span className={s.logBody}>{r.body}</span>}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section className={s.section} aria-labelledby="resp-h">
        <div className={s.sectionHead}>
          <h3 id="resp-h" className={s.sectionTitle}>Shared with responders</h3>
        </div>
        <dl className={s.responderGrid}>
          <div>
            <dt>Location</dt>
            <dd className="num">{c.responder_view.location.lat.toFixed(4)}, {c.responder_view.location.lon.toFixed(4)}</dd>
          </div>
          <div>
            <dt>People</dt>
            <dd>{c.responder_view.people_count == null ? 'Not confirmed' : c.responder_view.people_count === 1 ? '1 person' : `${c.responder_view.people_count} people`}</dd>
          </div>
          <div>
            <dt>Water</dt>
            <dd className="num">{formatDepth(c.responder_view.water_depth_in)}</dd>
          </div>
        </dl>
      </section>

      <p className={s.simNote}>Drone flight, drone imagery and outreach are simulated in this demo.</p>
    </div>
  )
}
