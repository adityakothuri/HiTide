import { useEffect, useState } from 'react'
import { backendModes, forcedDataMode, type BackendModes, type DataMode } from '../config/dataMode'
import s from './DataModeBadge.module.css'

interface Label { text: string; tone: 'test' | 'real' | 'live' | 'offline'; title: string }

function labelFor(forced: DataMode | null, modes: BackendModes | null | undefined, liveOnly: boolean): Label | null {
  if (modes === undefined) return null // still loading
  if (liveOnly) {
    return { text: 'Live data', tone: 'real', title: 'This monitor only shows readings from the last 15-30 minutes, so it is live in both test and real mode' }
  }
  if (modes === null) {
    return { text: 'Recorded demo', tone: 'offline', title: 'Backend not reachable: playing bundled demo data' }
  }
  const mode = forced ?? (modes.data_mode === 'real' ? 'real' : 'test')
  const detail = `Feeds ${modes.feeds}, outreach ${modes.outreach}, region ${modes.region}`
  if (mode === 'test') return { text: 'Test data', tone: 'test', title: `Simulated and cached data. ${detail}` }
  if (modes.outreach !== 'mock') {
    return { text: 'Real data · live texts', tone: 'live', title: `Texts and calls go to real phones. ${detail}` }
  }
  return { text: 'Real data', tone: 'real', title: `Live feeds. ${detail}` }
}

interface DataModeBadgeProps {
  className?: string
  /** The screen has no test dataset (e.g. the Texas monitor): always say live. */
  liveOnly?: boolean
}

/** Says whether the screen shows test or real data (and whether real texts can go out). */
export function DataModeBadge({ className = '', liveOnly = false }: DataModeBadgeProps) {
  const [modes, setModes] = useState<BackendModes | null | undefined>(undefined)
  useEffect(() => {
    let alive = true
    void backendModes().then((m) => alive && setModes(m))
    return () => {
      alive = false
    }
  }, [])
  const label = labelFor(forcedDataMode(), modes, liveOnly)
  if (!label) return null
  return (
    <span className={`${s.badge} ${s[label.tone]} ${className}`} title={label.title} data-testid="data-mode">
      <span className={s.dot} aria-hidden="true" />
      {label.text}
    </span>
  )
}
