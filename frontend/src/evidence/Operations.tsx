import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, Check, CircleHelp, Database, Droplets, Layers, MapPin, Radio, RefreshCw, Send, ShieldAlert } from 'lucide-react'
import type { Access, EvidenceState, Observation, Road, Task } from './types'
import s from './Operations.module.css'

function time(iso?: string | null) {
  if (!iso) return 'Not supplied'
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? 'Invalid timestamp' : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', timeZoneName: 'short' })
}

function localTime() {
  const date = new Date()
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

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

function RoadMap({ roads, selected, onSelect }: { roads: Road[]; selected: string; onSelect: (id: string) => void }) {
  const projection = useMemo(() => {
    const points = roads.flatMap((road) => road.geometry?.coordinates ?? [])
    if (!points.length) return { paths: [], grid: [] }
    const xs = points.map((p) => p[0] * Math.cos((p[1] * Math.PI) / 180))
    const ys = points.map((p) => p[1])
    const xmin = xs.reduce((a, b) => Math.min(a, b), Infinity), xmax = xs.reduce((a, b) => Math.max(a, b), -Infinity)
    const ymin = ys.reduce((a, b) => Math.min(a, b), Infinity), ymax = ys.reduce((a, b) => Math.max(a, b), -Infinity)
    const scale = Math.min(880 / Math.max(xmax - xmin, 0.0001), 450 / Math.max(ymax - ymin, 0.0001))
    const cx = (xmin + xmax) / 2, cy = (ymin + ymax) / 2
    return {
      paths: roads.map((road) => ({ road, points: road.geometry?.coordinates.map(([lon, lat]) => `${500 + (lon * Math.cos((lat * Math.PI) / 180) - cx) * scale},${285 - (lat - cy) * scale}`).join(' ') ?? '' })),
      grid: Array.from({ length: 12 }, (_, i) => i * 100),
    }
  }, [roads])
  return (
    <div className={s.map}>
      <svg viewBox="0 0 1000 570" className={s.mapSvg} role="group" aria-label="Road evidence map. Use the road selector below for a full accessible list.">
        <defs><pattern id="map-grid" width="55" height="55" patternUnits="userSpaceOnUse"><path d="M55 0H0V55" fill="none" stroke="currentColor" strokeWidth="0.6" /></pattern></defs>
        <rect width="1000" height="570" fill="url(#map-grid)" className={s.grid} />
        {projection.paths.map(({ road, points }, index) => (
          <g key={road.id} role="button" tabIndex={road.id === selected || (!selected && index === 0) ? 0 : -1}
            aria-label={`${road.name} — ${road.access}`} aria-pressed={road.id === selected}
            onClick={() => onSelect(road.id)} onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(road.id) }
            }} className={`${s.mapRoad} ${s[road.access]} ${road.id === selected ? s.selectedRoad : ''}`}>
            <title>{road.name}: {road.access}, evidence {road.freshness}</title>
            <polyline points={points} fill="none" strokeWidth="22" className={s.hitArea} />
            {road.id === selected && <polyline points={points} fill="none" strokeWidth="13" className={s.selectionHalo} />}
            <polyline points={points} fill="none" strokeWidth={roads.length > 100 ? 2.4 : 7} strokeLinecap="round" className={s.roadLine} />
          </g>
        ))}
        {!roads.length && <text x="500" y="285" textAnchor="middle" fill="currentColor">Waiting for road evidence</text>}
      </svg>
      <div className={s.mapNote}><MapPin size={14} /> Kerrville, Texas <span>Road geometry · no external map tiles</span></div>
      <div className={s.north} aria-hidden="true">N ↑</div>
    </div>
  )
}

function ObservationCard({ observation }: { observation: Observation }) {
  const description = observation.raw.description
  const cached = observation.source_mode === 'cached' || observation.raw.source === 'cached' || observation.raw.feed_source === 'cached'
  return (
    <article className={s.observation}>
      <div className={s.row}><strong>{observation.source_id.replaceAll('_', ' ')}</strong><span className={s.tag}>{observation.kind}</span></div>
      <div className={s.badges}><span className={s.tag}>{observation.quality}</span>{observation.simulated && <span className={s.demoTag}>Simulated</span>}{cached && <span className={s.tag}>Cached</span>}</div>
      {typeof description === 'string' && <p>{description}</p>}
      <dl className={s.timestamps}><div><dt>Observed</dt><dd>{time(observation.observed_at)}</dd></div><div><dt>Received</dt><dd>{time(observation.ingested_at)}</dd></div></dl>
      <p className={s.small}>Reported access: <strong>{observation.access}</strong>{observation.value != null && <> · {observation.value} {observation.unit}</>}</p>
    </article>
  )
}

function InspectionCard({ task, simulated, busy, onAction, onSelect }: { task: Task; simulated: boolean; busy: boolean; onAction: (path: string, body: unknown, success: string) => Promise<void>; onSelect: (id: string) => void }) {
  const [outcome, setOutcome] = useState('closed')
  const [observedAt, setObservedAt] = useState(localTime)
  const [image, setImage] = useState('')
  const active = task.status === 'queued' || task.status === 'assigned' || task.status === 'inconclusive'
  return (
    <article className={`${s.task} ${active ? '' : s.finished}`}>
      <div className={s.row}><span className={s.taskState}>{task.status}</span><span className={s.priority}>Priority {task.priority.toFixed(0)}</span></div>
      <button className={s.taskTitle} onClick={() => onSelect(task.road_id)}>{task.road_name}<ArrowRight size={16} /></button>
      <ul className={s.reasons}>{task.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      {task.affected_communities.length > 0 && <p className={s.small}>Affects {task.affected_communities.join(', ')}</p>}
      {(task.status === 'queued' || task.status === 'inconclusive') && <button className={s.assign} disabled={busy} onClick={() => void onAction(`/tasks/${encodeURIComponent(task.id)}/assign`, {}, 'Inspection assigned. Awaiting fresh evidence.')}><Send size={15} />Assign inspection</button>}
      {task.status === 'assigned' && <form className={s.inspectionForm} onSubmit={(event) => {
        event.preventDefault()
        void onAction(`/tasks/${encodeURIComponent(task.id)}/complete`, { outcome, observed_at: new Date(observedAt).toISOString(), ...(image ? { image_url: image } : {}) }, 'Inspection recorded. Road evidence and priorities recomputed.')
      }}>
        <label>Inspection finding<select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option value="closed">Closed / flooding observed</option><option value="open">Open / no obstruction observed</option><option value="inconclusive">Inconclusive / unable to verify</option></select></label>
        <label>Captured at (your local time)<input type="datetime-local" required value={observedAt} onChange={(event) => setObservedAt(event.target.value)} /></label>
        {!simulated && <label>Image path (optional)<input value={image} onChange={(event) => setImage(event.target.value)} placeholder="/static/drone/inspection.jpg" /></label>}
        <button className={s.assign} disabled={busy} type="submit"><Check size={15} />{simulated ? 'Record simulated inspection' : 'Record inspection evidence'}</button>
      </form>}
    </article>
  )
}

export function Operations() {
  const [state, setState] = useState<EvidenceState | null>(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [selectedId, setSelectedId] = useState('')
  const [reportAccess, setReportAccess] = useState<Access>('unknown')
  const [reportText, setReportText] = useState('')
  const [reportTime, setReportTime] = useState(localTime)
  const [filter, setFilter] = useState('')
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
      finally { if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 5_000) }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [refresh])

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

  const selectedRoad = state?.roads.find((road) => road.id === selectedId) ?? state?.roads.find((road) => road.id === state.tasks.find((task) => task.status === 'queued')?.road_id) ?? state?.roads[0]
  const selectedEvidence = useMemo(() => {
    if (!selectedRoad || !state) return []
    return state.observations.filter((observation) => selectedRoad.evidence_ids.includes(observation.id) || observation.road_id === selectedRoad.id)
      .sort((a, b) => (b.observed_at ?? '').localeCompare(a.observed_at ?? ''))
  }, [selectedRoad, state])
  const activeTasks = state?.tasks.filter((task) => task.status !== 'completed') ?? []
  const historyTasks = state?.tasks.filter((task) => task.status === 'completed') ?? []
  const filteredRoads = state?.roads.filter((road) => `${road.name} ${road.id}`.toLowerCase().includes(filter.toLowerCase())) ?? []

  function submitReport(event: FormEvent) {
    event.preventDefault()
    if (!selectedRoad) return
    void action('/reports', {
      source_id: 'local_reports', kind: 'report', road_id: selectedRoad.id, access: reportAccess,
      observed_at: new Date(reportTime).toISOString(), quality: 'unverified', simulated: state?.dataset.simulated ?? false,
      raw: { description: reportText },
    }, 'Local report stored with its source and observation time.')
  }

  return (
    <div className={s.app}>
      <a className={s.skip} href="#evidence-main">Skip to operations</a>
      <header className={s.header}><a href="/console" className={s.brand}><span className={s.brandMark}><Droplets size={23} /></span><span>Flood Watch<span className={s.brandSub}>STATE FARM HACKATHON</span></span></a><nav aria-label="Main"><a href="/console" aria-current="page">Operations</a><a href="/gallery">Components</a></nav><span className={s.connection}><span className={error ? s.offlineDot : s.liveDot} />{error ? 'Connection needs attention' : state ? 'Evidence service connected' : 'Connecting'}</span></header>
      <main id="evidence-main" className={s.main}>
        <div className={s.pageHeading}><div><p className={s.eyebrow}>KERRVILLE / GUADALUPE RIVER</p><h1>Flood intelligence</h1><p className={s.subtitle}>Find the information gaps that could change how people get out.</p></div><div className={s.actions}><button disabled={busy} className={s.secondary} onClick={() => void action('/ingest', {}, 'Source fetch finished. Review source health and observation times below.')}><RefreshCw size={16} />Refresh sources</button><button disabled={busy} className={s.primary} onClick={() => void action('/demo', {}, 'Synthetic two-exit scenario loaded. Real observations are preserved.')}><Layers size={16} />Load two-exit demo</button></div></div>
        {error && <div role="alert" className={s.error}><ShieldAlert size={18} /><div><strong>Evidence service needs attention</strong><p>{error}. {state ? 'Showing the last successful snapshot; conditions may have changed.' : 'Start the backend to load observations. No demonstration data has been substituted.'}</p></div></div>}
        <div role="status" aria-live="polite" className={message ? s.notice : s.emptyNotice}>{message && <><Check size={16} />{message}</>}</div>
        {state?.dataset.simulated && <div className={s.demoBanner}><span className={s.demoTag}>SIMULATED SCENARIO</span><p>{state.dataset.name}. Inspections and neighborhood connectivity are demonstration data.</p><button className={s.secondary} disabled={busy} onClick={() => void action('/town', {}, 'Actual Kerrville road network restored. Observation history preserved.')}>Return to Kerrville roads</button></div>}
        {!state ? <section className={s.loading} aria-label="Loading evidence"><Database size={32} /><h2>{error ? 'Waiting for the evidence service' : 'Loading the shared picture'}</h2><p>Road observations, source provenance, and inspection priorities will appear here.</p></section> : <>
          <section className={s.metrics} aria-label="Operations overview"><div><span>Observations stored</span><strong>{state.observations.length}</strong><small>Source and timestamp preserved</small></div><div><span>Roads needing fresh evidence</span><strong>{state.roads.filter((road) => road.freshness !== 'current' || road.agreement === 'conflicting').length}</strong><small>Missing, stale, or conflicting</small></div><div><span>Active inspection targets</span><strong>{activeTasks.length}</strong><small>Ranked by modeled access impact</small></div><div><span>Communities with uncertain access</span><strong>{state.communities.filter((community) => !community.conservative_access).length}</strong><small>Includes no modeled exit</small></div></section>
          <div className={s.workspace}>
            <section className={s.mapPanel} aria-labelledby="map-heading"><div className={s.panelHeading}><div><p className={s.eyebrow}>SHARED OPERATING PICTURE</p><h2 id="map-heading">Road evidence</h2></div><span className={s.tag}>Updated {time(state.generated_at)}</span></div><RoadMap roads={state.roads} selected={selectedRoad?.id ?? ''} onSelect={setSelectedId} /><div className={s.legend}>{(['open', 'closed', 'restricted', 'unknown'] as const).map((status) => <span key={status}><i className={`${s.legendLine} ${s[status]}`} />{status === 'open' ? 'Reported open' : status}</span>)}</div><div className={s.roadSelector}><label>Find a road<input placeholder="Search road name or ID" value={filter} onChange={(event) => setFilter(event.target.value)} /></label><label>Select road<select value={filteredRoads.some((road) => road.id === selectedRoad?.id) ? selectedRoad?.id : ''} onChange={(event) => setSelectedId(event.target.value)}><option value="" disabled>{filteredRoads.length ? 'Choose a road' : 'No matching roads'}</option>{filteredRoads.map((road) => <option key={road.id} value={road.id}>{road.name || road.id}</option>)}</select></label></div><p className={s.mapDisclaimer}><CircleHelp size={15} />Evidence describes reported conditions. This map does not certify a safe evacuation route.</p></section>
            <aside className={s.queue} aria-labelledby="queue-heading"><div className={s.panelHeading}><div><p className={s.eyebrow}>WHERE TO LOOK NEXT</p><h2 id="queue-heading">Inspection priorities</h2></div><span className={s.count}>{activeTasks.length}</span></div><div className={s.queueBody}>{activeTasks.length ? activeTasks.map((task) => <InspectionCard key={task.id} task={task} simulated={state.dataset.simulated} busy={busy} onAction={action} onSelect={setSelectedId} />) : <div className={s.empty}><Check size={24} /><h3>No active inspection targets</h3><p>{state.communities.length ? 'No actionable information gaps are queued.' : 'Add community origins and evacuation destinations to rank access impact, or load the labeled demo.'}</p></div>}{historyTasks.length > 0 && <details className={s.history}><summary>Completed inspections ({historyTasks.length})</summary>{historyTasks.map((task) => <InspectionCard key={task.id} task={task} simulated={state.dataset.simulated} busy={busy} onAction={action} onSelect={setSelectedId} />)}</details>}</div></aside>
          </div>
          <div className={s.lowerGrid}>
            <section className={s.panel} aria-labelledby="evidence-heading"><div className={s.panelHeading}><div><p className={s.eyebrow}>WHY THE MAP SAYS THIS</p><h2 id="evidence-heading">{selectedRoad?.name ?? 'Select a road'}</h2></div>{selectedRoad && <span className={`${s.accessTag} ${s[selectedRoad.access]}`}>{selectedRoad.access}</span>}</div>{selectedRoad && <div className={s.evidenceBody}><div className={s.badges}><span className={s.tag}>Evidence {selectedRoad.freshness}</span><span className={selectedRoad.agreement === 'conflicting' ? s.warningTag : s.tag}>{selectedRoad.agreement}</span></div>{selectedRoad.reasons?.map((reason) => <p key={reason} className={s.small}>{reason}</p>)}{selectedEvidence.length ? selectedEvidence.map((observation) => <ObservationCard key={observation.id} observation={observation} />) : <p className={s.empty}>No direct observations. Missing information is treated as unknown.</p>}<details className={s.report}><summary>Add a local report</summary><form onSubmit={submitReport}><p className={s.small}>Report what was observed at this road. Reports are stored as unverified evidence.{state.dataset.simulated && ' This report will be labeled simulated.'}</p><label>Observed access<select value={reportAccess} onChange={(event) => setReportAccess(event.target.value as Access)}><option value="unknown">Unknown / unable to verify</option><option value="closed">Closed / blocked</option><option value="restricted">Restricted</option><option value="open">Reported open</option></select></label><label>Observed at (your local time)<input type="datetime-local" required value={reportTime} onChange={(event) => setReportTime(event.target.value)} /></label><label>What did you observe?<textarea required maxLength={2000} value={reportText} onChange={(event) => setReportText(event.target.value)} placeholder="Location details, water coverage, visible obstructions…" /></label><button className={s.secondary} type="submit" disabled={busy || !reportText.trim()}>Save observation</button></form></details></div>}</section>
            <div className={s.sidePanels}><section className={s.panel} aria-labelledby="community-heading"><div className={s.panelHeading}><div><p className={s.eyebrow}>CONSEQUENCE OF THE GAP</p><h2 id="community-heading">Community access</h2></div><MapPin size={20} /></div><div className={s.evidenceBody}>{state.communities.length ? state.communities.map((community) => <article className={s.community} key={community.id}><strong>{community.name}</strong><span className={!community.optimistic_access ? s.warningTag : community.conservative_access ? s.goodTag : s.warningTag}>{!community.optimistic_access ? 'No modeled exit' : community.conservative_access ? 'Modeled connection exists' : 'Access depends on uncertain roads'}</span><p className={s.small}>{community.remaining_exits != null ? `${community.remaining_exits} possible modeled exit${community.remaining_exits === 1 ? '' : 's'}. ` : ''}Optimistic: {community.optimistic_access ? 'connected' : 'disconnected'} · Conservative: {community.conservative_access ? 'connected' : 'disconnected'}</p></article>) : <p className={s.small}>No community origins or destinations configured. Road evidence is available; access analysis needs these inputs.</p>}<p className={s.contextNote}>Optimistic assumes uncertain roads are usable. Conservative excludes them. Neither proves that a route is safe.</p></div></section><section className={s.panel} aria-labelledby="source-heading"><div className={s.panelHeading}><div><p className={s.eyebrow}>PROVENANCE & COVERAGE</p><h2 id="source-heading">Source health</h2></div><Radio size={20} /></div><div className={s.evidenceBody}>{state.sources.length ? state.sources.map((source, index) => <div className={s.source} key={source.id ?? source.source_id ?? index}><strong>{source.name ?? source.id ?? source.source_id}</strong><span className={s.tag}>{source.status ?? source.last_status ?? 'Not fetched'}</span><small>Last success: {time(source.last_successful_fetch_at)}</small>{source.detail && <small>{source.detail}</small>}</div>) : <p className={s.small}>No source runs recorded yet. Refresh sources to fetch available NWS and USGS evidence.</p>}<p className={s.contextNote}>River gauge height is context, not road water depth. Refreshing a feed does not refresh the observation time.</p></div></section></div>
          </div>
        </>}
        <footer className={s.footer}><span>Flood Watch · HackUTD 2026</span><span>Evidence → access impact → verification → updated priorities</span></footer>
      </main>
    </div>
  )
}
