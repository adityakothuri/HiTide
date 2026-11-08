import { useEffect, useRef, useState } from 'react'
import { Battery, ExternalLink, Gauge, OctagonX, PlaneLanding, PlaneTakeoff, Radio, Thermometer, Timer } from 'lucide-react'
import s from './LiveDronePanel.module.css'

/** Contract: docs/api-contract.md, "Live drone". Fields after controls_url exist only when bridge is online. */
export type LiveDroneStatus = {
  bridge: 'online' | 'offline' | 'outdated'
  fallback_image_url: string
  controls_url: string
  connected?: boolean
  flying?: boolean
  busy?: '' | 'takeoff' | 'land'
  battery?: number
  temp?: number
  height?: number
  flight_time?: number
  video_age?: number | null
  log?: string[]
}

type Action = 'takeoff' | 'land' | 'emergency'

const POLL_MS = 1_000
const VIDEO_STALE_S = 4
const LOW_BATTERY = 20
const HOT_C = 80

function clock(seconds = 0) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function feedState(status: LiveDroneStatus | null) {
  if (!status || status.bridge === 'offline') return { live: false, label: 'Cached footage', note: 'No live drone connected. Start the Tello bridge to stream the real drone.' }
  if (status.bridge === 'outdated') return { live: false, label: 'Bridge outdated', note: 'Restart the Tello dashboard so it reports connection state.' }
  if (!status.connected) return { live: false, label: 'Link lost', note: 'Bridge running, no telemetry from the drone. Is the laptop on the TELLO Wi-Fi and the drone on?' }
  const videoFresh = status.video_age != null && status.video_age < VIDEO_STALE_S
  return videoFresh ? { live: true, label: 'Live', note: '' } : { live: false, label: 'Acquiring video', note: 'Drone connected. Waiting for the camera feed.' }
}

export function LiveDronePanel() {
  const [status, setStatus] = useState<LiveDroneStatus | null>(null)
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState<Action | null>(null)
  const [streamKey, setStreamKey] = useState(0)
  const wasLive = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const response = await fetch('/api/live-drone/status', { signal: controller.signal, cache: 'no-store' })
        if (response.ok) {
          const next = await response.json() as LiveDroneStatus
          // Reopen the MJPEG stream whenever the feed comes back, so a reconnect shows fresh video.
          const live = feedState(next).live
          if (live && !wasLive.current) setStreamKey((key) => key + 1)
          wasLive.current = live
          setStatus(next)
        }
      } catch { /* backend unreachable: keep the last status; the console header already reports it */ }
      finally { if (!controller.signal.aborted) timer = setTimeout(() => void poll(), POLL_MS) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [])

  const feed = feedState(status)
  const online = status?.bridge === 'online'
  const airborne = Boolean(status?.flying || status?.busy === 'takeoff')

  async function send(action: Action) {
    setPending(action); setMessage('')
    try {
      const response = await fetch(`/api/live-drone/action/${action}`, { method: 'POST' })
      const body = await response.json() as { result?: string; detail?: string }
      setMessage(response.ok ? (body.result === 'ok' ? '' : `Drone: ${body.result}`) : (body.detail ?? `Request failed (${response.status})`))
    } catch { setMessage('Could not reach the backend.') }
    finally { setPending(null) }
  }

  const batteryLow = (status?.battery ?? 100) <= LOW_BATTERY
  const hot = (status?.temp ?? 0) >= HOT_C
  return (
    <section className={s.panel} aria-labelledby="live-drone-heading">
      <div className={s.heading}>
        <div><p className={s.eyebrow}>VERIFY FROM THE AIR</p><h2 id="live-drone-heading">Live drone</h2></div>
        <span className={feed.live ? s.liveTag : s.cachedTag}><Radio size={13} />{feed.label}</span>
      </div>
      <div className={s.body}>
        <div className={s.feed}>
          {feed.live
            ? <img key={streamKey} src="/api/live-drone/video" alt="Live camera feed from the drone" />
            : <img src={status?.fallback_image_url ?? '/static/drone/flood_03.jpg'} alt="Cached drone image of a flooded road (not live)" />}
          {!feed.live && <p className={s.feedNote}><strong>{feed.label === 'Cached footage' ? 'CACHED · NOT LIVE' : feed.label.toUpperCase()}</strong>{feed.note}</p>}
        </div>
        <div className={s.side}>
          <dl className={s.telemetry}>
            <div className={batteryLow ? s.warn : ''}><dt><Battery size={14} />Battery</dt><dd>{online ? `${status?.battery ?? 0}%` : '—'}</dd></div>
            <div><dt><Gauge size={14} />Altitude</dt><dd>{online ? `${status?.height ?? 0} cm` : '—'}</dd></div>
            <div className={hot ? s.warn : ''}><dt><Thermometer size={14} />Temperature</dt><dd>{online ? `${status?.temp ?? 0} °C` : '—'}</dd></div>
            <div><dt><Timer size={14} />Flight time</dt><dd>{online ? clock(status?.flight_time) : '—'}</dd></div>
          </dl>
          <div className={s.controls}>
            <button className={s.launch} disabled={!online || !status?.connected || airborne || Boolean(status?.busy) || pending !== null}
              onClick={() => void send('takeoff')}><PlaneTakeoff size={16} />{status?.busy === 'takeoff' ? 'Launching…' : 'Launch'}</button>
            {/* Land is never blocked by an in-progress takeoff: it must always be reachable. */}
            <button className={airborne ? s.landHot : s.land} disabled={!online || status?.busy === 'land'}
              onClick={() => void send('land')}><PlaneLanding size={16} />{status?.busy === 'land' ? 'Landing…' : 'Land'}</button>
            <button className={s.kill} disabled={!online} onClick={() => void send('emergency')}
              title="Cuts all motors immediately. The drone will fall."><OctagonX size={16} />Emergency motor stop</button>
          </div>
          <p role="status" aria-live="polite" className={s.message}>{message}</p>
          {online && <a className={s.controlsLink} href={status?.controls_url} target="_blank" rel="noopener noreferrer">
            Full flight controls (keyboard, hover drift log)<ExternalLink size={13} /></a>}
          {online && status?.log?.length ? <ul className={s.log} aria-label="Drone event log">{status.log.slice(0, 3).map((line) => <li key={line}>{line}</li>)}</ul> : null}
        </div>
      </div>
    </section>
  )
}
