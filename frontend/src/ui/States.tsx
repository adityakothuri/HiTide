import { CircleAlert, Clock, RotateCw, WifiOff } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ConnectionStatus } from '../data/provider'
import { formatClock, formatRelative } from '../lib/format'
import { isStale } from '../lib/staleness'
import { Button } from './Button'
import s from './States.module.css'

/** Wrap skeletons in this so screen readers hear "Loading". */
export function Loading({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div aria-busy="true">
      <span className="visually-hidden" role="status">{label}</span>
      {children}
    </div>
  )
}

export function Skeleton({ width = '100%', height = 16, radius = 'sm' }: { width?: number | string; height?: number; radius?: 'sm' | 'md' }) {
  return <span className={`${s.skeleton} ${s[radius]}`} style={{ width, height }} aria-hidden="true" />
}

/** Empty states give an instruction, not a mood. */
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={s.empty}>
      <p className={s.emptyTitle}>{title}</p>
      {children && <p className={s.emptyText}>{children}</p>}
      {action}
    </div>
  )
}

/** Says what failed and how to recover. */
export function ErrorState({ what, how, onRetry }: { what: string; how: string; onRetry?: () => void }) {
  return (
    <div className={s.error} role="alert">
      <CircleAlert className={s.errorIcon} aria-hidden="true" />
      <div className={s.errorBody}>
        <p className={s.emptyTitle}>{what}</p>
        <p className={s.emptyText}>{how}</p>
        {onRetry && (
          <Button variant="secondary" icon={RotateCw} onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </div>
  )
}

/** "NWS 8:41 PM". Turns caution-colored with a clock icon once older than 5 minutes. */
export function StaleIndicator({ label, iso, now }: { label: string; iso: string | null | undefined; now: number }) {
  const stale = isStale(iso, now)
  if (!iso) {
    return <span className={`${s.fresh} ${s.stale}`}><Clock className={s.smallIcon} aria-hidden="true" />{label} unavailable</span>
  }
  return (
    <span className={`${s.fresh} ${stale ? s.stale : ''}`} title={stale ? `${label} data is more than 5 minutes old` : undefined}>
      {stale && <Clock className={s.smallIcon} aria-hidden="true" />}
      <span>{label}</span>
      <span className="num">{stale ? `updated ${formatRelative(iso, now)}` : formatClock(iso)}</span>
    </span>
  )
}

const STATUS_COPY: Record<ConnectionStatus, string> = {
  connecting: 'Connecting',
  live: 'Live data',
  reconnecting: 'Reconnecting to backend',
  offline_demo: 'Offline demo data',
}

export function ConnectionChip({ status }: { status: ConnectionStatus }) {
  const off = status !== 'live'
  return (
    <span className={`${s.chip} ${status === 'reconnecting' ? s.chipWarn : ''}`} role="status">
      {off ? <WifiOff className={s.smallIcon} aria-hidden="true" /> : <span className={s.liveDot} aria-hidden="true" />}
      {STATUS_COPY[status]}
    </span>
  )
}
