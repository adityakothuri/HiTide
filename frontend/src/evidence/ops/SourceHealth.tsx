import { CircleAlert, CircleCheck, CircleDashed, CircleX, FlaskConical } from 'lucide-react'
import type { EvidenceState } from '../types'
import { bySourceHealth, secondsAgo, sourceStatus, type SourceTone } from './derive'
import s from './ops.module.css'

const TONE_ICON: Record<SourceTone, typeof CircleCheck> = {
  current: CircleCheck,
  partial: CircleAlert,
  down: CircleX,
  idle: CircleDashed,
  simulated: FlaskConical,
}

const CATEGORY_TEXT: Record<string, string> = {
  warning: 'Warnings, watches, and advisories',
  gauge: 'River and stream data',
  closure: 'Road closures and restrictions',
  context: 'Flood impact reference points',
  report: 'Operator and community reports',
  drone: 'Inspection imagery',
}

interface Props {
  state: EvidenceState
  now: number
  onReturnToTown: () => void
  busy: boolean
}

/** Real sources first; synthetic exercise feeds are summarized as one entry. */
export function SourceHealth({ state, now, onReturnToTown, busy }: Props) {
  const real = state.sources.filter((src) => sourceStatus(src).tone !== 'simulated').sort(bySourceHealth)
  const simulatedCount = state.sources.length - real.length
  return (
    <footer id="source-health" className={s.sourceBar} aria-labelledby="source-heading">
      <h2 id="source-heading" className={s.sourceTitle}>Source health</h2>
      <ul className={s.sourceList}>
        {real.map((src, i) => {
          const status = sourceStatus(src)
          const Icon = TONE_ICON[status.tone]
          const when = src.last_successful_fetch_at ?? src.last_success_at ?? src.last_attempt_at ?? src.fetched_at
          return (
            <li key={src.id ?? src.source_id ?? i} className={s.source} title={src.detail ?? undefined}>
              <span className={s.sourceHead}>
                <strong>{src.name ?? src.id ?? src.source_id}</strong>
                <span className={`${s.sourceStatus} ${s[`src_${status.tone}`]}`}><Icon size={15} aria-hidden />{status.label}</span>
              </span>
              <small>{CATEGORY_TEXT[(src as { category?: string }).category ?? ''] ?? 'Evidence source'} · {when ? `Updated ${secondsAgo(when, now)}` : 'No successful fetch yet'}</small>
            </li>
          )
        })}
        {!real.length && <li className={s.muted}>No source runs recorded yet.</li>}
      </ul>
      {state.dataset.simulated ? (
        <span className={s.simBadge}>
          Synthetic exercise{simulatedCount ? ` · ${simulatedCount} simulated feeds` : ''}
          <button type="button" className={s.linkButton} onClick={onReturnToTown} disabled={busy}>Return to Kerrville roads</button>
        </span>
      ) : null}
    </footer>
  )
}
