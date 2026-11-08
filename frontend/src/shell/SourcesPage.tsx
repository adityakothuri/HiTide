import { CircleCheck, CircleDashed, CircleSlash, History, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { FeedStatus, Feeds } from '../data/types'
import { formatClock } from '../lib/format'
import { useRiskGrid } from '../risk/useRiskGrid'
import { useStore } from '../state/StoreContext'
import { AppShell } from './AppShell'
import s from './SourcesPage.module.css'

type State = 'live' | 'cached' | 'replay' | 'unavailable'

const STATE: Record<State, { label: string; icon: LucideIcon }> = {
  live: { label: 'Live', icon: CircleCheck },
  cached: { label: 'Cached', icon: History },
  replay: { label: 'Replay', icon: CircleDashed },
  unavailable: { label: 'Unavailable', icon: CircleSlash },
}

interface Row {
  name: string
  provider: string
  use: string
  state: State
  detail: string
}

function feedRow(f: FeedStatus | undefined, name: string, provider: string, use: string, recorded: boolean): Row {
  if (!f) return { name, provider, use, state: 'unavailable', detail: 'Not reported by the backend' }
  // The offline demo replays a recorded sample re-timed to now; never present it as live.
  if (recorded) return { name, provider, use, state: 'cached', detail: 'Recorded sample, offline demo' }
  return {
    name,
    provider,
    use,
    state: f.source,
    detail: f.fetched_at ? `Fetched ${formatClock(f.fetched_at)}` : 'No successful fetch',
  }
}

/** Every input the console uses, with where it comes from and how fresh it is. Status is icon plus label. */
export function SourcesPage() {
  const store = useStore()
  const [feeds, setFeeds] = useState<Feeds | null>(null)
  const [feedError, setFeedError] = useState<string | null>(null)
  const risk = useRiskGrid(0, true)

  useEffect(() => {
    let alive = true
    store.provider.getFeeds().then(
      (f) => alive && setFeeds(f),
      (e: unknown) => alive && setFeedError(e instanceof Error ? e.message : 'Feed status unavailable'),
    )
    return () => {
      alive = false
    }
  }, [store])

  const riskDetail =
    risk.status === 'ready'
      ? `${risk.index.frames.length} frames, ${risk.index.cellM} m cells, ${risk.index.studyArea}`
      : risk.status === 'error'
        ? risk.message
        : 'Loading'

  const recorded = store.provider.kind === 'mock'
  const rows: Row[] = [
    feedRow(feeds?.nws_alerts, 'Weather alerts', 'National Weather Service', 'Active warning in the header; warning marks on the time bar', recorded),
    feedRow(feeds?.usgs_gage, 'River gauges', 'USGS Water Data', 'Gauge dots, stage charts, river gauge list', recorded),
    feedRow(feeds?.usgs_flood_impacts, 'Flood impact points', 'USGS Flood Impacts', 'Road evidence for inspections', recorded),
    { name: 'Rainfall', provider: 'NOAA MRMS via Iowa Environmental Mesonet', use: 'Rainfall base field; rain factor of the risk index', state: 'replay', detail: 'Archived tiles, July 4, 2025' },
    { name: 'Flood risk index', provider: 'HiTide model (USGS 3DEP, OSM waterways, MRMS)', use: 'Flood risk base field and hover readout', state: risk.status === 'ready' ? 'replay' : risk.status === 'error' ? 'unavailable' : 'cached', detail: riskDetail },
    { name: 'Modelled flood depth', provider: 'HiTide model (USGS 3DEP 10 m)', use: 'Flood depth base field, road closures', state: 'replay', detail: 'One frame per 0.5 m of river rise' },
    { name: 'Roads and basemap', provider: 'OpenStreetMap, CARTO', use: 'Road network, routing, basemap', state: 'cached', detail: 'Town road graph bundled for offline use' },
  ]

  return (
    <AppShell page="sources">
      <div className={s.page}>
        <h1 className={s.h1}>Sources</h1>
        <p className={s.lede}>Where each layer comes from and how fresh it is. Replay sources are the July 4, 2025 event, played back offline.</p>
        {feedError && <p className={s.error} role="status">Backend feed status unavailable: {feedError}. Showing the bundled sources only.</p>}
        <table className={s.table}>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">Provider</th>
              <th scope="col">Used for</th>
              <th scope="col">Status</th>
              <th scope="col">Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const st = STATE[r.state]
              const Icon = st.icon
              return (
                <tr key={r.name}>
                  <th scope="row">{r.name}</th>
                  <td>{r.provider}</td>
                  <td>{r.use}</td>
                  <td>
                    <span className={`${s.status} ${s[r.state]}`}>
                      <Icon size={14} aria-hidden="true" />
                      {st.label}
                    </span>
                  </td>
                  <td className="num">{r.detail}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </AppShell>
  )
}
