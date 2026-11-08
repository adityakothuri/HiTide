import { CircleCheck, CircleDot, Circle } from 'lucide-react'
import { useApp } from '../../state/StoreContext'
import type { Town } from '../../data/types'
import { formatClock } from '../../lib/format'
import { helpSteps, type HelpStep, type StepStatus } from '../../state/driverFlow'
import { MiniMap } from '../../map/MiniMap'
import { LargeTitle, Section } from '../ios'
import iosStyles from '../ios.module.css'
import { Call911 } from './Call911'
import type { DriverView } from '../useDriverView'
import s from './Screens.module.css'

const ICON = { done: CircleCheck, active: CircleDot, waiting: Circle }
const ICON_CLASS: Record<StepStatus, string> = { done: s.stepDone, active: s.stepActive, waiting: s.stepWaiting }
const STATUS_TEXT: Record<StepStatus, string> = { done: 'Done', active: 'In progress', waiting: 'Waiting' }

function advice(view: DriverView): string {
  const onRoof = view.case?.vision?.people.some((p) => p.placement === 'on_roof')
  if (onRoof) return 'Stay on the roof and hold on. Rescuers know you are there.'
  return 'If water is rising inside the car, unbuckle, open a window and climb onto the roof. Do not walk into moving water.'
}

function stepTitle(st: HelpStep): string {
  return st.key === 'drone' && st.status === 'done' ? 'Drone reached your car' : st.label
}


export function Help({ view, town }: { view: DriverView; town: Town | null }) {
  const segments = useApp((st) => st.segments)
  const c = view.case
  if (!c) return null
  const contact = view.persona?.contact.name ?? 'your emergency contact'
  const steps = helpSteps(c, view.drone, contact)
  const drone = view.drone
  const onScene = drone?.status === 'on_scene'
  const car: [number, number] = [c.location.lon, c.location.lat]
  const dronePt: [number, number] | null = drone ? [drone.lon, drone.lat] : null

  return (
    <>
      <LargeTitle sub={advice(view)}>Help is on the way</LargeTitle>

      <Section header="Progress" id="progress">
        {steps.map((st) => {
          const Icon = ICON[st.status]
          const time = st.ts && st.status === 'done' ? formatClock(st.ts) : undefined
          return (
            <div key={st.key} className={`${iosStyles.row} ${iosStyles.withIcon}`}>
              <Icon className={`${s.stepIcon} ${ICON_CLASS[st.status]}`} aria-hidden="true" />
              <span className={iosStyles.rowText}>
                <span className={iosStyles.rowTitle}>{stepTitle(st)}</span>
                <span className="visually-hidden">{STATUS_TEXT[st.status]}</span>
                {st.key === 'drone' && st.status === 'active' && st.detail && <span className={iosStyles.rowSub}>{st.detail}</span>}
              </span>
              {time && <time className={iosStyles.trailing} dateTime={st.ts}>{time}</time>}
            </div>
          )
        })}
      </Section>

      {town && (
        <Section header="Your location" id="loc" footer={`${onScene ? 'The drone is over your car. ' : drone ? 'A drone is on the way. ' : ''}Rescuers can see this location.`}>
          <div className={s.mapWrap}>
            <MiniMap town={town} segments={segments} focus={car} drone={dronePt} height={190} maxZoom={14.5} label="Map showing your car and the drone flying to it" />
          </div>
        </Section>
      )}

      <Call911 />
    </>
  )
}
