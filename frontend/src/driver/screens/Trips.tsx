import { Check, MapPin, TriangleAlert } from 'lucide-react'
import { LargeTitle, Row, Section } from '../ios'
import type { DriverView } from '../useDriverView'
import s from './Screens.module.css'

export function Trips({ view }: { view: DriverView }) {
  const p = view.persona
  const flooded = view.pretrip !== null || view.turnAround !== null
  return (
    <>
      <LargeTitle>Trips</LargeTitle>
      <Section header="Usual trips" id="usual" footer="Flood Watch checks these routes whenever a flood warning is active.">
        {p ? (
          <Row
            icon={MapPin}
            title={p.trip.label}
            subtitle={flooded ? 'Crosses a flooded road. Safer route sent.' : `Home to ${p.trip.destination}`}
            trailing={flooded
              ? <span className={`${s.clear} ${s.flooded}`}><TriangleAlert aria-hidden="true" />Flooded</span>
              : <span className={s.clear}><Check aria-hidden="true" />Clear</span>}
          />
        ) : (
          <Row title="No usual trips yet" />
        )}
      </Section>
    </>
  )
}
