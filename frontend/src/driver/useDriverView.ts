import { useMemo } from 'react'
import { DEFAULT_DRIVER_ID, displayName, personaFor, type Persona } from '../data/personas'
import type { Alert, Case, DroneState, OutreachEvent, Reply, Reroute, TurnAround } from '../data/types'
import { deriveDriverScreen, type DriverScreen } from '../state/driverFlow'
import { useApp, useUi } from '../state/StoreContext'

export interface DriverView {
  driverId: string
  name: string
  persona: Persona | null
  screen: DriverScreen
  alert: Alert | null
  pretrip: OutreachEvent | null
  reroute: Reroute | null
  turnAround: TurnAround | null
  case: Case | null
  drone: DroneState | null
  reply: Reply | null
  routeAccepted: boolean
  remindLater: boolean
  callBody: string | null
  /** Latest voice call placed to this driver for the open case. */
  call: OutreachEvent | null
}

/** `?driver=demo-d` pins the phone to one driver. Otherwise it follows the demo's focus driver. */
export function driverFromUrl(): string | null {
  return new URLSearchParams(window.location.search).get('driver')
}

export function useDriverView(pinned: string | null): DriverView {
  const focus = useApp((s) => s.focusDriverId)
  const presenterPick = useUi((u) => u.phoneDriverId)
  const driverId = pinned ?? presenterPick ?? focus ?? DEFAULT_DRIVER_ID

  const alert = useApp((s) => s.alert)
  const pretrip = useApp((s) => s.pretrip[driverId] ?? null)
  const reroute = useApp((s) => s.reroutes[driverId] ?? null)
  const turnAround = useApp((s) => s.turnArounds[driverId] ?? null)
  const cases = useApp((s) => s.cases)
  const drones = useApp((s) => s.drones)
  const outreach = useApp((s) => s.outreach)
  const backendName = useApp((s) => s.drivers[driverId]?.name ?? '')
  const replies = useUi((u) => u.replies)
  const turnDismissed = useUi((u) => u.turnDismissed[driverId] ?? false)
  const routeAccepted = useUi((u) => u.routeAccepted[driverId] ?? false)
  const remindLater = useUi((u) => u.remindLater[driverId] ?? false)

  return useMemo(() => {
    const c = cases.find((x) => x.driver_id === driverId) ?? null
    const drone = c ? Object.values(drones).find((d) => d.case_id === c.id) ?? null : null
    const reply = c ? replies[c.id] ?? null : null
    const call = c ? outreach.findLast((o) => o.case_id === c.id && o.recipient === 'driver' && o.channel === 'voice') : undefined
    const screen = deriveDriverScreen({
      alertActive: alert?.active ?? false,
      hasPretrip: pretrip !== null,
      turnAround: turnAround !== null,
      turnAroundDismissed: turnDismissed,
      case: c,
      reply,
    })
    return {
      driverId,
      name: displayName(driverId, backendName || c?.driver_name || 'Driver'),
      persona: personaFor(driverId),
      screen,
      alert,
      pretrip,
      reroute,
      turnAround,
      case: c,
      drone,
      reply,
      routeAccepted,
      remindLater,
      callBody: call?.body ?? null,
      call: call ?? null,
    }
  }, [driverId, backendName, alert, pretrip, reroute, turnAround, cases, drones, outreach, replies, turnDismissed, routeAccepted, remindLater])
}
