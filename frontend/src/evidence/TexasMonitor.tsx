import { useEffect, useMemo, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { LogoMark } from '../ui/LogoMark'
import { useNow } from '../lib/useNow'
import { DataModeBadge } from '../ui/DataModeBadge'
import boundary from './texasBoundary.json'
import s from './Operations.module.css'
import t from './TexasMonitor.module.css'

const labels: Record<string, string> = {
  drivetexas_work_zones: 'Construction restrictions',
  nws_local_storm_reports: 'Road flood reports',
  nws_alerts: 'Flood alerts',
  usgs_gage: 'River gages',
} as const
type Source = string
type Category = 'alert' | 'road' | 'river' | 'rain' | 'other'
const CATEGORY_OF: Record<string, Category> = {
  nws_alerts: 'alert',
  nws_local_storm_reports: 'road', atx_flood_closures: 'road', sariver_crossings: 'road', hcfcd_inundation: 'road',
  transtar_incidents: 'road', transtar_lane_closures: 'road', transtar_flood_risk: 'road',
  usgs_gage: 'river', noaa_nwps: 'river', lcra_hydromet: 'river', hcfcd_water_levels: 'river',
  noaa_mrms: 'rain', noaa_flash: 'rain',
}
const CATEGORIES: { key: Category; label: string }[] = [
  { key: 'alert', label: 'Flood alerts' }, { key: 'road', label: 'Flooded roads' }, { key: 'river', label: 'River levels' },
  { key: 'rain', label: 'Rain and runoff' }, { key: 'other', label: 'Other' },
]
const categoryOf = (source: string): Category => CATEGORY_OF[source] ?? 'other'
const CATEGORY_RANK: Record<Category, number> = { alert: 0, road: 1, river: 2, other: 3, rain: 4 }
type Preview = { title: string; detail: string; time: string | null; geometry?: GeoJSON.Geometry | null; evidence_type: string; timestamp_role: string; link?: string; value?: number }
type Envelope = {
  preview?: Preview | null
  provider_metadata?: { feed_updated_at?: string }
  source_record_id: string | null
  attempt_id: string
  record_index: number | null
  raw_payload: { properties?: Record<string, unknown>; geometry?: GeoJSON.Geometry | null }
}
type Batch = { label?: string; notes?: string; errors?: string[]; context?: Envelope[]; records: Envelope[]; status: 'complete' | 'partial' | 'unavailable'; excluded: Record<string, number> }
type Snapshot = { scope: string; as_of: string; max_age_minutes: number; sources: Partial<Record<Source, Batch>> }
type Entry = { id: string; source: Source; title: string; detail: string; stamp: number; expiry?: number; geometry?: GeoJSON.Geometry | null; link?: string; category?: string; context?: boolean; value?: number }

function formatTime(stamp: number) {
  if (!Number.isFinite(stamp)) return 'Time unverified'
  return new Date(stamp).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' })
}

function mapGeometry(value: unknown): GeoJSON.Point | GeoJSON.LineString | GeoJSON.MultiLineString | GeoJSON.Polygon | GeoJSON.MultiPolygon | null {
  if (!value || typeof value !== 'object' || !('type' in value) || !('coordinates' in value)) return null
  const point = (p: unknown): p is number[] => Array.isArray(p) && p.length >= 2
    && Number.isFinite(p[0]) && Math.abs(p[0]) <= 180 && Number.isFinite(p[1]) && Math.abs(p[1]) <= 90
  const polygon = (p: unknown): p is number[][][] => Array.isArray(p) && p.length > 0
    && p.every(ring => Array.isArray(ring) && ring.length >= 4 && ring.every(point))
  const xy = value.coordinates
  const line = (p: unknown): p is number[][] => Array.isArray(p) && p.length >= 2 && p.every(point)
  if (value.type === 'LineString' && line(xy)) return { type: 'LineString', coordinates: xy }
  if (value.type === 'MultiLineString' && Array.isArray(xy) && xy.length > 0 && xy.every(line)) return { type: 'MultiLineString', coordinates: xy }
  if (value.type === 'Point' && point(xy)) return { type: 'Point', coordinates: xy }
  if (value.type === 'Polygon' && polygon(xy)) return { type: 'Polygon', coordinates: xy }
  if (value.type === 'MultiPolygon' && Array.isArray(xy) && xy.length > 0 && xy.every(polygon)) return { type: 'MultiPolygon', coordinates: xy }
  return null
}

function entry(record: Envelope, source: Source): Entry {
  if (record.preview) {
    const p = record.preview
    return { id: `${source}/${record.source_record_id ?? `${record.attempt_id}/${record.record_index}`}`,
      source, title: p.title, detail: p.detail, stamp: p.time ? Date.parse(p.time) : NaN,
      geometry: mapGeometry(p.geometry), value: p.value, category: `${p.evidence_type} · ${p.timestamp_role.replaceAll('_', ' ')}`,
      link: p.link?.startsWith('https://') ? p.link : undefined }
  }
  const props = record.raw_payload?.properties ?? {}
  const text = (field: string) => typeof props[field] === 'string' ? String(props[field]).trim() : ''
  let title, detail, timestamp, expiry
  if (source === 'drivetexas_work_zones') {
    const core = props.core_details as Record<string, unknown> | undefined
    title = Array.isArray(core?.road_names) ? core.road_names.join(' / ') : 'Work zone'
    const description = typeof core?.description === 'string' ? core.description.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim() : ''
    detail = [text('vehicle_impact').replaceAll('-', ' '), description,
      `Scheduled through ${text('end_date')}`,
      core?.update_date && `Record updated ${String(core.update_date)}`].filter(Boolean).join(' · ')
    timestamp = record.provider_metadata?.feed_updated_at ?? ''
    expiry = Date.parse(text('end_date'))
  } else if (source === 'nws_alerts') {
    title = text('event') || 'Flood bulletin'
    detail = text('areaDesc') || text('headline')
    timestamp = text('sent')
    expiry = Date.parse(text('expires'))
  } else if (source === 'usgs_gage') {
    title = text('monitoring_location_name') || text('monitoring_location_id') || 'USGS station'
    detail = props.value == null || !text('unit_of_measure') ? 'River stage unavailable' : `River stage · ${props.value} ${text('unit_of_measure')}`
    timestamp = text('time')
  } else {
    title = [text('city'), text('county') && `${text('county')} County`].filter(Boolean).join(' · ') || 'Texas road report'
    detail = text('remark')
    timestamp = text('valid')
  }
  return { id: `${source}/${record.source_record_id ?? `${record.attempt_id}/${record.record_index}`}`,
    source, title, detail, stamp: Date.parse(timestamp), expiry, geometry: mapGeometry(record.raw_payload?.geometry) }
}

// Fixed Texas equirectangular extent. Both the Census outline and all reported geometries use lon/lat.
function project([lon, lat]: number[]) {
  return [55 + (lon + 106.7) * 41, 24 + (36.6 - lat) * 48]
}
function ringPath(ring: number[][]) {
  return ring.map((p, i) => `${i === 0 ? 'M' : 'L'}${project(p).map(n => n.toFixed(1)).join(' ')}`).join(' ') + 'Z'
}
const outline = boundary.rings.map(ringPath).join(' ')
const cities: [string, number, number][] = [
  ['El Paso', -106.49, 31.76], ['Amarillo', -101.83, 35.22], ['Dallas', -96.8, 32.78],
  ['Austin', -97.74, 30.27], ['Houston', -95.37, 29.76], ['Brownsville', -97.5, 25.9],
]
function Mark({ item, selected, choose }: { item: Entry; selected: boolean; choose: () => void }) {
  const g = item.geometry
  if (!g) return null
  const className = `${t[categoryOf(item.source)]} ${selected ? t.selected : ''}`
  const grid = item.source === 'noaa_mrms' || item.source === 'noaa_flash'
  const fraction = Math.min(1, Math.max(0, (item.value ?? 0) / (item.source === 'noaa_mrms' ? 25 : 5)))
  const gridStyle = grid ? { fill: item.source === 'noaa_mrms' ? '#2f7f86' : '#5b5bb5', fillOpacity: 0.06 + 0.6 * fraction, stroke: 'none' } : undefined
  // Every marker has an equivalent keyboard-accessible button in the observation list.
  const title = <title>{item.title} · {item.detail}</title>
  if (g.type === 'Point' && grid) {
    // 0.5° grid cell centred on the point: a shaded raster, not a station marker.
    const [x0, y0] = project([g.coordinates[0] - 0.25, g.coordinates[1] + 0.25])
    const [x1, y1] = project([g.coordinates[0] + 0.25, g.coordinates[1] - 0.25])
    return <rect className={className} style={gridStyle} x={x0} y={y0} width={x1 - x0} height={y1 - y0} onClick={choose}>{title}</rect>
  }
  if (g.type === 'Point') {
    const [x, y] = project(g.coordinates)
    return <circle className={className} style={gridStyle} cx={x} cy={y} r={selected ? 6.5 : categoryOf(item.source) === 'river' ? 2.6 : 4.2} onClick={choose}>{title}</circle>
  }
  if (g.type === 'Polygon' || g.type === 'MultiPolygon') {
    const rings = g.type === 'Polygon' ? g.coordinates : g.coordinates.flat()
    return <path className={className} style={gridStyle} d={rings.map(ringPath).join(' ')} fillRule="evenodd" onClick={choose}>{title}</path>
  }
  if (g.type === 'LineString' || g.type === 'MultiLineString') {
    const lines = g.type === 'LineString' ? [g.coordinates] : g.coordinates
    const path = lines.map(line => line.map((p, i) => `${i ? 'L' : 'M'}${project(p).join(' ')}`).join(' ')).join(' ')
    return <path className={className} d={path} onClick={choose}>{title}</path>
  }
  return null
}

export function TexasMonitor() {
  const [minutes, setMinutes] = useState(30)
  const [reload, setReload] = useState(0)
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [source, setSource] = useState<Source | ''>('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState('')
  const [limit, setLimit] = useState(20)
  const [includeContext, setIncludeContext] = useState(false)
  const [category, setCategory] = useState<Category | ''>('')
  const clock = useNow(5_000)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const response = await fetch(`/api/feeds/recent?map_view=true&max_age_minutes=${minutes}`, { signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw new Error()
        const next: Snapshot = await response.json()
        if (next.scope !== 'texas' || next.max_age_minutes !== minutes || !next.sources || !Number.isFinite(Date.parse(next.as_of))) throw new Error()
        if (!controller.signal.aborted) { setSnapshot(next); setError('') }
      } catch {
        if (!controller.signal.aborted) { setSnapshot(null); setError('Texas feed unavailable. Retrying in one minute.') }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 60_000)
      }
    }
    void poll()
    return () => { controller.abort(); clearTimeout(timer) }
  }, [minutes, reload])

  const current = snapshot?.max_age_minutes === minutes ? snapshot : null
  const sources = useMemo(() => [...new Set([...Object.keys(labels), ...Object.keys(current?.sources ?? {})])], [current])
  const label = (key: string) => current?.sources[key]?.label ?? labels[key] ?? key.replaceAll('_', ' ')
  const entries = useMemo(() => sources.flatMap(key => [
    ...(current?.sources[key]?.records ?? []).map(row => entry(row, key)),
    ...(includeContext ? (current?.sources[key]?.context ?? []).map(row => ({ ...entry(row, key), context: true })) : []),
  ]), [current, sources, includeContext])
  const asOf = Math.max(clock, current ? Date.parse(current.as_of) : 0)
  const inWindow = entries.filter(row => row.context || (row.stamp <= asOf && asOf - row.stamp <= minutes * 60_000 && (row.expiry === undefined || row.expiry > asOf)))
  const counts = CATEGORIES.map(c => ({ ...c, n: inWindow.filter(row => !row.context && categoryOf(row.source) === c.key).length }))
  const visible = inWindow
    .filter(row => (!source || row.source === source) && (!category || categoryOf(row.source) === category)
      && `${row.title} ${row.detail}`.toLowerCase().includes(query.toLowerCase().trim()))
    .sort((a, b) => Number(!!a.context) - Number(!!b.context)
      || CATEGORY_RANK[categoryOf(a.source)] - CATEGORY_RANK[categoryOf(b.source)]
      || (b.stamp - a.stamp || a.id.localeCompare(b.id)))
  const active = visible.find(row => row.id === selected)
  const complete = current && sources.every(key => current.sources[key]?.status === 'complete')
  const reporting = current ? sources.filter(key => current.sources[key]?.status !== 'unavailable').length : 0
  const statusText = (key: string) => {
    const batch = current?.sources[key]
    if (!current) return error ? 'Source unavailable' : 'Checking…'
    return batch?.status === 'complete' ? 'Request complete' : batch?.status === 'partial' ? 'Partial results' : 'Source unavailable'
  }

  return <div className={t.app}>
    <a className={s.skip} href="#texas-main">Skip to Texas monitoring</a>
    <header className={t.topbar}>
      <a href="/" className={t.brand} aria-label="HiTide home"><LogoMark size={30} /><span>HiTide</span></a>
      <nav aria-label="Main" className={t.tabs}><a href="/texas" aria-current="page">Texas monitor</a><a href="/console">Kerrville test case</a></nav>
      <div className={t.topRight}>
        <DataModeBadge liveOnly />
        <span className={t.checked}>{current ? `Updated ${formatTime(Date.parse(current.as_of))}` : error ? 'Not connected' : 'Connecting…'}</span>
        <button className={t.iconButton} onClick={() => setReload(n => n + 1)} aria-label="Refresh"><RefreshCw size={16} /></button>
      </div>
    </header>
    <main id="texas-main" className={t.main}>
      <div className={t.heading}>
        <div>
          <h1>Texas flood monitor</h1>
          <p>Flood alerts, flooded roads, river levels and radar rain across Texas, from {sources.length} public sources.</p>
        </div>
        <label className={t.window}>Observation window<select value={minutes} onChange={e => { setMinutes(Number(e.target.value)); setLimit(20) }}>
          <option value={15}>Past 15 minutes</option><option value={30}>Past 30 minutes</option></select></label>
      </div>
      {error && <p role="alert" className={t.error}><span className={t.errorDot} />{error}</p>}
      <div className={t.stats} role="group" aria-label="Filter by category">
        {counts.map(c => <button key={c.key} className={t.stat} aria-pressed={category === c.key}
          onClick={() => { setCategory(category === c.key ? '' : c.key); setLimit(20) }}>
          <span className={t.statLabel}><i className={t[c.key]} />{c.label}</span>
          <strong>{current ? c.n.toLocaleString() : '–'}</strong>
        </button>)}
        <details className={t.sourceDetails}>
          <summary><span className={t.statLabel}>Sources reporting</span><strong>{current ? `${reporting}/${sources.length}` : '–'}</strong></summary>
          <div className={t.coverage} aria-label="Source coverage">
            {sources.map(key => { const batch = current?.sources[key]; const st = statusText(key)
              return <div key={key}>
                <span className={t.coverageName}><i className={st === 'Request complete' ? t.ok : st === 'Partial results' ? t.partial : t.down} />{label(key)}</span>
                <span className={t.coverageStatus}>{st}</span>
                {batch?.notes && <small>{batch.notes}</small>}
                {!!batch?.errors?.length && <small>{batch.errors.join(', ').replaceAll('_', ' ')}</small>}
                {!!batch && Object.entries(batch.excluded).filter(([reason]) => reason !== 'empty').map(([reason, count]) => <small key={reason}>{count} excluded · {reason.replaceAll('_', ' ')}</small>)}
              </div>
            })}
          </div>
        </details>
      </div>
      <div className={t.workspace}>
        <section className={t.card} aria-labelledby="tx-map-title">
          <div className={t.cardHead}><h2 id="tx-map-title">Statewide map</h2>
            {category && <button className={t.clear} onClick={() => setCategory('')}>Show all categories</button>}</div>
          <svg className={t.map} viewBox="0 0 665 575" role="img" aria-label="Texas observation map. Matching observations are listed alongside the map.">
            <defs><clipPath id="tx-state-clip"><path d={outline} /></clipPath></defs>
            <path d={outline} className={t.boundary} />
            <g clipPath="url(#tx-state-clip)">
              {[...visible].reverse().filter(row => categoryOf(row.source) === 'rain').map(row => <Mark key={row.id} item={row} selected={false} choose={() => setSelected(row.id)} />)}
            </g>
            <path d={outline} className={t.boundaryLine} />
            {[...visible].reverse().filter(row => categoryOf(row.source) !== 'rain').map(row => <Mark key={row.id} item={row} selected={false} choose={() => setSelected(row.id)} />)}
            {cities.map(([name, lon, lat]) => { const [x, y] = project([lon, lat]); return <g key={name} className={t.city}><circle cx={x} cy={y} r="2.2" /><text x={x + 6} y={y - 6}>{name}</text></g> })}
            {active && <Mark item={active} selected choose={() => setSelected(active.id)} />}
          </svg>
          {(source === 'noaa_mrms' || source === 'noaa_flash' || category === 'rain') && <p className={t.caption}>Rain cells show the maximum on a 0.5° grid; darker means more rain (up to 25 mm/hour) or more modeled runoff. Cells describe an area, not individual roads.</p>}
          <p className={t.caption}>Unmarked roads have unknown conditions. River gauges measure water height at one station; road depth needs a local observation.</p>
          <small className={t.credit}>State boundary: <a href="https://tigerweb.geo.census.gov/arcgis/rest/services/Generalized_ACS2019/State_County/MapServer/9">U.S. Census Bureau</a></small>
        </section>
        <section className={`${t.card} ${t.listCard}`} aria-labelledby="tx-records-title">
          <div className={t.cardHead}><h2 id="tx-records-title">Observations</h2>{current && <span className={t.count}>{visible.length.toLocaleString()}</span>}</div>
          <div className={t.filters}>
            <label className={t.search}>Find a location<input value={query} placeholder="Road, county or station" onChange={e => { setQuery(e.target.value); setLimit(20) }} /></label>
            <label>Source<select value={source} onChange={e => { setSource(e.target.value as Source | ''); setLimit(20) }}>
              <option value="">All sources</option>{sources.map(key => <option key={key} value={key}>{label(key)}</option>)}</select></label>
            <label className={t.check}><input type="checkbox" checked={includeContext} onChange={e => setIncludeContext(e.target.checked)} />Include source context with unverified freshness</label>
          </div>
          {active && <div className={t.selection}>
            <span className={t.meta}><i className={t[categoryOf(active.source)]} />{label(active.source)} · {formatTime(active.stamp)}{!active.geometry && ' · Geometry unavailable'}</span>
            <strong>{active.title}</strong><p>{active.detail}</p>
            {active.category && <small>{active.category}</small>}
            <div className={t.selectionActions}>
              {active.link && <a href={active.link} target="_blank" rel="noreferrer">Open provider data</a>}
              <button className={t.clear} onClick={() => setSelected('')}>Clear selection</button>
            </div>
          </div>}
          <div className={t.results}>
            {!visible.length && <p className={t.empty}>{error ? 'Current observations unavailable.' : !current ? 'Retrieving Texas observations…' : !complete ? 'No matching observations in the available data. Coverage is incomplete.' : 'No matching observations in this time window.'}</p>}
            {visible.slice(0, limit).map(row => <button key={row.id} className={t.record} aria-pressed={selected === row.id} onClick={() => setSelected(row.id)}>
              <i className={t[categoryOf(row.source)]} />
              <span className={t.recordBody}>
                <span className={t.recordTop}><strong>{row.title}</strong><time>{formatTime(row.stamp)}</time></span>
                <span className={t.detail}>{row.detail || 'Detail unavailable'}</span>
                <span className={t.meta}>{label(row.source)}{!row.geometry && ' · Geometry unavailable'}</span>
              </span>
            </button>)}
            {visible.length > limit && <button className={t.more} onClick={() => setLimit(n => n + 20)}>Show more observations</button>}
          </div>
        </section>
      </div>
    </main>
  </div>
}
