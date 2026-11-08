import { Play } from 'lucide-react'
import { useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { Case } from '../data/types'
import { displayName } from '../data/personas'
import { useTown } from '../hooks/useTown'
import { formatRelative } from '../lib/format'
import { useNow } from '../lib/useNow'
import { caseSeverity, stepLabel } from '../state/cases'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { TONE_ICON } from '../ui/status'
import { casePlace } from './caseInfo'
import s from './Queue.module.css'

const isOpen = (c: Case) => c.state !== 'resolved'
const SEV_LABEL = { critical: 'Critical', caution: 'Caution', safe: 'Resolved' } as const

type Tab = 'open' | 'resolved'

/**
 * Case list: one row per case, open cases first. Selecting a row opens the detail panel.
 * `tabs` (Driver cases page) splits open and resolved; `filter` narrows by name or place.
 */
export function Queue({ tabs = false, filter = '' }: { tabs?: boolean; filter?: string }) {
  const [tab, setTab] = useState<Tab>('open')
  const store = useStore()
  const cases = useApp((a) => a.cases)
  const outreach = useApp((a) => a.outreach)
  const newest = useApp((a) => a.newestCaseId)
  const selected = useUi((u) => u.selectedCaseId)
  const { state: town } = useTown()
  const now = useNow(15_000)
  const listRef = useRef<HTMLUListElement>(null)

  const openCount = useMemo(() => cases.filter(isOpen).length, [cases])
  const townData = town.status === 'ready' ? town.town : null
  const places = useMemo(
    () => Object.fromEntries(cases.map((c) => [c.id, casePlace(c, outreach, townData)])),
    [cases, outreach, townData],
  )
  const sorted = useMemo(() => {
    const q = filter.trim().toLowerCase()
    const match = (c: Case) => !q || displayName(c.driver_id, c.driver_name).toLowerCase().includes(q) || (places[c.id] ?? '').toLowerCase().includes(q)
    const ordered = [...cases.filter(isOpen), ...cases.filter((c) => !isOpen(c))].filter(match)
    return tabs ? ordered.filter((c) => (tab === 'open') === isOpen(c)) : ordered
  }, [cases, filter, places, tabs, tab])
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
      {tabs ? (
        <>
        <h2 id="cases-h" className={s.srOnly}>Driver cases</h2>
        <div className={s.tabs} role="group" aria-label="Case status">
          {(['open', 'resolved'] as const).map((t) => (
            <button key={t} type="button" aria-pressed={tab === t} className={s.tab} onClick={() => setTab(t)}>
              {t === 'open' ? 'Open' : 'Resolved'}
              <span className={`${s.tabCount} num`}>{t === 'open' ? openCount : cases.length - openCount}</span>
            </button>
          ))}
        </div>
        </>
      ) : (
        <h2 id="cases-h" className={s.heading}>
          Cases <span className={`${s.count} num`}>{openCount} open</span>
        </h2>
      )}
      <p className={s.srOnly} aria-live="polite">{newestCase ? `New case: car stopped in water near ${places[newestCase.id] ?? 'a flooded road'}` : ''}</p>

      <div className={s.scroll}>
        {sorted.length === 0 ? (
          <div className={s.empty}>
            <p>{filter ? 'No cases match.' : tabs && tab === 'resolved' ? 'No resolved cases yet.' : 'No open cases. A case opens when a car stops on a flooded road.'}</p>
            {!filter && cases.length === 0 && <RunScenario />}
          </div>
        ) : (
          <ul className={s.list} ref={listRef} onKeyDown={onKey}>
            {sorted.map((c, i) => {
              const sev = caseSeverity(c)
              const SevIcon = TONE_ICON[sev]
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
                    <SevIcon size={16} className={`${s.sev} ${s[sev]}`} aria-hidden="true" />
                    <span className={s.name}>{displayName(c.driver_id, c.driver_name)}</span>
                    <span className={`${s.age} num`}>{formatRelative(c.opened_at, now)}</span>
                    <span className={s.sub}><span className={`${s.sevText} ${s[sev]}`}>{SEV_LABEL[sev]}</span> · {places[c.id] ?? 'Locating road'} · {stepLabel(c.state)}</span>
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

/** Starts the synthetic driver scenario (offline replay or the backend demo) from the console. */
function RunScenario() {
  const store = useStore()
  const [state, setState] = useState<'idle' | 'starting' | 'error'>('idle')
  const start = () => {
    setState('starting')
    store.provider.startDemo().then(() => setState('idle'), () => setState('error'))
  }
  return (
    <>
      <button type="button" className={s.run} onClick={start} disabled={state === 'starting'}>
        <Play size={14} aria-hidden="true" />
        {state === 'starting' ? 'Starting…' : 'Run test scenario'}
      </button>
      {state === 'error' && <p className={s.runError} role="alert">Could not start the scenario. Is the backend running?</p>}
    </>
  )
}
