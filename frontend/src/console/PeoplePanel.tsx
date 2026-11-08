import { Home, Users } from 'lucide-react'
import { useMemo, useState } from 'react'
import { areasAtRisk, hadCall, needsHelp, peopleSummary, personTone, sortPeople } from '../region/derive'
import type { Area, Person } from '../region/types'
import type { RegionPick } from '../map/regionLayers'
import s from './Situation.module.css'

const PREVIEW = 8

const LEVEL_LABEL = { critical: 'Critical', danger: 'Danger', warning: 'Warning', watch: 'Watch', none: '' } as const
const AREA_LABEL = { cut_off: 'Cut off', partially_cut_off: 'Partly cut off', at_risk: 'At risk', ok: '' } as const
const INSTRUCTION = { route_out: 'Leave now', shelter_in_place: 'Shelter in place', wait_for_check: 'Waiting for a drone check', none: '' } as const
const RESCUE = { boat_required: 'Boat needed', truck_route: 'Truck can reach' } as const
const AREA_TONE = { cut_off: 'critical', partially_cut_off: 'warning', at_risk: 'warning', ok: 'muted' } as const

interface Pickable {
  pick: RegionPick | null
  onPick: (p: RegionPick) => void
}

/** Who is in a tough spot right now: counts by level, then the people, most urgent first. */
export function PeoplePanel({ people, total, names, pick, onPick, preview = PREVIEW }: Pickable & { people: readonly Person[]; total: number; names: Record<string, string>; preview?: number }) {
  const [all, setAll] = useState(false)
  const [warnings, setWarnings] = useState(false)
  const sum = useMemo(() => peopleSummary(people), [people])
  // Warning-level people are counted but listed only on request: the list is for people who need help now.
  // Anyone who asked for help is always listed, whatever their level.
  const sorted = useMemo(() => sortPeople(warnings ? people : people.filter((p) => needsHelp(p) || p.level === 'critical' || p.level === 'danger'), names), [people, names, warnings])
  const shown = all ? sorted : sorted.slice(0, preview)
  return (
    <section className={s.section} aria-labelledby="people-h">
      <div className={s.head}>
        <h2 id="people-h" className={s.title}><Users className={`${s.titleIcon} ${s.iconCritical}`} aria-hidden="true" />People in danger</h2>
        <span className={`${s.badge} ${sum.critical + sum.danger ? s.badgeCritical : ''} num`}>{total} flagged</span>
      </div>
      <p className={s.counts}>
        <span><strong className={sum.critical ? s.hot : ''}>{sum.critical}</strong> critical</span>
        <span><strong className={sum.danger ? s.hot : ''}>{sum.danger}</strong> danger</span>
        <span><strong className={sum.warning ? s.warm : ''}>{sum.warning}</strong> warning</span>
      </p>
      {sorted.length === 0 ? (
        <p className={s.empty}>No one in danger right now.</p>
      ) : (
        <ul className={s.list}>
          {shown.map((p) => {
            const selected = pick?.kind === 'person' && pick.id === p.user_id
            const where = p.hazard?.road_name ? `near ${p.hazard.road_name}` : null
            const help = needsHelp(p)
            const sub = help ? (hadCall(p) ? 'Asked for help on the HiTide call' : 'Asked for help') : p.stopped_in_water ? 'Car stopped in water' : p.reasons[0] ?? where
            return (
              <li key={p.user_id}>
                <button type="button" className={`${s.row} ${selected ? s.on : ''}`} aria-pressed={selected} onClick={() => onPick({ kind: 'person', id: p.user_id })}>
                  <span className={`${s.dot} ${s[help ? 'critical' : personTone(p.level)]}`} aria-hidden="true" />
                  <span className={s.main}>
                    <span className={s.name}>{names[p.user_id] ?? 'Unnamed person'}</span>
                    <span className={s.sub}>{sub}</span>
                  </span>
                  {help ? (
                    <span className={`${s.tag} ${s.critical} ${s.helpTag}`}>Needs emergency help</span>
                  ) : (
                    <span className={`${s.tag} ${s[personTone(p.level)]}`}>{LEVEL_LABEL[p.level]}</span>
                  )}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      <div className={s.moreRow}>
        {sorted.length > preview && (
          <button type="button" className={s.more} onClick={() => setAll((x) => !x)} aria-expanded={all}>
            {all ? 'Show fewer' : `Show all ${sorted.length}`}
          </button>
        )}
        {sum.warning > 0 && (
          <button type="button" className={s.more} onClick={() => setWarnings((x) => !x)} aria-pressed={warnings}>
            {warnings ? 'Hide warning level' : `Include ${sum.warning} at warning level`}
          </button>
        )}
      </div>
    </section>
  )
}

/** Neighbourhoods, camps and RV parks whose way out is flooded or uncertain. */
const AREA_PREVIEW = 6

export function AreasPanel({ areas, pick, onPick }: Pickable & { areas: readonly Area[] }) {
  const [all, setAll] = useState(false)
  const list = useMemo(() => areasAtRisk(areas), [areas])
  const shown = all ? list : list.slice(0, AREA_PREVIEW)
  const households = list.reduce((n, a) => n + a.households, 0)
  return (
    <section className={s.section} aria-labelledby="areas-h">
      <div className={s.head}>
        <h2 id="areas-h" className={s.title}><Home className={`${s.titleIcon} ${s.iconCritical}`} aria-hidden="true" />Areas cut off or at risk</h2>
        {list.length > 0 && <span className={`${s.badge} ${s.badgeCritical} num`}>{households.toLocaleString()} homes</span>}
      </div>
      {list.length === 0 ? (
        <p className={s.empty}>Every area still has a dry way out.</p>
      ) : (
        <ul className={s.list}>
          {shown.map((a) => {
            const selected = pick?.kind === 'area' && pick.id === a.id
            const detail = [a.rescue ? RESCUE[a.rescue] : null, INSTRUCTION[a.instruction] || null].filter(Boolean).join(' · ')
            return (
              <li key={a.id}>
                <button type="button" className={`${s.row} ${selected ? s.on : ''}`} aria-pressed={selected} onClick={() => onPick({ kind: 'area', id: a.id })} title={detail || a.reasons[0] || a.town}>
                  <span className={`${s.dot} ${s.ring} ${s[AREA_TONE[a.status]]}`} aria-hidden="true" />
                  <span className={s.name}>{a.name}</span>
                  <span className={`${s.tag} ${s[AREA_TONE[a.status]]}`}>{AREA_LABEL[a.status]}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {list.length > AREA_PREVIEW && (
        <button type="button" className={s.more} onClick={() => setAll((x) => !x)} aria-expanded={all}>
          {all ? 'Show fewer' : `Show all ${list.length}`}
        </button>
      )}
    </section>
  )
}
