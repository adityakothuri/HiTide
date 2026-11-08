import s from './Wordmark.module.css'

/**
 * Text wordmark with a neutral placeholder mark (a shield with a waterline). Deliberately not
 * State Farm's three-oval logo.
 */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`${s.wordmark} ${compact ? s.compact : ''}`}>
      <svg className={s.mark} viewBox="0 0 24 24" aria-hidden="true">
        <path className={s.shield} d="M12 2.5 4.5 5.4v5.9c0 4.6 3.1 8.6 7.5 10.2 4.4-1.6 7.5-5.6 7.5-10.2V5.4Z" />
        <path className={s.wave} d="M7.5 13.2c1.1 0 1.1-.9 2.25-.9s1.1.9 2.25.9 1.1-.9 2.25-.9 1.1.9 2.25.9" />
      </svg>
      <span className={s.text}>
        <span className={s.brand}>State Farm</span> <span className={s.product}>Flood Watch</span>
      </span>
    </span>
  )
}
