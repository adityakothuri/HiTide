import s from './Footer.module.css'

export const DISCLAIMER = 'Concept prototype. Not an official State Farm product.'

export function Disclaimer({ className }: { className?: string }) {
  return <p className={`${s.disclaimer} ${className ?? ''}`}>{DISCLAIMER}</p>
}
