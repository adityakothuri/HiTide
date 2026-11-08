import { useMemo, useRef, type KeyboardEvent } from 'react'
import type { Case } from '../data/types'
import { displayName } from '../data/personas'
import { useTown } from '../hooks/useTown'
import { formatRelative } from '../lib/format'
import { useNow } from '../lib/useNow'
import { caseSeverity, stepLabel } from '../state/cases'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { casePlace } from './caseInfo'
import s from './Queue.module.css'

const isOpen = (c: Case) => c.state !== 'resolved'

/** Compact case list: one line per case, open cases first. Selecting a row opens the detail panel. */
export function Queue() {
  const store = useStore()
  const cases = useApp((a) => a.cases)
  const outreach = useApp((a) => a.outreach)
  const newest = useApp((a) => a.newestCaseId)
  const selected = useUi((u) => u.selectedCaseId)
  const { state: town } = useTown()
  const now = useNow(15_000)
  const listRef = useRef<HTMLUListElement>(null)

  const sorted = useMemo(() => [...cases.filter(isOpen), ...cases.filter((c) => !isOpen(c))], [cases])
  const openCount = useMemo(() => cases.filter(isOpen).length, [cases])
  const townData = town.status === 'ready' ? town.town : null
  const places = useMemo(
    () => Object.fromEntries(cases.map((c) => [c.id, casePlace(c, outreach, townData)])),
    [cases, outreach, townData],
  )
  const newestCase = cases.find((c) => c.id === newest)

  const select = (id: string) => store.setUi((u) => ({ ...u, selectedCaseId: id }))

  const onKey = (e: KeyboardEvent<HTMLUListElement>) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const i = sorted.findIndex((c) => c.id === selected)
    const next = sorted[Math.max(0, Math.min(sorted.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]
    if (!next) return
    select(next.id)
    listRef.current?.querySelector<HTMLButtonElement>(`[data-case="${next.id}"]`)?.focus()
  }

  return (
    <section className={s.queue} aria-labelledby="cases-h">
      <h2 id="cases-h" className={s.heading}>
        Cases <span className={`${s.count} num`}>{openCount} open</span>
      </h2>
      <p className={s.srOnly} aria-live="polite">{newestCase ? `New case: car stopped in water near ${places[newestCase.id] ?? 'a flooded road'}` : ''}</p>

      <div className={s.scroll}>
        {sorted.length === 0 ? (
          <p className={s.empty}>No cases. A case opens when a car stops on a flooded road.</p>
        ) : (
          <ul className={s.list} ref={listRef} onKeyDown={onKey}>
            {sorted.map((c, i) => {
              const sev = caseSeverity(c)
              const isSel = c.id === selected
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    data-case={c.id}
                    className={`${s.row} ${isSel ? s.selected : ''} ${isOpen(c) ? '' : s.closedRow}`}
                    aria-current={isSel ? 'true' : undefined}
                    tabIndex={isSel || (i === 0 && !sorted.some((v) => v.id === selected)) ? 0 : -1}
                    onClick={() => select(c.id)}
                  >
                    <span className={`${s.sev} ${s[sev]}`} aria-label={sev === 'critical' ? 'Critical' : sev === 'caution' ? 'Caution' : 'Resolved'} role="img" />
                    <span className={s.name}>{displayName(c.driver_id, c.driver_name)}</span>
                    <span className={`${s.age} num`}>{formatRelative(c.opened_at, now)}</span>
                    <span className={s.sub}>{places[c.id] ?? 'Locating road'} · {stepLabel(c.state)}</span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </section>
  )
}
