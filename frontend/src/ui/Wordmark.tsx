import s from './Wordmark.module.css'

/** HiTide wordmark: the shield-and-wave logo plus the name. */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={s.wordmark}>
      <img className={compact ? s.markCompact : s.mark} src="/hitide-logo.png" alt="" width={28} height={28} />
      <span className={compact ? s.textCompact : s.text}>HiTide</span>
    </span>
  )
}
