// Small iOS-style building blocks for the driver app: inset grouped sections, rows, glyph tiles
// and buttons. Local to the phone so the console's primitives stay independent.
import { ChevronRight, type LucideIcon } from 'lucide-react'
import type { ButtonHTMLAttributes, ReactNode, Ref } from 'react'
import s from './ios.module.css'

export type Tone = 'red' | 'blue' | 'green' | 'gray' | 'water' | 'critical' | 'caution' | 'ink'

export function Glyph({ icon: Icon, tone = 'gray' }: { icon: LucideIcon; tone?: Tone }) {
  return (
    <span className={`${s.glyph} ${s[`g_${tone}`]}`} aria-hidden="true">
      <Icon strokeWidth={2.2} />
    </span>
  )
}

export function Section({ header, footer, children, id, flush = false }: { header?: ReactNode; footer?: ReactNode; children: ReactNode; id?: string; flush?: boolean }) {
  return (
    <section className={s.section} aria-labelledby={header && id ? id : undefined}>
      {header && <h3 id={id} className={s.header}>{header}</h3>}
      <div className={`${s.group} ${flush ? s.flush : ''}`}>{children}</div>
      {footer && <p className={s.footer}>{footer}</p>}
    </section>
  )
}

interface RowProps {
  icon?: LucideIcon
  tone?: Tone
  title: ReactNode
  subtitle?: ReactNode
  trailing?: ReactNode
  onClick?: () => void
  chevron?: boolean
  label?: string
}

export function Row({ icon, tone = 'gray', title, subtitle, trailing, onClick, chevron = false, label }: RowProps) {
  const body = (
    <>
      {icon && <Glyph icon={icon} tone={tone} />}
      <span className={s.rowText}>
        <span className={s.rowTitle}>{title}</span>
        {subtitle && <span className={s.rowSub}>{subtitle}</span>}
      </span>
      {trailing && <span className={s.trailing}>{trailing}</span>}
      {chevron && <ChevronRight className={s.chevron} aria-hidden="true" />}
    </>
  )
  const cls = `${s.row} ${icon ? s.withIcon : ''}`
  if (onClick) {
    return (
      <button type="button" className={`${cls} ${s.tappable}`} onClick={onClick} aria-label={label}>
        {body}
      </button>
    )
  }
  return <div className={cls}>{body}</div>
}

type BtnVariant = 'filled' | 'tinted' | 'gray' | 'plain' | 'dark' | 'done'

interface BtnProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: BtnVariant
  icon?: LucideIcon
  ref?: Ref<HTMLButtonElement>
  children: ReactNode
}

export function Btn({ variant = 'filled', icon: Icon, className, children, ref, type = 'button', ...rest }: BtnProps) {
  return (
    <button ref={ref} type={type} className={`${s.btn} ${s[variant]} ${className ?? ''}`} {...rest}>
      {Icon && <Icon aria-hidden="true" strokeWidth={2.2} />}
      <span>{children}</span>
    </button>
  )
}

/** Large title, iOS style. Focusable so screen changes can move focus here. */
export function LargeTitle({ children, sub, size = 'large' }: { children: ReactNode; sub?: ReactNode; size?: 'large' | 'title' }) {
  return (
    <div className={s.titleBlock}>
      <h2 className={size === 'large' ? s.largeTitle : s.title1} tabIndex={-1}>{children}</h2>
      {sub && <p className={s.titleSub}>{sub}</p>}
    </div>
  )
}
