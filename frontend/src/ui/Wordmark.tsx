import s from './Wordmark.module.css'

/** Text wordmark plus a neutral placeholder mark. Not State Farm's logo. */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={s.wordmark}>
      <svg className={s.mark} viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="6" />
        <path d="M6 21c3 0 3-2 5-2s2 2 5 2 3-2 5-2 2 2 5 2" />
      </svg>
      <span className={compact ? s.textCompact : s.text}>State Farm Flood Watch</span>
    </span>
  )
}
