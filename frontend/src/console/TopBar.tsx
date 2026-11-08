import { useEffect, useState } from 'react'
import type { Feeds } from '../data/types'
import { formatClock, sentenceCase } from '../lib/format'
import { useApp, useStore, useUi } from '../state/StoreContext'
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

/** Brand, the active warning, and connection status. Nothing else. */
export function TopBar({ compact, replayWarning }: { compact: boolean; replayWarning?: WxWarning | null }) {
  const alert = useApp((a) => a.alert)
  const status = useUi((u) => u.status)
  const feeds = useFeeds()
  const active = alert?.active ? alert : null
  const area = active ? areaOf(active.headline) : null
  const nws = feeds?.nws_alerts?.fetched_at
  const usgs = feeds?.usgs_gage?.fetched_at
  const feedTitle = nws || usgs ? `NWS ${nws ? formatClock(nws) : 'unavailable'}, USGS ${usgs ? formatClock(usgs) : 'unavailable'}` : undefined

  if (replayWarning !== undefined) {
    return (
      <header className={`${s.bar} ${compact ? s.compact : ''}`}>
        <Brand />
        <p className={s.warning} role="status">
          {replayWarning ? (
            <>
              <span className={s.warningDot} aria-hidden="true" />
              <span className={s.warningText}>{replayWarning.event}, {replayWarning.area}</span>
              <span className={`${s.issued} num`}>Issued {wxClock(replayWarning.issuedAt)}</span>
            </>
          ) : (
            <span className={s.warningText}>No active warnings, Kerr County</span>
          )}
        </p>
        <ConnStatus status={status} title={feedTitle} />
      </header>
    )
  }

  return (
    <header className={`${s.bar} ${compact ? s.compact : ''}`}>
      <Brand />

      <p className={s.warning} role="status">
        {active ? (
          <>
            <span className={s.warningDot} aria-hidden="true" />
            <span className={s.warningText}>
              {sentenceCase(active.event)}
              {area && `, ${area}`}
            </span>
            {active.simulated && <span className={s.warningSim}>Simulated</span>}
          </>
        ) : (
          <span className={s.warningText}>No active warnings, Kerr County</span>
        )}
      </p>

      <ConnStatus status={status} title={feedTitle} />
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
