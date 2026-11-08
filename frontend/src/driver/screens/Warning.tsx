import { Check, Clock, Droplets, Route as RouteIcon, TriangleAlert } from 'lucide-react'
import { useMemo } from 'react'
import { useApp, useStore } from '../../state/StoreContext'
import type { Town } from '../../data/types'
import { formatClock, formatDepth, formatDistance, sentenceCase } from '../../lib/format'
import { streetFromText, streetOf } from '../../lib/geo'
import { MiniMap } from '../../map/MiniMap'
import { Btn, LargeTitle, Row, Section } from '../ios'
import type { DriverView } from '../useDriverView'
import s from './Screens.module.css'

type Pt = [number, number]

function tripLabel(body: string | undefined, fallback: string): string {
  const m = body ? /route to (\w[\w ]*?) crosses/.exec(body) : null
  return m ? m[1] : fallback.toLowerCase()
}

export function Warning({ view, town }: { view: DriverView; town: Town | null }) {
  const store = useStore()
  const segments = useApp((st) => st.segments)
  const { reroute, turnAround, pretrip, alert } = view
  const taEdge = turnAround?.hazard_edge_id
  const hazardIds = useMemo(
    () => (reroute?.blocked_edge_ids.length ? reroute.blocked_edge_ids : taEdge ? [taEdge] : []),
    [reroute, taEdge],
  )
  const route = useMemo(() => (reroute ? (reroute.route.coordinates as Pt[]) : null), [reroute])
  const hazardId = hazardIds[0]
  const street = (hazardId && streetOf(town, hazardId)) || streetFromText(pretrip?.body) || 'A road on your route'
  const depth = turnAround?.hazard_depth_in ?? (hazardId ? segments[hazardId]?.depth_in : undefined)
  const trip = tripLabel(pretrip?.body, view.persona?.trip.label ?? 'your trip')
  const hasSaferRoute = reroute !== null
  const accepted = view.routeAccepted || turnAround !== null
  const driverId = view.driverId

  const accept = () => store.setUi((u) => ({ ...u, routeAccepted: { ...u.routeAccepted, [driverId]: true } }))
  const later = () => store.setUi((u) => ({ ...u, remindLater: { ...u.remindLater, [driverId]: true } }))

  return (
    <>
      <div className={s.alert} role="status">
        <TriangleAlert aria-hidden="true" />
        <div>
          <p className={s.alertTitle}>{sentenceCase(alert?.event ?? 'Flash flood warning')}</p>
          <p className={s.alertSub}>
            Kerr County{pretrip ? `, sent ${formatClock(pretrip.ts)}` : ''}
            {alert?.simulated ? ', simulated' : ''}
          </p>
        </div>
      </div>

      <LargeTitle size="title" sub={turnAround ? undefined : 'Just 12 inches of moving water can float a car.'}>
        {turnAround ? 'You turned around. Here is your new route.' : `Your usual route to ${trip} crosses a flooded road`}
      </LargeTitle>

      <div className={s.stackTight}>
        <Section flush>
          {town ? (
            <MiniMap
              town={town}
              segments={segments}
              route={route}
              hazardEdgeIds={hazardIds}
              height={200}
              label={`Map of your trip: ${hasSaferRoute ? 'safer route in green, ' : ''}flooded road at ${street} in red`}
            />
          ) : (
            <div className={s.mapPlaceholder} aria-hidden="true" />
          )}
          <Row icon={Droplets} title={street} subtitle={`Flooded${depth !== undefined ? `, about ${formatDepth(depth)} of water` : ''}`} />
          {hasSaferRoute ? (
            <Row icon={RouteIcon} title={`Safer route, ${formatDistance(reroute.distance_m)}`} subtitle="Avoids every flooded road we know about" />
          ) : (
            <Row icon={Clock} title="No dry route right now" subtitle="Please delay your trip" />
          )}
        </Section>
        <p className={s.caption}>{hasSaferRoute ? 'Green is the safer route. The dashed line marks the flooded crossing.' : 'The dashed line marks the flooded crossing.'}</p>
      </div>

      {hasSaferRoute && (
        <div className={s.actionBar}>
          {accepted ? (
            <Btn variant="done" icon={Check} aria-disabled="true">Using safer route</Btn>
          ) : (
            <Btn icon={RouteIcon} onClick={accept}>Use safer route</Btn>
          )}
          {!accepted && !view.remindLater && <Btn variant="plain" onClick={later}>Remind me before I leave</Btn>}
          {view.remindLater && !accepted && <p className={s.note} role="status">We'll remind you 15 minutes before you usually leave.</p>}
        </div>
      )}
    </>
  )
}
