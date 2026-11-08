import { LifeBuoy, Megaphone, Undo2 } from 'lucide-react'
import { useState } from 'react'
import type { DroneCommand } from '../data/types'
import { formatEta } from '../lib/eta'
import type { DroneWithTrail } from '../state/reducer'
import { useStore } from '../state/StoreContext'
import { useToast } from '../ui/Toast'
import s from './Detail.module.css'

const STATUS: Record<DroneWithTrail['status'], string> = {
  launching: 'Launching',
  en_route: 'En route',
  on_scene: 'On scene',
  returning: 'Returning to station',
}

const DONE: Record<DroneCommand, [string, string]> = {
  speak: ['Message played from the drone', '"Help is coming. Stay on the roof."'],
  drop_jacket: ['Life jacket dropped', 'Logged on the case timeline.'],
  return: ['Drone returning', 'Heading back to Kerrville Fire Station 1.'],
}

/**
 * Typical ground-crew response for a low-water crossing in Kerr County, used only when the backend
 * doesn't send crew_eta_s yet (proposed field). Shown as an estimate.
 */
const ESTIMATED_CREW_ETA_S = 17 * 60
const MIN_BAR = 2

/** Drone status, drone vs ground-crew ETA, and drone actions. */
export function DronePanel({ drone, caseId }: { drone: DroneWithTrail; caseId: string }) {
  const store = useStore()
  const toast = useToast()
  const [busy, setBusy] = useState<DroneCommand | null>(null)
  const crewEstimated = drone.crew_eta_s == null
  const crewEta = drone.crew_eta_s ?? ESTIMATED_CREW_ETA_S
  const onScene = drone.status === 'on_scene'
  const returning = drone.status === 'returning'
  const droneEta = onScene || returning ? 0 : drone.eta_s
  const droneBar = crewEta > 0 ? Math.max(MIN_BAR, (droneEta / crewEta) * 100) : MIN_BAR

  const send = async (cmd: DroneCommand) => {
    setBusy(cmd)
    try {
      await store.provider.droneCommand(drone.id, caseId, cmd)
      toast(...DONE[cmd])
    } catch {
      toast('Drone command failed', 'Check the backend connection and try again.')
    } finally {
      setBusy(null)
    }
  }

  const actions: { cmd: DroneCommand; label: string; icon: typeof Megaphone; enabled: boolean }[] = [
    { cmd: 'speak', label: 'Speak', icon: Megaphone, enabled: onScene },
    { cmd: 'drop_jacket', label: 'Drop life jacket', icon: LifeBuoy, enabled: onScene },
    { cmd: 'return', label: 'Return', icon: Undo2, enabled: !returning },
  ]

  return (
    <section className={s.section} aria-labelledby="drone-h">
      <div className={s.sectionHead}>
        <h3 id="drone-h" className={s.sectionTitle}>Drone</h3>
        <span className={s.sectionAside}>{STATUS[drone.status]}</span>
      </div>

      <div className={s.race} role="img" aria-label={`Drone ${onScene ? 'at the car' : `arrives in ${formatEta(drone.eta_s)}`}. Ground crew ${crewEstimated ? 'about ' : ''}${formatEta(crewEta)}.`}>
        <div className={s.lane}>
          <span className={s.laneLabel}>Drone</span>
          <span className={s.track}><span className={`${s.bar} ${s.barDrone}`} style={{ width: `${droneBar}%` }} /></span>
          <span className={`${s.laneValue} num`}>{onScene ? 'At the car' : returning ? 'Returning' : formatEta(drone.eta_s)}</span>
        </div>
        <div className={s.lane}>
          <span className={s.laneLabel}>Crew</span>
          <span className={s.track}><span className={`${s.bar} ${s.barCrew}`} style={{ width: '100%' }} /></span>
          <span className={`${s.laneValue} num`}>{crewEstimated ? `About ${formatEta(crewEta)}` : formatEta(crewEta)}</span>
        </div>
      </div>

      <div className={s.actions} role="group" aria-label="Drone actions">
        {actions.map(({ cmd, label, icon: Icon, enabled }) => (
          <button
            key={cmd}
            type="button"
            className={s.action}
            aria-disabled={!enabled || busy !== null}
            onClick={() => enabled && !busy && void send(cmd)}
          >
            <Icon aria-hidden="true" />
            {busy === cmd ? 'Sending' : label}
          </button>
        ))}
      </div>
      {!onScene && !returning && <p className={s.note}>Speak and life jacket unlock when the drone is on scene.</p>}
    </section>
  )
}
