import type { HTMLAttributes, ReactNode } from 'react'
import s from './Card.module.css'

/** Driver-app card: white, bordered, medium radius. No shadow. */
export function Card({ children, className, flush = false, ...rest }: HTMLAttributes<HTMLDivElement> & { children: ReactNode; flush?: boolean }) {
  return (
    <div className={`${s.card} ${flush ? s.flush : ''} ${className ?? ''}`} {...rest}>
      {children}
    </div>
  )
}

/** Console section: divided by a rule, not boxed. */
export function Section({ title, aside, children, className }: { title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`${s.section} ${className ?? ''}`}>
      {(title || aside) && (
        <header className={s.sectionHead}>
          {title && <h3>{title}</h3>}
          {aside}
        </header>
      )}
      {children}
    </section>
  )
}
