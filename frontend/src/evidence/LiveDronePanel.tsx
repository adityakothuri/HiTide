import { useEffect, useRef, useState } from 'react'
import { Battery, Camera, Crosshair, Droplets, ExternalLink, Gauge, OctagonX, PlaneLanding, PlaneTakeoff, Play, Radio, Square, Thermometer, Timer } from 'lucide-react'
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

export type CarLevel = 'none' | 'wheels' | 'doors' | 'windows' | 'roof'

/** Contract: docs/api-contract.md, "Gauge tray water level". Estimate fields are null until the first reading. */
export type GaugeStatus = {
  gauge: 'online' | 'offline' | 'unavailable'
  enabled?: boolean
  running?: boolean
  error?: string | null
  ft?: number | null
  ft_range?: [number, number] | null
  confidence?: number | null
  crossing_flooded?: boolean | null
  car_level?: CarLevel | null
  houses_flooded?: number | null
  houses_total?: number | null
  tags_seen?: number | null
  has_baseline?: boolean
  simulated?: boolean | null
  reason?: string | null
  ts?: number | null
  /** Seconds since `ts`; null before any reading. */
  age_s?: number | null
  /** The camera moved since the dry baseline, so the reading uses dye colour only. */
  baseline_moved?: boolean | null
  wet_fraction?: number | null
  /** Where the camera pose came from: the tags, the 4 clicked corners, or the detected tray outline. */
  pose_source?: 'tags' | 'corners' | 'rim' | null
  /** The 4 clicked tray corners (frame px), when set. */
  corners?: [number, number][] | null
}

type GaugeCommand = 'baseline' | 'start' | 'stop'

const OFFLINE_GAUGE: GaugeStatus = { gauge: 'offline' }
const CORNER_PROMPTS = [
  'Click corner 1 on the video: the LEFT end of the FLOOD WATCH edge',
  'Corner 2: the RIGHT end of the FLOOD WATCH edge',
  'Corner 3: the next corner going round (far right)',
  'Corner 4: the last corner (far left)',
]
const FRAME_FALLBACK = { width: 960, height: 720 }
const CAR_SEVERITY: Record<CarLevel, string> = { none: 'sevNone', wheels: 'sevLow', doors: 'sevMid', windows: 'sevHigh', roof: 'sevHigh' }

const POLL_MS = 1_000
const GAUGE_STALE_S = 5
const VIDEO_STALE_S = 4
const LOW_BATTERY = 20
const HOT_C = 80

function clock(seconds = 0) {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

function feet(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function isGaugeStatus(value: unknown): value is GaugeStatus {
  return typeof value === 'object' && value !== null && typeof (value as GaugeStatus).gauge === 'string'
}

/** Polls the gauge once a second; `refresh` re-polls right away (after a button press). */
function useGaugeStatus() {
  const [gauge, setGauge] = useState<GaugeStatus>(OFFLINE_GAUGE)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const response = await fetch('/api/live-drone/gauge', { signal: controller.signal, cache: 'no-store' })
        const body: unknown = response.ok ? await response.json() : null
        setGauge(isGaugeStatus(body) ? body : OFFLINE_GAUGE)
      } catch { if (!controller.signal.aborted) setGauge(OFFLINE_GAUGE) }
      finally { if (!controller.signal.aborted) timer = setTimeout(() => void poll(), POLL_MS) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [tick])

  return { gauge, refresh: () => setTick((value) => value + 1) }
}

function gaugeNote(gauge: GaugeStatus) {
  if (gauge.gauge === 'offline') return 'Tello bridge not running. Start it to read the gauge tray.'
  if (gauge.gauge === 'unavailable') return gauge.error ?? 'The gauge reader is not installed in the bridge.'
  // A valid reading can still carry a caveat in `reason`: show it whenever it is set.
  const fallback = gauge.ft != null ? '' : gauge.enabled ? 'Waiting for the first reading.' : 'Press Start to read the water level.'
  return gauge.reason ?? gauge.error ?? fallback
}

function rangeText(range: [number, number] | null | undefined) {
  if (!range) return 'No range'
  return range[0] === range[1] ? 'At or below normal pool' : `${feet(range[0])}–${feet(range[1])} ft range`
}

function poseText(gauge: GaugeStatus) {
  if (gauge.pose_source === 'tags') return `Tags (${gauge.tags_seen ?? 0})`
  if (gauge.pose_source === 'corners') return 'Clicked corners'
  if (gauge.pose_source === 'rim') return 'Tray outline'
  return gauge.corners ? 'Clicked corners (waiting)' : '—'
}

/** Frame pixel under a click on an <img> drawn with object-fit: cover (centre-cropped). */
function framePoint(img: HTMLImageElement, clientX: number, clientY: number): [number, number] | null {
  const box = img.getBoundingClientRect()
  const nw = img.naturalWidth || FRAME_FALLBACK.width
  const nh = img.naturalHeight || FRAME_FALLBACK.height
  const scale = Math.max(box.width / nw, box.height / nh)
  const x = (clientX - box.left - (box.width - nw * scale) / 2) / scale
  const y = (clientY - box.top - (box.height - nh * scale) / 2) / scale
  return x >= 0 && y >= 0 && x <= nw && y <= nh ? [Math.round(x), Math.round(y)] : null
}

function baselineText(gauge: GaugeStatus) {
  if (gauge.baseline_moved) return 'Camera moved, using dye only'
  return gauge.has_baseline ? 'Captured' : 'None'
}

/** A reading older than GAUGE_STALE_S, or from a stopped reader, must not look live. */
function isStale(gauge: GaugeStatus) {
  return gauge.age_s != null && (gauge.age_s > GAUGE_STALE_S || !gauge.running)
}

type GaugeCardProps = {
  gauge: GaugeStatus
  showOverlay: boolean
  onToggleOverlay: (on: boolean) => void
  onCommand: (command: GaugeCommand) => void
  pending: GaugeCommand | null
  message: string
  messageOk: boolean
  /** Corner picking: start, clear, and whether a live feed is available to click on. */
  picking: boolean
  canPick: boolean
  onPickCorners: () => void
  onClearCorners: () => void
}

/** When Start (or Stop) disables itself, move focus to the button that now does something. */
function useHandOffFocus(enabled: boolean | undefined) {
  const startRef = useRef<HTMLButtonElement>(null)
  const stopRef = useRef<HTMLButtonElement>(null)
  const handOff = useRef<'start' | 'stop' | null>(null)
  useEffect(() => {
    if (handOff.current === 'start' && enabled) stopRef.current?.focus()
    if (handOff.current === 'stop' && !enabled) startRef.current?.focus()
    if ((handOff.current === 'start') === Boolean(enabled)) handOff.current = null
  }, [enabled])
  const handOffFrom = (button: 'start' | 'stop') => { handOff.current = button }
  return { startRef, stopRef, handOffFrom }
}

function GaugeCard({ gauge, showOverlay, onToggleOverlay, onCommand, pending, message, messageOk, picking, canPick,
  onPickCorners, onClearCorners }: GaugeCardProps) {
  const online = gauge.gauge === 'online'
  const hasLevel = online && gauge.ft != null
  const confidence = Math.round((gauge.confidence ?? 0) * 100)
  const note = gaugeNote(gauge)
  const stale = online && isStale(gauge)
  const { startRef, stopRef, handOffFrom } = useHandOffFocus(gauge.enabled)
  const reading = hasLevel ? `${feet(gauge.ft ?? 0)} ft` : '— ft'
  const range = hasLevel ? rangeText(gauge.ft_range) : 'No reading'
  const crossing = gauge.crossing_flooded == null ? '—' : gauge.crossing_flooded ? 'Flooded' : 'Clear'
  const houses = gauge.houses_flooded == null ? '—' : `${gauge.houses_flooded} / ${gauge.houses_total ?? '?'}`
  const carLevel = gauge.car_level
    ? <span className={`${s.levelTag} ${s[CAR_SEVERITY[gauge.car_level]]}`}>{gauge.car_level}</span>
    : '—'
  return (
    <section className={`${s.gauge} ${stale ? s.gaugeStale : ''}`} aria-labelledby="gauge-heading">
      <div className={s.gaugeHead}>
        <h3 id="gauge-heading"><Droplets size={15} />Water gauge</h3>
        {gauge.simulated ? <span className={s.simTag}>SIMULATED</span> : null}
        {!online && <span className={s.cachedTag}>{gauge.gauge === 'unavailable' ? 'Unavailable' : 'Offline'}</span>}
      </div>
      <div className={s.gaugeReading} aria-live="polite">
        <strong>{reading}</strong>
        <span>{range}</span>
      </div>
      {stale && <p className={s.gaugeAge}>Last reading {Math.round(gauge.age_s ?? 0)}s ago</p>}
      <p className={s.gaugeNote} role="status">{note}</p>
      <dl className={s.gaugeFacts}>
        <div><dt>Car level</dt><dd>{carLevel}</dd></div>
        <div><dt>Crossing</dt><dd className={gauge.crossing_flooded ? s.flooded : ''}>{crossing}</dd></div>
        <div><dt>Houses flooded</dt><dd>{houses}</dd></div>
        <div><dt>Dry baseline</dt><dd className={gauge.baseline_moved ? s.baselineMoved : ''}>{baselineText(gauge)}</dd></div>
        <div><dt>Pose from</dt><dd>{poseText(gauge)}</dd></div>
      </dl>
      <div className={s.confidence}>
        <span id="gauge-confidence-label">Confidence {gauge.confidence == null ? '—' : `${confidence}%`}</span>
        <div className={s.confidenceBar} role="meter" aria-labelledby="gauge-confidence-label"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={confidence}
          aria-valuetext={gauge.confidence == null ? 'no reading' : `${confidence}%`}>
          <div style={{ width: `${confidence}%` }} />
        </div>
      </div>
      <div className={s.gaugeButtons}>
        <button className={s.land} disabled={!online || pending !== null} onClick={() => onCommand('baseline')}
          aria-label="Capture dry baseline" title="Before pouring water: capture the dry tray from this exact camera pose"><Camera size={15} />Capture dry baseline</button>
        <button ref={startRef} className={s.launch} disabled={!online || Boolean(gauge.enabled) || pending !== null}
          aria-label="Start water gauge reading"
          onClick={() => { handOffFrom('start'); onCommand('start') }}><Play size={15} />Start</button>
        <button ref={stopRef} className={s.land} disabled={!online || !gauge.enabled || pending !== null}
          aria-label="Stop water gauge reading"
          onClick={() => { handOffFrom('stop'); onCommand('stop') }}><Square size={15} />Stop</button>
        <button className={s.land} disabled={!online || !canPick || picking} onClick={onPickCorners} aria-label="Set tray corners"
          title="No readable tags? Click the 4 tray corners on the live video"><Crosshair size={15} />Set tray corners</button>
        <button className={s.land} disabled={!online || !gauge.corners} onClick={onClearCorners}>Clear corners</button>
      </div>
      <label className={s.overlayToggle}>
        <input type="checkbox" checked={showOverlay} disabled={!online} onChange={(event) => onToggleOverlay(event.target.checked)} />
        Show the gauge overlay in the feed
      </label>
      <p role="status" aria-live="polite" className={messageOk ? s.messageOk : s.message}>{message}</p>
    </section>
  )
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
  const { gauge, refresh: refreshGauge } = useGaugeStatus()
  const [overlayWanted, setOverlayWanted] = useState(false)
  const [gaugePending, setGaugePending] = useState<GaugeCommand | null>(null)
  const [gaugeMessage, setGaugeMessage] = useState('')
  const [gaugeMessageOk, setGaugeMessageOk] = useState(false)
  const [brokenOverlayTs, setBrokenOverlayTs] = useState<number | null>(null)
  const [picks, setPicks] = useState<{ frame: [number, number]; dot: [number, number] }[] | null>(null)
  const feedImage = useRef<HTMLImageElement>(null)

  useEffect(() => {
    if (!picks) return undefined
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { setPicks(null); setGaugeMessage('Corner picking cancelled'); setGaugeMessageOk(false) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [picks])

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

  async function sendGauge(command: GaugeCommand) {
    setGaugePending(command); setGaugeMessage(''); setGaugeMessageOk(false)
    try {
      const response = await fetch(`/api/live-drone/gauge/${command}`, { method: 'POST' })
      const body = await response.json() as { result?: string; detail?: string }
      const ok = response.ok && body.result === 'ok'
      if (!response.ok) setGaugeMessage(body.detail ?? `Request failed (${response.status})`)
      else if (command === 'baseline') setGaugeMessage(ok ? 'Dry baseline captured' : `Baseline refused: ${body.result}`)
      else setGaugeMessage(ok ? '' : `Gauge: ${body.result}`)
      setGaugeMessageOk(ok)
    } catch { setGaugeMessage('Could not reach the backend.') }
    finally { setGaugePending(null); refreshGauge() }
  }

  async function postCorners(body: { points: [number, number][] } | { clear: true }) {
    try {
      const response = await fetch('/api/live-drone/gauge/corners', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      const data = await response.json() as { result?: string; detail?: unknown }
      if (!response.ok) return typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`
      return data.result ?? 'no answer'
    } catch { return 'Could not reach the backend.' }
  }

  function startPicking() {
    setOverlayWanted(false)  // clicks must land on the live feed, not the overlay
    setPicks([])
    setGaugeMessage(`${CORNER_PROMPTS[0]} (Esc to cancel)`); setGaugeMessageOk(true)
  }

  async function clearCorners() {
    setPicks(null)
    const answer = await postCorners({ clear: true })
    setGaugeMessage(answer === 'ok' ? 'Corners cleared: using tags or the automatic outline' : `Clear failed: ${answer}`)
    setGaugeMessageOk(answer === 'ok'); refreshGauge()
  }

  async function pickAt(event: React.MouseEvent<HTMLDivElement>) {
    const img = feedImage.current
    if (!picks || !img) return
    const point = framePoint(img, event.clientX, event.clientY)
    if (!point) return
    const box = event.currentTarget.getBoundingClientRect()
    const next = [...picks, { frame: point, dot: [event.clientX - box.left, event.clientY - box.top] as [number, number] }]
    if (next.length < CORNER_PROMPTS.length) {
      setPicks(next); setGaugeMessage(CORNER_PROMPTS[next.length]); setGaugeMessageOk(true)
      return
    }
    setPicks(null)
    const answer = await postCorners({ points: next.map((p) => p.frame) })
    setGaugeMessage(answer === 'ok'
      ? 'Corners set. Turn on the overlay and check the FLOOD WATCH / RIVER labels sit on the right edges, then capture the dry baseline.'
      : `Corners refused: ${answer}`)
    setGaugeMessageOk(answer === 'ok'); refreshGauge()
  }

  // The overlay exists only after a reading; its ts changes per reading, which reloads the image.
  // An overlay that fails to load (no JPEG for that reading) falls back to the feed until the next reading.
  const showOverlay = overlayWanted && gauge.gauge === 'online' && gauge.ts != null && gauge.ts !== brokenOverlayTs
  const batteryLow = (status?.battery ?? 100) <= LOW_BATTERY
  const hot = (status?.temp ?? 0) >= HOT_C
  return (
    <section className={s.panel} aria-labelledby="live-drone-heading">
      <div className={s.heading}>
        <div><p className={s.eyebrow}>VERIFY FROM THE AIR</p><h2 id="live-drone-heading">Live drone</h2></div>
        <span className={feed.live ? s.liveTag : s.cachedTag}><Radio size={13} />{feed.label}</span>
      </div>
      <div className={s.body}>
        <div className={`${s.feed} ${picks ? s.feedPicking : ''}`} onClick={(event) => void pickAt(event)}>
          {picks?.map((p, i) => <span key={i} className={s.cornerDot} style={{ left: p.dot[0], top: p.dot[1] }}>{i + 1}</span>)}
          {showOverlay
            ? <img src={`/api/live-drone/gauge/overlay.jpg?t=${gauge.ts}`} alt="Gauge tray overlay: detected tags and flooded cells tinted"
                onError={() => setBrokenOverlayTs(gauge.ts ?? null)} />
            : feed.live
            ? <img ref={feedImage} key={streamKey} src="/api/live-drone/video" alt="Live camera feed from the drone" />
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
          <GaugeCard gauge={gauge} showOverlay={overlayWanted} onToggleOverlay={setOverlayWanted}
            onCommand={(command) => void sendGauge(command)} pending={gaugePending} message={gaugeMessage}
            messageOk={gaugeMessageOk} picking={picks !== null} canPick={feed.live}
            onPickCorners={startPicking} onClearCorners={() => void clearCorners()} />
        </div>
      </div>
    </section>
  )
}
