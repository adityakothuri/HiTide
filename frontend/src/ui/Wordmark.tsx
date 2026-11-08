import { LogoMark } from './LogoMark'
import s from './Wordmark.module.css'

/** HiTide brand: the shield-and-wave logo on its own, large. The name is for screen readers only. */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`${s.wordmark} ${compact ? s.compact : ''}`} role="img" aria-label="HiTide">
      <LogoMark size={compact ? 30 : 40} />
    </span>
  )
}
