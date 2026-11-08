import { FileText, House, Route, Settings as Gear } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useTown } from '../hooks/useTown'
import { Disclaimer } from '../ui/Footer'
import { ConnectionChip } from '../ui/States'
import { useStore, useUi } from '../state/StoreContext'
import { IncomingCall } from './IncomingCall'
import { PushBanner } from './PushBanner'
import { Home } from './screens/Home'
import { Warning } from './screens/Warning'
import { TurnAround } from './screens/TurnAround'
import { CheckIn } from './screens/CheckIn'
import { Help } from './screens/Help'
import { Claim, ClaimsTab } from './screens/Claim'
import { Settings } from './screens/Settings'
import { Trips } from './screens/Trips'
import { driverFromUrl, useDriverView, type DriverView } from './useDriverView'
import s from './Driver.module.css'

type Tab = 'home' | 'trips' | 'claims' | 'profile'

const TABS: { key: Tab; label: string; icon: typeof House }[] = [
  { key: 'home', label: 'Home', icon: House },
  { key: 'trips', label: 'Trips', icon: Route },
  { key: 'claims', label: 'Claims', icon: FileText },
  { key: 'profile', label: 'Settings', icon: Gear },
]

const URGENT = new Set(['en_route', 'check_in', 'help'])

const TAB_TITLE: Record<Tab, string> = { home: 'HiTide', trips: 'Trips', claims: 'Claims', profile: 'Settings' }

const clock = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago' })

function StatusBar() {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  return (
    <div className={s.statusBar} aria-hidden="true">
      <span className="num">{clock.format(now).replace(/\s?[AP]M$/, '')}</span>
      <span className={s.statusIcons}>
        <span className={s.signal}><i /><i /><i /><i /></span>
        <span className={s.battery}><i /></span>
      </span>
    </div>
  )
}

function HomeContent({ view, onSettings }: { view: DriverView; onSettings: () => void }) {
  const { state: town } = useTown()
  const t = town.status === 'ready' ? town.town : null
  switch (view.screen) {
    case 'warning':
      return <Warning view={view} town={t} />
    case 'check_in':
      return <CheckIn view={view} town={t} />
    case 'help':
      return <Help view={view} town={t} />
    case 'after':
      return <Claim view={view} />
    default:
      return <Home view={view} onSettings={onSettings} />
  }
}

/** The State Farm driver app with HiTide. `framed` draws a phone around it for desktop and /present. */
export function DriverApp({ framed = false, driverId }: { framed?: boolean; driverId?: string | null }) {
  const view = useDriverView(driverId ?? driverFromUrl())
  const status = useUi((u) => u.status)
  const [tab, setTab] = useState<Tab>('home')
  const mainRef = useRef<HTMLElement>(null)
  const { state: town } = useTown()
  const store = useStore()
  const handled = useUi((u) => u.handled)
  const markHandled = useCallback((id: string) => store.setUi((u) => ({ ...u, handled: { ...u.handled, [id]: true } })), [store])

  const call = view.screen === 'check_in' && view.call && view.case && !handled[view.call.id] ? view.call : null
  const push = view.screen === 'warning' && view.pretrip && !handled[view.pretrip.id] && !view.turnAround ? view.pretrip : null
  const callId = call?.id
  const pushId = push?.id
  const endCall = useCallback(() => callId && markHandled(callId), [callId, markHandled])
  const dismissPush = useCallback(() => pushId && markHandled(pushId), [pushId, markHandled])

  // Urgent screens always take the user back to Home.
  const urgent = URGENT.has(view.screen)
  useEffect(() => {
    if (urgent) setTab('home')
  }, [urgent, view.screen])

  // New screen: scroll to top. Coming out of the takeover, move focus to the new heading.
  const prevScreen = useRef(view.screen)
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0 })
    if (prevScreen.current === 'en_route' && view.screen !== 'en_route') {
      mainRef.current?.querySelector<HTMLElement>('h2')?.focus()
    }
    prevScreen.current = view.screen
  }, [tab, view.screen])

  const turnAround = view.screen === 'en_route' && view.turnAround !== null
  const takeover = turnAround || call !== null

  const brand = tab === 'home' && view.screen === 'calm'
  let content: ReactNode
  if (tab === 'trips') content = <Trips view={view} />
  else if (tab === 'claims') content = <ClaimsTab view={view} />
  else if (tab === 'profile') content = <Settings view={view} />
  else content = <HomeContent view={view} onSettings={() => setTab('profile')} />

  const app = (
    <div className={`${s.app} ${framed ? s.framed : ''}`} data-screen={view.screen} data-tone={brand ? 'brand' : undefined} data-framed={framed}>
      {framed && <StatusBar />}
      {!brand && (
        <header className={`${s.nav} ${tab !== 'home' ? s.navLarge : ''}`} inert={takeover}>
          <span />
          {tab === 'home' ? <h1 className={s.navTitle}>HiTide</h1> : <h1 className="visually-hidden">{TAB_TITLE[tab]}</h1>}
          {tab === 'home' ? (
            <button type="button" className={s.navButton} onClick={() => setTab('profile')} aria-label="HiTide settings">
              <Gear aria-hidden="true" />
            </button>
          ) : <span />}
        </header>
      )}
      {brand && <h1 className="visually-hidden">HiTide</h1>}
      {status === 'reconnecting' && (
        <div className={s.connection}>
          <ConnectionChip status={status} />
        </div>
      )}
      <main ref={mainRef} className={s.main} inert={takeover}>
        {content}
        <Disclaimer className={s.disclaimer} />
      </main>
      <nav className={s.tabBar} aria-label="App sections" inert={takeover}>
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            className={s.tab}
            aria-current={tab === key ? 'page' : undefined}
            onClick={() => setTab(key)}
          >
            <Icon aria-hidden="true" className={s.tabIcon} />
            <span>{label}</span>
          </button>
        ))}
      </nav>
      {turnAround && <TurnAround view={view} town={town.status === 'ready' ? town.town : null} />}
      {call && view.case && <IncomingCall call={call} caseId={view.case.id} onDone={endCall} />}
      {push && !takeover && (
        <PushBanner
          message={push}
          onOpen={() => {
            dismissPush()
            setTab('home')
          }}
          onDismiss={dismissPush}
        />
      )}
    </div>
  )

  if (!framed) return <div className={s.page}>{app}</div>
  return (
    <div className={s.device}>
      <div className={s.screen}>
        {app}
        <span className={s.island} aria-hidden="true" />
        <span className={s.homeIndicator} aria-hidden="true" />
      </div>
    </div>
  )
}
