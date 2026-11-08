import { CircleCheck, Circle, CircleDot } from 'lucide-react'
import type { ReactNode } from 'react'
import type { StepStatus } from '../state/driverFlow'
import s from './Timeline.module.css'

export interface TimelineItem {
  id: string
  title: ReactNode
  time?: string
  iso?: string
  detail?: ReactNode
  status?: StepStatus
  tag?: ReactNode
}

const STATUS_ICON = { done: CircleCheck, active: CircleDot, waiting: Circle }
const STATUS_TEXT: Record<StepStatus, string> = { done: 'Done', active: 'In progress', waiting: 'Waiting' }

/** Vertical timeline. With `status`, each step shows its state by icon shape and text. */
export function Timeline({ items, showStatus = false, size = 'md' }: { items: TimelineItem[]; showStatus?: boolean; size?: 'sm' | 'md' }) {
  return (
    <ol className={`${s.list} ${s[size]}`} role="list">
      {items.map((item) => {
        const status = item.status ?? 'done'
        const Icon = STATUS_ICON[status]
        return (
          <li key={item.id} className={`${s.item} ${s[status]}`}>
            <span className={s.rail} aria-hidden="true">
              <Icon className={s.icon} strokeWidth={2.25} />
            </span>
            <div className={s.content}>
              {!showStatus && item.status && <span className="visually-hidden">{STATUS_TEXT[status]}: </span>}
              <div className={s.head}>
                {item.time && <time className={`${s.time} num`} dateTime={item.iso}>{item.time}</time>}
                <span className={s.title}>{item.title}</span>
                {item.tag}
              </div>
              {item.detail && <div className={s.detail}>{item.detail}</div>}
            </div>
            {showStatus && <span className={s.status}>{STATUS_TEXT[status]}</span>}
          </li>
        )
      })}
    </ol>
  )
}
