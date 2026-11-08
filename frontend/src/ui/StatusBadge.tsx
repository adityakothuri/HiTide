import { TONE_ICON, TONE_LABEL, type Tone } from './status'
import s from './StatusBadge.module.css'

/** Status is always icon + label + color, never color alone. */
export function StatusBadge({ tone, label, quiet = false }: { tone: Tone; label?: string; quiet?: boolean }) {
  const Icon = TONE_ICON[tone]
  return (
    <span className={`${s.badge} ${s[tone]} ${quiet ? s.quiet : ''}`}>
      <Icon className={s.icon} aria-hidden="true" strokeWidth={2.25} />
      {label ?? TONE_LABEL[tone]}
    </span>
  )
}
