import { AlertTriangle, Clock } from 'lucide-react'
import { useEffect, useState, type JSX } from 'react'
import type { Feeds } from '../data/types'
import { formatClock, sentenceCase } from '../lib/format'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { DataModeBadge } from '../ui/DataModeBadge'
import { Wordmark } from '../ui/Wordmark'
import { wxClock } from '../wx/time'
import type { WxWarning } from '../wx/types'
import s from './TopBar.module.css'

const FEED_REFRESH_MS = 60_000

function useFeeds(): Feeds | null {
  const store = useStore()
  const [feeds, setFeeds] = useState<Feeds | null>(null)
  useEffect(() => {
    let alive = true
    const load = () => store.provider.getFeeds().then((f) => alive && setFeeds(f), () => undefined)
    void load()
    const id = window.setInterval(load, FEED_REFRESH_MS)
    return () => {
      alive = false
      window.clearInterval(id)
    }
  }, [store])
  return feeds
}

function areaOf(headline: string): string | null {
  return /for ([A-Z][\w ]*?County)/.exec(headline)?.[1] ?? null
}

const STATUS_TEXT = { live: 'Live', connecting: 'Connecting', reconnecting: 'Reconnecting', offline_demo: 'Offline demo' } as const

/** The active warning, the data time, and connection status. Used in the shell header and in /present. */
export function HeaderStatus({ replayWarning, dataTime, connection }: { replayWarning?: WxWarning | null; dataTime?: number | null; connection?: keyof typeof STATUS_TEXT }) {
  const alert = useApp((a) => a.alert)
  const storeStatus = useUi((u) => u.status)
  // The monitor polls the region API, so its own reachability is the status that matters there.
  const status = connection ?? storeStatus
  const feeds = useFeeds()
  const nws = feeds?.nws_alerts?.fetched_at
  const usgs = feeds?.usgs_gage?.fetched_at
  const feedTitle = nws || usgs ? `NWS ${nws ? formatClock(nws) : 'unavailable'}, USGS ${usgs ? formatClock(usgs) : 'unavailable'}` : undefined
  const stale = status === 'reconnecting'

  let warning: JSX.Element
  const hasWarning = replayWarning !== undefined ? Boolean(replayWarning) : Boolean(alert?.active)
  if (replayWarning !== undefined) {
    warning = replayWarning ? (
      <>
        <AlertTriangle size={14} className={s.warningIcon} aria-hidden="true" />
        <span className={s.warningText}>{replayWarning.event}, {replayWarning.area}</span>
        <span className={`${s.issued} num`}>issued {wxClock(replayWarning.issuedAt)}</span>
      </>
    ) : (
      <span className={s.warningText}>No active warnings, Kerr County</span>
    )
  } else {
    const active = alert?.active ? alert : null
    const area = active ? areaOf(active.headline) : null
    warning = active ? (
      <>
        <AlertTriangle size={14} className={s.warningIcon} aria-hidden="true" />
        <span className={s.warningText}>
          {sentenceCase(active.event)}
          {area && `, ${area}`}
        </span>
      </>
    ) : (
      <span className={s.warningText}>No active warnings, Kerr County</span>
    )
  }

  return (
    <>
      <p className={`${s.warning} ${hasWarning ? s.warningOn : ''}`} role="status">{warning}</p>
      {dataTime != null && (
        <span className={`${s.updated} ${stale ? s.stale : ''} num`} title={stale ? 'Data may be out of date' : undefined}>
          {stale && <Clock size={12} aria-hidden="true" />}
          Data {wxClock(dataTime)}
        </span>
      )}
      <DataModeBadge className={s.modeBadge} />
      <ConnStatus status={status} title={feedTitle} />
    </>
  )
}

/** Compact bar for /present: brand plus the same status. */
export function TopBar({ compact, replayWarning }: { compact: boolean; replayWarning?: WxWarning | null }) {
  return (
    <header className={`${s.bar} ${compact ? s.compact : ''}`}>
      <Brand />
      <HeaderStatus replayWarning={replayWarning} />
    </header>
  )
}

function Brand() {
  return (
    <div className={s.brand}>
      <Wordmark compact />
      <span className={s.product}>Flood operations</span>
    </div>
  )
}

function ConnStatus({ status, title }: { status: keyof typeof STATUS_TEXT; title?: string }) {
  return (
    <span className={`${s.conn} ${status === 'live' ? s.connLive : status === 'reconnecting' ? s.connWarn : ''}`} role="status" title={title}>
      <span className={s.connDot} aria-hidden="true" />
      {STATUS_TEXT[status]}
    </span>
  )
}
