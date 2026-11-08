import { Gallery } from './gallery/Gallery'
import { StoreProvider } from './state/StoreContext'
import { TipProvider } from './ui/Tip'
import { ToastProvider } from './ui/Toast'
import { Wordmark } from './ui/Wordmark'
import { Disclaimer } from './ui/Footer'
import { Operations } from './evidence/Operations'

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
    default:
      return <Index />
  }
}

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '')
  if (path === '' || path === '/console') return <Operations />
  return (
    <StoreProvider>
      <TipProvider>
        <ToastProvider>{route(window.location.pathname)}</ToastProvider>
      </TipProvider>
    </StoreProvider>
  )
}
