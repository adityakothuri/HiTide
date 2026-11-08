import s from './Counter.module.css'

/** Inline number + plain label. No card, no icon. */
export function Counter({ value, label }: { value: number | string; label: string }) {
  return (
    <span className={s.counter}>
      <span className={`${s.value} num`}>{value}</span>
      <span className={s.label}>{label}</span>
    </span>
  )
}
