import type { Case, DroneState, Reply } from '../data/types'
import { formatEta } from '../lib/eta'
import { stateIndex } from './cases'

export type DriverScreen = 'calm' | 'warning' | 'en_route' | 'check_in' | 'help' | 'after'

export interface DriverFlowInput {
  alertActive: boolean
  hasPretrip: boolean
  turnAround: boolean
  turnAroundDismissed: boolean
  case: Case | null
  reply: Reply | null
}

/** Which driver screen to show. Precedence: case > turn-around > pre-trip warning > calm. */
export function deriveDriverScreen(i: DriverFlowInput): DriverScreen {
  if (i.case) {
    if (i.reply === 'safe' || i.case.state === 'resolved') return 'after'
    if (i.reply === 'need_help' || stateIndex(i.case.state) >= stateIndex('drone_en_route')) return 'help'
    return 'check_in'
  }
  if (i.turnAround) return i.turnAroundDismissed ? 'warning' : 'en_route'
  if (i.hasPretrip && i.alertActive) return 'warning'
  return 'calm'
}

export type StepStatus = 'done' | 'active' | 'waiting'

export interface HelpStep {
  key: 'called' | 'contact' | 'drone' | 'rescue'
  label: string
  status: StepStatus
  detail?: string
  ts?: string
}

function findTs(c: Case, match: (kind: string, text: string) => boolean): string | undefined {
  return c.timeline.find((e) => match(e.kind, e.text.toLowerCase()))?.ts
}

/** The four steps on "Help is on the way", derived from the case and its drone. */
export function helpSteps(c: Case, drone: DroneState | null, contactName: string): HelpStep[] {
  const idx = stateIndex(c.state)
  const droneDone = drone?.status === 'on_scene' || idx >= stateIndex('verified')
  const droneActive = !droneDone && idx >= stateIndex('drone_en_route')
  const rescueDone = c.responder_flag || idx >= stateIndex('handed_to_responders')

  const droneDetail = droneDone ? 'At your car' : droneActive && drone ? `Arriving in ${formatEta(drone.eta_s)}` : undefined

  return [
    {
      key: 'called',
      label: 'We called you',
      status: idx >= stateIndex('calling') ? 'done' : 'waiting',
      ts: findTs(c, (k) => k === 'outreach'),
    },
    {
      key: 'contact',
      label: `We contacted ${contactName}`,
      detail: 'Emergency contact',
      status: idx >= stateIndex('contacting_family') ? 'done' : 'waiting',
      ts: findTs(c, (_, t) => t.includes('family') || t.includes('daughter')),
    },
    {
      key: 'drone',
      label: 'Drone on the way',
      detail: droneDetail,
      status: droneDone ? 'done' : droneActive ? 'active' : 'waiting',
      ts: findTs(c, (k) => k === 'drone'),
    },
    {
      key: 'rescue',
      label: 'Rescue team notified',
      status: rescueDone ? 'done' : 'waiting',
      ts: findTs(c, (k, t) => k === 'flag' || t.includes('responders')),
    },
  ]
}
