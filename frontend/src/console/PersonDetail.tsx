import { MessageSquare, Phone, PhoneMissed, ShieldAlert, Users, X } from 'lucide-react'
import { helpAt, lastCallSummary, needsHelp, personTone } from '../region/derive'
import type { Person } from '../region/types'
import { wxClock } from '../wx/time'
import { stepText } from './stepText'
import s from './Situation.module.css'

const LEVEL = { critical: 'Critical', danger: 'Danger', warning: 'Warning', watch: 'Watch', none: 'No danger' } as const
const ADVICE: Record<string, string> = {
  move_to_high_ground: 'Move to high ground now',
  stay_off_roads: 'Stay off the roads',
  turn_around: 'Turn around, don’t drown',
  shelter_in_place: 'Shelter in place',
  monitor: 'Keep watching conditions',
}

/** A person in danger: why, what we told them, and every text, call and escalation so far. */
export function PersonDetail({ person, name, onClose }: { person: Person; name: string; onClose: () => void }) {
  const r = person.response
  const tone = personTone(person.level)
  const help = needsHelp(person)
  const helpTime = help ? helpAt(person) : null
  const summary = help ? lastCallSummary(person) : null
  const flags = r
    ? [
        { on: r.called, label: r.call_unanswered ? 'Call unanswered' : 'Called', icon: r.call_unanswered ? PhoneMissed : Phone },
        { on: r.awaiting_reply, label: 'Waiting for reply', icon: MessageSquare },
        { on: r.family_contacted, label: 'Family contacted', icon: Users },
        { on: r.responders_flagged, label: 'Responders flagged', icon: ShieldAlert },
      ].filter((f) => f.on)
    : []
  return (
    <aside className={`${s.personPanel}`} aria-label={`${name}, details`}>
      {help && (
        <div className={s.helpBanner} role="alert">
          <strong><ShieldAlert size={15} aria-hidden="true" />Needs emergency help</strong>
          {helpTime != null && <span className="num">Asked at {wxClock(helpTime * 1000)}</span>}
          {summary && <p>{summary}</p>}
        </div>
      )}
      <div className={s.section}>
        <div className={s.head}>
          <span className={`${s.tag} ${s[tone]}`}>{LEVEL[person.level]}{person.stopped_in_water ? ' · car in water' : ''}</span>
          <button type="button" className={s.close} onClick={onClose} aria-label="Close person detail"><X size={16} aria-hidden="true" /></button>
        </div>
        <h2 className={s.personName}>{name}</h2>
        {person.advice && <p className={s.advice}>{ADVICE[person.advice] ?? person.advice.replace(/_/g, ' ')}</p>}
        {flags.length > 0 && (
          <ul className={s.flags}>
            {flags.map(({ label, icon: Icon }) => (
              <li key={label}><Icon size={13} aria-hidden="true" />{label}</li>
            ))}
          </ul>
        )}
      </div>

      <div className={s.section}>
        <h3 className={s.title}>Why</h3>
        <ul className={s.reasons}>
          {person.reasons.map((x) => <li key={x}>{x}</li>)}
        </ul>
      </div>

      <div className={s.section}>
        <h3 className={s.title}>Outreach</h3>
        {r && r.timeline.length > 0 ? (
          <ol className={s.ladder}>
            {r.timeline.map((e, i) => (
              <li key={`${e.t}-${i}`}>
                <time className="num">{wxClock(e.t * 1000)}</time>
                <span>{stepText(e.what)}</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className={s.empty}>No texts or calls yet.</p>
        )}
      </div>

      {person.location.lat != null && person.location.lon != null && (
        <div className={s.section}>
          <h3 className={s.title}>Shared with responders</h3>
          <p className={`${s.sub} num`}>{person.location.lat.toFixed(4)}, {person.location.lon.toFixed(4)}{person.hazard?.road_name ? ` · near ${person.hazard.road_name}` : ''}</p>
        </div>
      )}
    </aside>
  )
}
