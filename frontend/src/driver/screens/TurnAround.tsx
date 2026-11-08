import { OctagonAlert, Route as RouteIcon, Volume2, VolumeX } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../../state/StoreContext'
import type { Town } from '../../data/types'
import { formatDepth, formatDistance } from '../../lib/format'
import { streetOf } from '../../lib/geo'
import { speak, spokenAlertsOn, stopSpeaking } from '../speech'
import type { DriverView } from '../useDriverView'
import s from './TurnAround.module.css'

/** Full-screen en-route alert. Speaks the backend's message once and moves focus to the action. */
export function TurnAround({ view, town }: { view: DriverView; town: Town | null }) {
  const store = useStore()
  const ta = view.turnAround
  const actionRef = useRef<HTMLButtonElement>(null)
  const [speaking, setSpeaking] = useState(false)
  const message = ta?.message ?? 'Flooded road ahead. Turn around.'

  useEffect(() => {
    actionRef.current?.focus()
    if (spokenAlertsOn()) speak(message, setSpeaking)
    return () => stopSpeaking()
  }, [message])

  if (!ta) return null
  const street = streetOf(town, ta.hazard_edge_id)
  const [first, ...rest] = message.split('. ')

  const dismiss = () => {
    stopSpeaking()
    store.setUi((u) => ({
      ...u,
      turnDismissed: { ...u.turnDismissed, [view.driverId]: true },
      routeAccepted: { ...u.routeAccepted, [view.driverId]: true },
    }))
  }

  const toggleVoice = () => {
    if (speaking) {
      stopSpeaking()
      setSpeaking(false)
    } else {
      speak(message, setSpeaking)
    }
  }

  return (
    <div className={`${s.takeover} on-dark`} role="alertdialog" aria-modal="true" aria-labelledby="ta-title" aria-describedby="ta-detail">
      <div className={s.body}>
        <OctagonAlert className={s.icon} aria-hidden="true" strokeWidth={2} />
        <p className={s.kicker}>Critical alert</p>
        <h2 id="ta-title" className={s.title}>
          {first.replace(/\.$/, '')}.
          {rest.length > 0 && <><br />{rest.join('. ')}</>}
        </h2>
        <div id="ta-detail" className={s.detail}>
          <p>{street ? `${street}, ` : ''}{formatDistance(ta.distance_m)} ahead</p>
          <p>About {formatDepth(ta.hazard_depth_in)} of water</p>
        </div>
        <button type="button" className={s.voice} onClick={toggleVoice} aria-pressed={speaking}>
          {speaking ? <Volume2 aria-hidden="true" /> : <VolumeX aria-hidden="true" />}
          {speaking ? 'Speaking this alert. Tap to stop.' : 'Tap to hear this alert'}
        </button>
      </div>
      <div>
        <button ref={actionRef} type="button" className={s.action} onClick={dismiss}>
          <RouteIcon aria-hidden="true" />
          Show new route
        </button>
      </div>
    </div>
  )
}
