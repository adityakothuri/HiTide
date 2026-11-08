import type { ReactNode } from 'react'
import { TONE_ICON, TONE_LABEL, type Tone } from './status'
import s from './Banner.module.css'

export function Banner({ tone, title, children, role }: { tone: Tone; title: string; children?: ReactNode; role?: 'status' | 'alert' }) {
  const Icon = TONE_ICON[tone]
  return (
    <div className={`${s.banner} ${s[tone]}`} role={role ?? (tone === 'critical' ? 'alert' : 'status')}>
      <Icon className={s.icon} aria-hidden="true" strokeWidth={2.25} />
      <div className={s.body}>
        <p className={s.title}>
          <span className="visually-hidden">{TONE_LABEL[tone]}: </span>
          {title}
        </p>
        {children && <div className={s.detail}>{children}</div>}
      </div>
    </div>
  )
}
