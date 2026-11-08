import * as Tabs from '@radix-ui/react-tabs'
import type { ReactNode } from 'react'
import s from './FilterTabs.module.css'

export interface FilterOption<T extends string> {
  value: T
  label: string
  count?: number
}

/** Radix tabs styled as filters. Selected uses the brand-red indicator (a selected state, not danger). */
export function FilterTabs<T extends string>({ value, onChange, options, label, children }: {
  value: T
  onChange: (v: T) => void
  options: FilterOption<T>[]
  label: string
  children?: ReactNode
}) {
  return (
    <Tabs.Root value={value} onValueChange={(v) => onChange(v as T)} className={s.root}>
      <Tabs.List aria-label={label} className={s.list}>
        {options.map((o) => (
          <Tabs.Trigger key={o.value} value={o.value} className={s.trigger}>
            {o.label}
            {o.count !== undefined && (
              <span className={`${s.count} num`}>
                {o.count}
                <span className="visually-hidden"> cases</span>
              </span>
            )}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {children}
    </Tabs.Root>
  )
}

export const FilterPanel = Tabs.Content
