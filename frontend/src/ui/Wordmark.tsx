import { LogoMark } from './LogoMark'
import s from './Wordmark.module.css'

/** HiTide wordmark: the shield-and-wave logo with the product name. Deliberately not State Farm's three-oval logo. */
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`${s.wordmark} ${compact ? s.compact : ''}`}>
      <LogoMark size={compact ? 22 : 26} />
      <span className={s.text}>
        <span className={s.brand}>State Farm</span> <span className={s.product}>HiTide</span>
      </span>
    </span>
  )
}
