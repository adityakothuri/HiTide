import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Activity, AlertTriangle, Car, Check, ClipboardCheck, Database, ExternalLink, FlaskConical, Layers, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import type { EvidenceState } from './types'
import { activeWarning, fullTime, mappedRoads, type QueueTab, secondsAgo, summary, tasksFor } from './ops/derive'
import { EvidenceMap } from './ops/EvidenceMap'
import { Queue } from './ops/Queue'
import { RoadDetail } from './ops/RoadDetail'
import { SourceHealth } from './ops/SourceHealth'
import s from './ops/ops.module.css'
import { LogoMark } from '../ui/LogoMark'

const POLL_MS = 5_000
const TICK_MS = 5_000
const MAX_RESULTS = 6

async function request(path: string, signal: AbortSignal, body?: unknown) {
  const response = await fetch(`/api/evidence${path}`, {
    method: body === undefined ? 'GET' : 'POST', signal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const error = await response.json() as { detail?: unknown }
      if (typeof error.detail === 'string') message = error.detail
      else if (Array.isArray(error.detail)) message = error.detail.map((entry: { msg?: string }) => entry.msg ?? 'Invalid input').join('; ')
    } catch { /* An unavailable service may return a non-JSON error. */ }
    throw new Error(message)
  }
  return response.json()
}

function Sidebar() {
  return (
    <aside className={s.sidebar} aria-label="Workspace">
      <a href="/console" className={s.brand}><LogoMark size={34} /><span>HiTide</span></a>
      <div className={s.workspace}><span>Workspace</span><strong>Kerr County</strong></div>
      <nav aria-label="Main" className={s.nav}>
        <a href="/texas"><Activity size={20} aria-hidden />Flood monitor</a>
        <a href="/console" aria-current="page"><ClipboardCheck size={20} aria-hidden />Inspections</a>
        <a href="/present"><Car size={20} aria-hidden />Driver cases</a>
        <a href="#source-health"><Layers size={20} aria-hidden />Sources</a>
      </nav>
    </aside>
  )
}

interface SearchProps { state: EvidenceState | null; onPick: (roadId: string) => void }

function RoadSearch({ state, onPick }: SearchProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const q = query.trim().toLowerCase()
  const results = useMemo(() => {
    if (!state || !q) return []
    const communities = state.communities.filter((c) => c.name.toLowerCase().includes(q)).flatMap((c) => {
      const task = state.tasks.find((t) => t.affected_communities.includes(c.id))
      return task ? [{ key: `c-${c.id}`, label: c.name, hint: `Community · ${task.road_name}`, roadId: task.road_id }] : []
    })
    const roads = state.roads.filter((r) => `${r.name} ${r.id}`.toLowerCase().includes(q))
      .map((r) => ({ key: `r-${r.id}`, label: r.name || r.id, hint: `Road · ${r.access}`, roadId: r.id }))
    return [...communities, ...roads].slice(0, MAX_RESULTS)
  }, [state, q])
  const pick = (roadId: string) => { onPick(roadId); setQuery(''); setOpen(false) }
  return (
    <div className={s.search}>
      <Search size={18} aria-hidden />
      <input type="search" placeholder="Search roads or communities" aria-label="Search roads or communities" value={query}
        role="combobox" aria-expanded={open && results.length > 0} aria-controls="search-results" aria-autocomplete="list"
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => { if (e.key === 'Enter' && results[0]) pick(results[0].roadId); if (e.key === 'Escape') setOpen(false) }} />
      {open && q && (
        <ul id="search-results" role="listbox" className={s.results}>
          {results.length ? results.map((r) => (
            <li key={r.key} role="option" aria-selected={false}>
              <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r.roadId)}><strong>{r.label}</strong><small>{r.hint}</small></button>
            </li>
          )) : <li className={s.noResults}>No matching roads or communities</li>}
        </ul>
      )}
    </div>
  )
}

export function Operations() {
  const [state, setState] = useState<EvidenceState | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [selectedId, setSelectedId] = useState('')
  const [tab, setTab] = useState<QueueTab>('review')
  const [now, setNow] = useState(() => Date.now())
  const lifecycle = useRef<AbortController | null>(null)
  const generation = useRef(0)
  const mutation = useRef(false)

  const refresh = useCallback(async (signal: AbortSignal) => {
    const version = ++generation.current
    const next = await request('/state', signal) as EvidenceState
    if (!signal.aborted && version === generation.current) { setState(next); setError('') }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    lifecycle.current = controller
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try { if (!mutation.current) await refresh(controller.signal) }
      catch (err) { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Unable to reach the evidence service.') }
      finally { if (!controller.signal.aborted) timer = setTimeout(() => void poll(), POLL_MS) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [refresh])

  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), TICK_MS)
    return () => window.clearInterval(t)
  }, [])

  const action = useCallback(async (path: string, body: unknown, success: string) => {
    const controller = lifecycle.current
    if (!controller || controller.signal.aborted || mutation.current) return
    mutation.current = true
    ++generation.current
    setBusy(true); setMessage(''); setError('')
    try {
      await request(path, controller.signal, body)
      await refresh(controller.signal)
      if (!controller.signal.aborted) setMessage(success)
    } catch (err) {
      if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'The update could not be saved.')
    } finally { mutation.current = false; if (!controller.signal.aborted) setBusy(false) }
  }, [refresh])

  const roads = useMemo(() => (state ? mappedRoads(state) : []), [state])
  const defaultTask = state ? (tasksFor(state, 'review')[0] ?? tasksFor(state, 'assigned')[0]) : undefined
  const selectedRoad = state?.roads.find((r) => r.id === selectedId) ?? state?.roads.find((r) => r.id === defaultTask?.road_id) ?? roads[0]
  const selectedTask = state?.tasks.find((t) => t.road_id === selectedRoad?.id && t.status !== 'completed') ?? state?.tasks.find((t) => t.road_id === selectedRoad?.id)
  const mapRoads = useMemo(() => (selectedRoad && !roads.includes(selectedRoad) ? [...roads, selectedRoad] : roads), [roads, selectedRoad])
  const counts = state ? summary(state) : null
  const warning = state ? activeWarning(state) : null
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

  const loadDemo = () => void action('/demo', {}, 'Synthetic two-exit exercise loaded. Real observations are preserved.')
  const returnToTown = () => void action('/town', {}, 'Kerrville road network restored. Observation history preserved.')

  return (
    <div className={s.app}>
      <a className={s.skip} href="#ops-main">Skip to inspections</a>
      <Sidebar />
      <div className={s.shell}>
        <header className={s.topbar}>
          <nav aria-label="Breadcrumb" className={s.crumbs}><span>Operations</span><span aria-hidden>/</span><strong aria-current="page">Inspections</strong></nav>
          <RoadSearch state={state} onPick={setSelectedId} />
          <span className={s.avatar} title="Operator">OP</span>
        </header>

        <main id="ops-main" className={s.main}>
          <div className={s.heading}>
            <div>
              <h1>Road verification</h1>
              <p className={s.subtitle}>Prioritize the crossings that matter most.</p>
            </div>
            <div className={s.headActions}>
              <span className={s.stamp}>{fullTime(new Date(now).toISOString())}</span>
              {!state?.dataset.simulated && (
                <button type="button" className={s.secondary} disabled={busy} onClick={loadDemo}><FlaskConical size={16} aria-hidden />Load exercise</button>
              )}
              <button type="button" className={s.iconButton} disabled={busy} aria-label="Refresh sources"
                onClick={() => void action('/ingest', {}, 'Sources refreshed. Observation times are unchanged by the fetch.')}>
                <RefreshCw size={18} className={busy ? s.spin : ''} />
              </button>
            </div>
          </div>

          {error && (
            <div role="alert" className={s.error}>
              <ShieldAlert size={18} aria-hidden />
              <div><strong>Evidence service needs attention</strong><p>{error}. {state ? 'Showing the last successful snapshot; conditions may have changed.' : 'Start the backend to load observations. No demonstration data has been substituted.'}</p></div>
            </div>
          )}
          <div role="status" aria-live="polite" className={message ? s.notice : s.srOnly}>{message && <><Check size={16} aria-hidden />{message}</>}</div>

          {!state || !counts ? (
            <section className={s.loading} aria-label="Loading evidence">
              <Database size={30} aria-hidden />
              <h2>{error ? 'Waiting for the evidence service' : 'Loading road evidence'}</h2>
              <p>Inspection priorities, road evidence, and source health will appear here.</p>
            </section>
          ) : (
            <>
              <section className={s.stats} aria-label="Summary">
                <div><strong>{counts.awaiting}</strong> Awaiting inspection</div>
                <div><strong>{counts.conflicting}</strong> {counts.conflicting === 1 ? 'Conflicting report' : 'Conflicting reports'}</div>
                <div><strong>{counts.communitiesAffected}</strong> {counts.communitiesAffected === 1 ? 'Community affected' : 'Communities affected'}</div>
                <div className={s.updated}>Updated {secondsAgo(state.generated_at, now)}</div>
              </section>

              {warning && (
                <div className={s.warning} role="note">
                  <AlertTriangle size={22} aria-hidden />
                  <p><strong>{warning.title}</strong> · {warning.source}<span className={s.warningNote}>Hazard context, not a road closure</span></p>
                  {warning.link && <a href={warning.link} target="_blank" rel="noreferrer">View bulletin<ExternalLink size={16} aria-hidden /></a>}
                </div>
              )}

              <div className={s.grid}>
                <Queue state={state} tab={tab} onTab={setTab} selectedId={selectedRoad?.id ?? ''} onSelect={setSelectedId} now={now} onLoadDemo={loadDemo} busy={busy} />
                <EvidenceMap roads={mapRoads} selectedId={selectedRoad?.id ?? ''} onSelect={setSelectedId} />
                {selectedRoad ? (
                  <RoadDetail key={selectedRoad.id} state={state} road={selectedRoad} task={selectedTask} now={now} busy={busy} onAction={action} />
                ) : (
                  <section className={`${s.panel} ${s.detail}`} aria-labelledby="detail-heading">
                    <h2 id="detail-heading" className={s.detailTitle}>No crossings flagged</h2>
                    <p className={s.guidance}>{plural(state.roads.length, 'road', 'roads')} loaded with no direct road evidence yet. Unknown access is not treated as open.</p>
                    {state.limitations?.length ? (
                      <><h3 className={s.subhead}>Before ranking inspections</h3><ul className={s.reasons}>{state.limitations.map((l) => <li key={l}>{l}</li>)}</ul></>
                    ) : null}
                    <div className={s.detailActions}><button type="button" className={s.secondary} onClick={loadDemo} disabled={busy}><FlaskConical size={16} aria-hidden />Load two-exit exercise</button></div>
                  </section>
                )}
              </div>

              <SourceHealth state={state} now={now} onReturnToTown={returnToTown} busy={busy} />
            </>
          )}
        </main>
      </div>
    </div>
  )
}
