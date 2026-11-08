import s from './Footer.module.css'

export const DISCLAIMER = 'Concept prototype. Demo data where marked.'

export function Disclaimer({ className }: { className?: string }) {
  return <p className={`${s.disclaimer} ${className ?? ''}`}>{DISCLAIMER}</p>
}
