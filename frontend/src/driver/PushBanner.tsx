import { useEffect } from 'react'
import type { OutreachEvent } from '../data/types'
import s from './PushBanner.module.css'

const SHOW_MS = 7000

/** The pre-trip text as it lands on the lock screen: a notification banner that opens the warning. */
export function PushBanner({ message, onOpen, onDismiss }: { message: OutreachEvent; onOpen: () => void; onDismiss: () => void }) {
  useEffect(() => {
    const t = window.setTimeout(onDismiss, SHOW_MS)
    return () => window.clearTimeout(t)
  }, [onDismiss])

  const body = message.body.replace(/^State Farm Flood Watch:\s*/, '')
  return (
    <div className={s.wrap} role="status" data-push>
      <button type="button" className={s.banner} onClick={onOpen}>
        <span className={s.icon} aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M12 2.5 4.5 5.4v5.9c0 4.6 3.1 8.6 7.5 10.2 4.4-1.6 7.5-5.6 7.5-10.2V5.4Z" />
          </svg>
        </span>
        <span className={s.text}>
          <span className={s.head}>
            <span className={s.app}>Flood Watch</span>
            <span className={s.when}>now</span>
          </span>
          <span className={s.body}>{body}</span>
        </span>
      </button>
    </div>
  )
}
