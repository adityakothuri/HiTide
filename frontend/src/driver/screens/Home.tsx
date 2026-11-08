import { WaveMark } from '../../ui/WaveMark'
import { Check, CreditCard, LifeBuoy, MapPin, Settings as Gear, ShieldCheck, TriangleAlert, Users } from 'lucide-react'
import { useApp } from '../../state/StoreContext'
import { firstName, formatRelative } from '../../lib/format'
import { useNow } from '../../lib/useNow'
import { useToast } from '../../ui/Toast'
import { Row, Section } from '../ios'
import type { DriverView } from '../useDriverView'
import s from './Screens.module.css'

const hourFmt = new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: 'America/Chicago' })

export function greeting(now: number): string {
  const h = Number(hourFmt.format(now))
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

export function Home({ view, onSettings }: { view: DriverView; onSettings: () => void }) {
  const now = useNow()
  const toast = useToast()
  const checkedAt = useApp((st) => st.lastEventAt)
  const p = view.persona
  const warningNearby = view.alert?.active ?? false
  const notInDemo = () => toast('Not part of this prototype')

  return (
    <>
      <section className={s.band} data-band>
        <div className={s.bandBar}>
          <span className={s.bandMark}>
            <WaveMark size={14} />
            HiTide
          </span>
          <button type="button" className={s.bandButton} onClick={onSettings} aria-label="HiTide settings">
            <Gear aria-hidden="true" />
          </button>
        </div>
        <h2 className={s.bandTitle} tabIndex={-1}>{greeting(now)}, {firstName(view.name)}</h2>
      </section>

      <div className={s.overlap}>
        <Section>
          <div className={s.statusRow} role="status">
            {warningNearby
              ? <TriangleAlert className={`${s.statusGlyph} ${s.statusCaution}`} aria-hidden="true" />
              : <ShieldCheck className={`${s.statusGlyph} ${s.statusSafe}`} aria-hidden="true" />}
            <span className={s.statusText}>
              <span className={s.statusTitle}>{warningNearby ? 'Flood warning in your area' : 'HiTide is on'}</span>
              <span className={s.statusSub}>
                {warningNearby
                  ? 'Your usual routes are clear right now. We will alert you if that changes.'
                  : `No flood warnings near you${checkedAt ? `. Checked ${formatRelative(checkedAt, now).toLowerCase()}` : ''}.`}
              </span>
            </span>
          </div>
        </Section>
      </div>

      {p && (
        <Section header="Next trip" id="next-trip">
          <Row
            icon={MapPin}
            title={p.trip.label}
            subtitle={`Home to ${p.trip.destination}`}
            trailing={<span className={s.clear}><Check aria-hidden="true" />No flooding</span>}
          />
        </Section>
      )}

      <Section header={p ? `Your vehicle, ${p.vehicle}` : 'Your vehicle'} id="quick">
        <Row icon={CreditCard} title="ID cards" chevron onClick={notInDemo} />
        <Row icon={LifeBuoy} title="Roadside assistance" chevron onClick={notInDemo} />
        {p && <Row icon={Users} title="Emergency contact" subtitle={p.contact.name} chevron onClick={onSettings} />}
      </Section>
    </>
  )
}
