import { Activity, Car, ClipboardCheck, Layers, Moon, Sun } from 'lucide-react'
import type { ReactNode } from 'react'
import { setScheme, useScheme } from './scheme'
import s from './AppShell.module.css'

export type Page = 'monitor' | 'cases' | 'inspections' | 'sources'

export const PAGE_PATH: Record<Page, string> = {
  monitor: '/console',
  cases: '/console/cases',
  inspections: '/console/inspections',
  sources: '/console/sources',
}

const NAV: { page: Page; label: string; icon: typeof Activity }[] = [
  { page: 'monitor', label: 'Flood monitor', icon: Activity },
  { page: 'cases', label: 'Driver cases', icon: Car },
  { page: 'inspections', label: 'Inspections', icon: ClipboardCheck },
  { page: 'sources', label: 'Sources', icon: Layers },
]

const LABEL: Record<Page, string> = Object.fromEntries(NAV.map((n) => [n.page, n.label])) as Record<Page, string>

interface Props {
  page: Page
  /** Right side of the header: warning, data time, connection. */
  status?: ReactNode
  children: ReactNode
}

/** Operator shell: quiet sidebar, 48 px header, content fills the rest. Map pages run edge to edge. */
export function AppShell({ page, status, children }: Props) {
  const scheme = useScheme()
  return (
    <div className={s.shell} data-theme="dispatch" data-scheme={scheme}>
      <a className={s.skip} href="#main">Skip to content</a>
      <aside className={s.sidebar} aria-label="Workspace">
        <nav aria-label="Main" className={s.nav}>
          {NAV.map(({ page: p, label, icon: Icon }) => (
            <a key={p} href={PAGE_PATH[p]} aria-current={p === page ? 'page' : undefined} className={s.navItem}>
              <Icon size={18} aria-hidden="true" />
              {label}
            </a>
          ))}
        </nav>
        <div className={s.sideFoot}>
          <button
            type="button"
            className={s.schemeBtn}
            onClick={() => setScheme(scheme === 'light' ? 'dark' : 'light')}
            aria-label={scheme === 'light' ? 'Switch to night theme' : 'Switch to light theme'}
          >
            {scheme === 'light' ? <Moon size={16} aria-hidden="true" /> : <Sun size={16} aria-hidden="true" />}
            {scheme === 'light' ? 'Night theme' : 'Light theme'}
          </button>
          <p className={s.note}>Concept prototype. Demo data where marked.</p>
        </div>
      </aside>
      <header className={s.header}>
        <nav aria-label="Breadcrumb" className={s.crumbs}>
          <span title="Workspace: Guadalupe River basin">Kerr County, TX</span>
          <span aria-hidden="true">/</span>
          <strong aria-current="page">{LABEL[page]}</strong>
        </nav>
        <div className={s.status}>{status}</div>
      </header>
      <main id="main" className={s.main} tabIndex={-1}>
        {children}
      </main>
    </div>
  )
}
