import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import { useTown } from '../hooks/useTown'
import { caseSeverity } from '../state/cases'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { useWx } from '../wx/useWx'
import { Colorbar } from './Colorbar'
import { Detail } from './Detail'
import { FeatureDetail } from './FeatureDetail'
import { GaugeTable } from './GaugeTable'
import { LayerPanel } from './LayerPanel'
import { MapView, type Feature } from './MapView'
import { Queue } from './Queue'
import { TimeSlider } from './TimeSlider'
import { TopBar } from './TopBar'
import s from './Console.module.css'

const BASE_TITLE = 'Flood operations | HiTide'
const GAP = 8

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
 * Ops console: a full-bleed hydromet map (rain, modelled flood depth, gauges, road closures) with a thin
 * left panel for layers and cases, an always-on colorbar, a time slider, and detail only on click.
 * `compact` narrows the panels for /present.
 */
export function Console({ compact = false }: { compact?: boolean }) {
  useAutostart()
  const store = useStore()
  const wx = useWx()
  const { state: townState } = useTown()
  const cases = useApp((a) => a.cases)
  const selected = useUi((u) => u.selectedCaseId)
  const critical = useMemo(() => cases.filter((c) => caseSeverity(c) === 'critical').length, [cases])
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

  const leftW = compact ? 232 : 256
  const detailW = hasCase ? (compact ? 320 : 360) : activeFeature ? 320 : 0
  const vars = { '--left-w': `${leftW}px`, '--detail-w': `${detailW}px` } as CSSProperties
  const source = wx.load.status === 'ready' ? wx.load.source : null

  return (
    <div className={`${s.console} ${compact ? s.compact : ''}`} data-theme="dispatch" style={vars}>
      <TopBar compact={compact} replayWarning={source?.mode === 'replay' ? (wx.snapshot?.warning ?? null) : undefined} />
      <div className={s.stage}>
        <MapView padding={{ left: leftW + GAP * 2, right: detailW ? detailW + GAP * 2 : GAP, bottom: GAP }} wx={wx} feature={activeFeature} onFeature={selectFeature} />
        <div className={s.left}>
          <LayerPanel wx={wx} />
          {wx.snapshot && <GaugeTable gauges={wx.snapshot.gauges} feature={activeFeature} onFeature={selectFeature} />}
          <Queue />
        </div>
        <Colorbar wx={wx} />
        {hasCase && (
          <Detail
            onClose={() => {
              setFeature(null)
              store.setUi((u) => ({ ...u, selectedCaseId: null }))
            }}
          />
        )}
        {activeFeature && wx.snapshot && source && (
          <FeatureDetail feature={activeFeature} snap={wx.snapshot} town={townState.status === 'ready' ? townState.town : null} range={source.range} onClose={() => setFeature(null)} />
        )}
      </div>
      <TimeSlider wx={wx} />
      <footer className={s.footer}>
        <span>{source?.note ?? 'Demo data'}</span>
        <span>Concept prototype. Not an official State Farm product.</span>
      </footer>
    </div>
  )
}
