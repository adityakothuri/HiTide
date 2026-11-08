import { Undo2 } from 'lucide-react'
import { useState } from 'react'
import { formatEta } from '../lib/eta'
import type { DroneWithTrail } from '../state/reducer'
import { useStore } from '../state/StoreContext'
import { useToast } from '../ui/Toast'
import s from './Detail.module.css'

const STATUS: Record<DroneWithTrail['status'], string> = {
  launching: 'Launching',
  en_route: 'En route',
  on_scene: 'Over the location',
  returning: 'Returning to station',
}

/**
 * Drone status for a case. Drones map the flood and report cars in the water to emergency services.
 * They fly to the car's GPS fix and do not know whose car it is; they carry no payload or loudspeaker.
 */
export function DronePanel({ drone, caseId, target }: { drone: DroneWithTrail; caseId: string; target: { lat: number; lon: number } }) {
  const store = useStore()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const onScene = drone.status === 'on_scene'
  const returning = drone.status === 'returning'

  const recall = async () => {
    setBusy(true)
    try {
      await store.provider.droneCommand(drone.id, caseId, 'return')
      toast('Drone returning', 'Heading back to Kerrville Fire Station 1.')
    } catch {
      toast('Drone command failed', 'Check the backend connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  const where = onScene ? 'Over the location' : returning ? 'Returning to base' : `Arrives in ${formatEta(drone.eta_s)}`

  return (
    <section className={s.section} aria-labelledby="drone-h">
      <div className={s.sectionHead}>
        <h3 id="drone-h" className={s.sectionTitle}>Drone</h3>
        <span className={s.sectionAside}>{STATUS[drone.status]}</span>
      </div>

      <dl className={s.facts}>
        <div>
          <dt>Target</dt>
          <dd className="num">Car GPS {target.lat.toFixed(4)}, {target.lon.toFixed(4)}</dd>
        </div>
        <div>
          <dt>Drone</dt>
          <dd className="num">{where}</dd>
        </div>
        {drone.crew_eta_s != null && (
          <div>
            <dt>Ground crew</dt>
            <dd className="num">Arrives in {formatEta(drone.crew_eta_s)}</dd>
          </div>
        )}
      </dl>

      <p className={s.note}>
        Maps the flooded area around the GPS fix. If it sees a car in the water it calls emergency services with that location.
      </p>

      {!returning && (
        <div className={s.actions} role="group" aria-label="Drone actions">
          <button type="button" className={s.action} aria-disabled={busy} onClick={() => !busy && void recall()}>
            <Undo2 aria-hidden="true" />
            {busy ? 'Sending' : 'Recall drone'}
          </button>
        </div>
      )}
    </section>
  )
}
