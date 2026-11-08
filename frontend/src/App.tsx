import { useEffect } from 'react'
import { Console } from './console/Console'
import { DriverApp } from './driver/DriverApp'
import { Gallery } from './gallery/Gallery'
import { DemoPanel } from './present/DemoPanel'
import { Present } from './present/Present'
import { useStore } from './state/StoreContext'
import { StoreProvider } from './state/StoreContext'
import { TipProvider } from './ui/Tip'
import { ToastProvider } from './ui/Toast'
import { Wordmark } from './ui/Wordmark'
import { Disclaimer } from './ui/Footer'

function Index() {
  return (
    <main style={{ padding: 'var(--space-4)', display: 'grid', gap: 'var(--space-2)', justifyItems: 'start' }}>
      <Wordmark />
      <nav aria-label="Views">
        <ul style={{ display: 'grid', gap: 'var(--space-1)', paddingLeft: 'var(--space-2)' }}>
          <li><a href="/present">Presentation (phone and console)</a></li>
          <li><a href="/driver">Driver app</a></li>
          <li><a href="/console">Operations console</a></li>
          <li><a href="/gallery">Component gallery</a></li>
        </ul>
      </nav>
      <Disclaimer />
    </main>
  )
}

function route(path: string) {
  switch (path.replace(/\/+$/, '')) {
    case '/gallery':
      return <Gallery />
    case '/driver':
      return <><DriverAutostart /><DriverApp framed={window.innerWidth > 500} /></>
    case '/console':
      return <Console />
    case '/present':
      return <Present />
    default:
      return <Index />
  }
}

/** `?autostart=1` on /driver starts the offline scenario (the console handles its own). */
function DriverAutostart() {
  const store = useStore()
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('autostart') !== '1' || store.provider.kind !== 'mock') return
    const t = window.setTimeout(() => void store.provider.startDemo(), 300)
    return () => window.clearTimeout(t)
  }, [store])
  return null
}

export default function App() {
  return (
    <StoreProvider>
      <TipProvider>
        <ToastProvider>
          {route(window.location.pathname)}
          <DemoPanel />
        </ToastProvider>
      </TipProvider>
    </StoreProvider>
  )
}
