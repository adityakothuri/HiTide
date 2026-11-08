import { Search } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useTown } from '../hooks/useTown'
import { caseSeverity } from '../state/cases'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { useWx } from '../wx/useWx'
import { Colorbar, MapKey } from './Colorbar'
import { Detail } from './Detail'
import { FeatureDetail } from './FeatureDetail'
import { GaugeTable } from './GaugeTable'
import { FleetPanel } from './FleetPanelGroup'
import { LayerPanel } from './LayerPanel'
import { LayersMenu } from './LayersMenu'
import { MapView, type Feature, type RegionMap } from './MapView'
import { AreasPanel, PeoplePanel } from './PeoplePanel'
import { PersonDetail } from './PersonDetail'
import { PAGE_PATH } from '../shell/AppShell'
import { peopleSummary } from '../region/derive'
import { Queue } from './Queue'
import { TimeSlider } from './TimeSlider'
import { HeaderStatus, TopBar } from './TopBar'
import { useConsoleKeys } from './useConsoleKeys'
import { useRiskGrid } from '../risk/useRiskGrid'
import { useStudyArea } from '../risk/useStudyArea'
import { AppShell } from '../shell/AppShell'
import { useScheme } from '../shell/scheme'
import type { RegionPick } from '../map/regionLayers'
import { useRegion } from '../region/useRegion'
import s from './Console.module.css'

const BASE_TITLE = 'Flood operations | HiTide'
const GAP = 12
const RIGHT_W = 260
/** Risk surface stays underneath the situation markers. */
const SITUATION_OPACITY = 0.5

/** `?autostart=1` starts the offline scenario on load (used for screenshots). */
function useAutostart() {
  const store = useStore()
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('autostart') !== '1') return
    if (store.provider.kind !== 'mock') return
    const t = window.setTimeout(() => void store.provider.startDemo(), 300)
    return () => window.clearTimeout(t)
  }, [store])
}

/** Tab title shows how many critical cases are open, like an inbox count. */
function useDocumentTitle(critical: number) {
  useEffect(() => {
    const prev = document.title
    document.title = critical > 0 ? `(${critical}) ${BASE_TITLE}` : BASE_TITLE
    return () => {
      document.title = prev
    }
  }, [critical])
}

/**
 * Flood monitor: a full-bleed hydromet map (flood risk index, rain or modelled depth as the base field,
 * gauges and road closures on top) with a 280 px left panel, a colorbar for the active field, a time bar,
 * and detail only on click. Inside the operator shell; `compact` is the standalone variant for /present.
 */
export function Console({ compact = false, page = 'monitor' }: { compact?: boolean; page?: 'monitor' | 'cases' }) {
  useAutostart()
  const store = useStore()
  const scheme = useScheme()
  const isCases = page === 'cases' && !compact
  // The monitor shows the region situation; /present (compact) keeps the town demo.
  const isSituation = page === 'monitor' && !compact
  // Driver cases lists the same region people the monitor counts, on the same map.
  const isPeople = isCases
  /** Either page that shows the region situation map (monitor or Driver cases). */
  const regionPage = isSituation || isPeople
  const wx = useWx('risk', regionPage ? { opacity: SITUATION_OPACITY, gauges: false, roads: false } : {})
  const region = useRegion(isSituation || isPeople)
  const [pick, setPick] = useState<RegionPick | null>(null)
  const [query, setQuery] = useState('')
  const riskGrid = useRiskGrid(wx.t, true)
  const area = useStudyArea()
  const { state: townState } = useTown()
  const cases = useApp((a) => a.cases)
  const selected = useUi((u) => u.selectedCaseId)
  const caseCritical = useMemo(() => cases.filter((c) => caseSeverity(c) === 'critical').length, [cases])
  const peopleCritical = useMemo(() => region.people.filter((p) => p.level === 'critical' || p.level === 'danger').length, [region.people])
  const critical = isSituation || isPeople ? peopleCritical : caseCritical
  const [feature, setFeature] = useState<Feature | null>(null)
  useDocumentTitle(critical)

  const hasCase = selected !== null && cases.some((c) => c.id === selected)
  // A selected case takes the detail panel; a gauge or road shows only when no case is selected.
  const activeFeature = hasCase ? null : feature

  const selectFeature = useCallback(
    (f: Feature | null) => {
      setFeature(f)
      if (f) store.setUi((u) => ({ ...u, selectedCaseId: null }))
    },
    [store],
  )
  const closeDetail = useCallback(() => {
    setFeature(null)
    store.setUi((u) => ({ ...u, selectedCaseId: null }))
  }, [store])
  useConsoleKeys(wx, closeDetail, true)

  // One clock: while the backend replay runs, the weather and risk layers follow its time.
  const simT = region.state?.sim_time ? Date.parse(region.state.sim_time) : null
  const running = region.state?.scenario_running === true
  const wxSource = wx.load.status === 'ready' ? wx.load.source : null
  const { setT, setPlaying } = wx
  useEffect(() => {
    // After a run ends the backend keeps its last sim_time; stay there so map and counts agree.
    if (!regionPage || region.state?.mode !== 'replay' || simT == null || !wxSource) return
    const [a, b] = wxSource.range
    const snapped = Math.floor(simT / wxSource.stepMs) * wxSource.stepMs
    setPlaying(false)
    setT(Math.min(b, Math.max(a, snapped)))
  }, [regionPage, running, simT, wxSource, setT, setPlaying, region.state?.mode])

  // The risk surface is the July 4 replay; in live mode it would be stale, so it steps aside.
  const modeNow = region.state?.mode
  const { setLayers } = wx
  useEffect(() => {
    if (!regionPage || !modeNow) return
    setLayers((l) => (modeNow === 'live' ? (l.base === 'risk' ? { ...l, base: 'none' } : l) : l.base === 'none' ? { ...l, base: 'risk' } : l))
  }, [regionPage, modeNow, setLayers])

  const regionMap: RegionMap | undefined = useMemo(() => {
    if (!isSituation && !isPeople) return undefined
    const s = region.state
    const focus: [number, number] | null = (() => {
      if (!pick) return null
      if (pick.kind === 'person') {
        const p = region.people.find((x) => x.user_id === pick.id)
        return p?.location.lon != null && p.location.lat != null ? [p.location.lon, p.location.lat] : null
      }
      if (pick.kind === 'area') {
        const a = s?.nodes.find((x) => x.id === pick.id)
        return a ? [a.lon, a.lat] : null
      }
      const pt = region.points.find((x) => x.id === pick.id) ?? s?.critical_points.find((x) => x.id === pick.id)
      return pt ? [pt.lon, pt.lat] : null
    })()
    return {
      // Same situation map on both pages; Driver cases adds the people pins on top.
      data: {
        info: region.info,
        points: region.points,
        roads: region.roads,
        ranked: s?.critical_points.map((p) => p.id) ?? [],
        areas: s?.nodes.filter((n) => n.status !== 'ok') ?? [],
        people: isPeople ? region.people : [],
        drones: s?.drones ?? [],
        trails: region.trails,
        pick,
      },
      onPick: setPick,
      focus,
    }
  }, [isSituation, isPeople, region.state, region.info, region.points, region.roads, region.people, region.trails, pick])

  // Driver cases: open the most urgent case once, when the first one arrives. Closing it then sticks.
  const autoSelected = useRef(false)
  useEffect(() => {
    if (isPeople && !autoSelected.current && !pick) {
      const first = region.people.find((p) => p.level === 'critical') ?? region.people.find((p) => p.level === 'danger')
      if (first) {
        autoSelected.current = true
        setPick({ kind: 'person', id: first.user_id })
      }
      return
    }
    if (!isCases || autoSelected.current || hasCase) return
    const first = cases.find((c) => caseSeverity(c) === 'critical') ?? cases.find((c) => c.state !== 'resolved')
    if (!first) return
    autoSelected.current = true
    store.setUi((u) => ({ ...u, selectedCaseId: first.id }))
  }, [isCases, isPeople, hasCase, cases, store, region.people, pick])

  const leftW = compact ? 240 : isCases ? 320 : isSituation ? 300 : 280
  const pickedPerson = isPeople && pick?.kind === 'person' ? region.people.find((p) => p.user_id === pick.id) ?? null : null
  const detailW = isPeople ? (pickedPerson ? 340 : 0) : hasCase || activeFeature ? (compact ? 320 : 360) : isSituation ? RIGHT_W : 0
  const vars = { '--left-w': `${leftW}px`, '--detail-w': `${detailW}px` } as CSSProperties
  const source = wx.load.status === 'ready' ? wx.load.source : null
  const regionLive = (isSituation || isPeople) && region.state?.mode === 'live'
  // Live: the newest active NWS alert from the region feed (none means none). Replay: the replay's own timeline.
  const liveAlert = regionLive ? [...(region.state?.alerts ?? [])].reverse().find((a) => a.active) : undefined
  const replayWarning = regionLive
    ? liveAlert ? { event: liveAlert.event, area: liveAlert.area ?? 'Kerr County', issuedAt: liveAlert.at ? Date.parse(liveAlert.at) : Date.now() } : null
    : source?.mode === 'replay' ? (wx.snapshot?.warning ?? null) : undefined
  const riskIndex = riskGrid.status === 'ready' ? riskGrid.index : null
  const riskCurrent = riskGrid.status === 'ready' ? riskGrid.current : null
  const risk = useMemo(() => ({ index: riskIndex, current: riskCurrent, area }), [riskIndex, riskCurrent, area])

  const regionNote = region.status === 'error'
    ? <p className={s.layerError} role="status">Region data unavailable: {region.error}. Start the backend, then reload.</p>
    : null

  const sums = peopleSummary(region.people)
  const situationLeft = (
    <div className={s.left}>
      {regionNote}
      <p className={s.statLine} aria-label="Situation">
        <a href={PAGE_PATH.cases} className={s.stat} title={`${sums.critical} critical, ${sums.danger} danger, ${sums.warning} at warning level. Open Driver cases.`}>
          <strong className={sums.critical + sums.danger ? s.statHot : ''}>{(sums.critical + sums.danger).toLocaleString()}</strong> in danger
        </a>
        <span className={s.stat}>
          <strong className={(region.state?.counters.households_cut_off ?? 0) ? s.statHot : ''}>{(region.state?.counters.households_cut_off ?? 0).toLocaleString()}</strong> homes cut off
        </span>
        <span className={s.stat}>
          <strong>{(region.state?.counters.points_checked ?? 0).toLocaleString()}</strong> drone checks
        </span>
      </p>
      <AreasPanel areas={region.state?.nodes ?? []} pick={pick} onPick={setPick} />
    </div>
  )

  const peopleLeft = (
    <div className={s.left}>
      {regionNote}
      <PeoplePanel people={region.people} total={region.peopleTotal} names={region.names} pick={pick} onPick={setPick} preview={60} />
    </div>
  )

  const townLeft = (
    <div className={s.left}>
      {!compact && (
        <label className={s.search}>
          <Search size={14} aria-hidden="true" />
          <input type="search" data-console-search placeholder={isCases ? 'Search drivers or roads' : 'Search cases'} value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search cases by driver or road" />
          <kbd className={s.kbd}>/</kbd>
        </label>
      )}
      {!isCases && <LayerPanel wx={wx} />}
      {!isCases && wx.layers.base === 'risk' && riskGrid.status === 'error' && (
        <p className={s.layerError} role="status">
          Risk surface unavailable. {riskGrid.message}{' '}
          <button type="button" onClick={riskGrid.retry}>Retry</button>
        </p>
      )}
      <Queue tabs={isCases} filter={query} />
      {!isCases && wx.snapshot && <GaugeTable gauges={wx.snapshot.gauges} feature={activeFeature} onFeature={selectFeature} />}
    </div>
  )

  const stage = (
    <div className={s.stage}>
      <MapView padding={{ left: leftW + GAP * 2, right: detailW ? detailW + GAP * 2 : GAP, bottom: GAP }} wx={wx} feature={activeFeature} onFeature={selectFeature} risk={risk} region={regionMap} />
      {isSituation ? situationLeft : isPeople ? peopleLeft : townLeft}
      {pickedPerson && <PersonDetail person={pickedPerson} name={region.names[pickedPerson.user_id] ?? 'Unnamed person'} onClose={() => setPick(null)} />}
      {regionPage && <LayersMenu wx={wx} />}
      {isSituation && !activeFeature && (
        <FleetPanel state={region.state} pointNames={region.pointNames} pick={pick} onPick={setPick} />
      )}
      {regionPage && <MapKey people={isPeople} />}
      {!isPeople && !isSituation && <Colorbar wx={wx} studyArea={risk.index?.studyArea ? `Study area: ${risk.index.studyArea}` : undefined} />}
      {hasCase && !isSituation && <Detail onClose={closeDetail} />}
      {activeFeature && wx.snapshot && source && (
        <FeatureDetail feature={activeFeature} snap={wx.snapshot} town={townState.status === 'ready' ? townState.town : null} range={source.range} onClose={() => setFeature(null)} />
      )}
    </div>
  )

  if (compact) {
    return (
      <div className={`${s.console} ${s.compact}`} data-theme="dispatch" data-scheme={scheme} style={vars}>
        <TopBar compact replayWarning={replayWarning} />
        {stage}
        <TimeSlider wx={wx} riskFrames={risk.index?.frames} />
        <footer className={s.footer}>
          <span>{source?.note ?? 'Demo data'}</span>
          <span>Concept prototype. Demo data where marked.</span>
        </footer>
      </div>
    )
  }

  return (
    <AppShell page={page} status={<HeaderStatus replayWarning={replayWarning} dataTime={regionLive ? simT : source ? wx.t : null} connection={isSituation || isPeople ? (region.status === 'ready' ? (region.error ? 'reconnecting' : 'live') : region.status === 'error' ? 'reconnecting' : 'connecting') : undefined} />}>
      <div className={s.console} style={vars}>
        {stage}
        {(regionPage || !isCases) && (
          <TimeSlider
            wx={wx}
            riskFrames={risk.index?.frames}
            replay={regionPage ? { mode: region.state?.mode ?? 'replay', setMode: region.setMode, liveAt: region.state?.mode === 'live' ? simT : null, feeds: region.state?.sources, running, start: region.start, reset: region.reset } : undefined}
            chart={regionPage ? region.history : undefined}
          />
        )}
      </div>
    </AppShell>
  )
}
