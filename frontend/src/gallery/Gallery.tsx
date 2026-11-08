import { Hand, Phone, Route, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Banner } from '../ui/Banner'
import { Button } from '../ui/Button'
import { Card, Section } from '../ui/Card'
import { Counter } from '../ui/Counter'
import { FilterTabs } from '../ui/FilterTabs'
import { Disclaimer } from '../ui/Footer'
import { ConnectionChip, EmptyState, ErrorState, Loading, Skeleton, StaleIndicator } from '../ui/States'
import { StatusBadge } from '../ui/StatusBadge'
import { Timeline } from '../ui/Timeline'
import { Tip } from '../ui/Tip'
import { useToast } from '../ui/Toast'
import { Wordmark } from '../ui/Wordmark'
import s from './Gallery.module.css'

const COLOR_GROUPS: { title: string; tokens: string[] }[] = [
  { title: 'Brand and text', tokens: ['brand-red', 'ink', 'surface', 'surface-page'] },
  { title: 'Neutrals', tokens: ['neutral-1', 'neutral-2', 'neutral-3', 'neutral-4', 'neutral-5', 'neutral-6'] },
  { title: 'Water depth', tokens: ['water-1', 'water-2', 'water-3', 'water-4', 'water-5'] },
  { title: 'Status', tokens: ['safe', 'safe-bg', 'caution', 'caution-bg', 'critical', 'critical-bg', 'critical-deep', 'info', 'info-bg'] },
]

const TYPE_STEPS = ['2xl', 'xl', 'lg', 'md', 'sm', 'xs']

export function Gallery() {
  const toast = useToast()
  const [filter, setFilter] = useState<'critical' | 'contacting' | 'drone' | 'resolved'>('critical')
  const now = Date.now()

  return (
    <div className={s.page}>
      <header className={s.top}>
        <Wordmark />
        <h1 className={s.topNote}>Component gallery</h1>
      </header>

      <main className={s.main}>
        <Section title="Color tokens">
          <div className={s.groups}>
            {COLOR_GROUPS.map((g) => (
              <div key={g.title}>
                <p className={s.groupTitle}>{g.title}</p>
                <div className={s.swatches}>
                  {g.tokens.map((t) => (
                    <div key={t} className={s.swatch}>
                      <span className={s.chip} style={{ background: `var(--${t})` }} />
                      <code>--{t}</code>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Type scale (Public Sans)">
          <div className={s.stack}>
            {TYPE_STEPS.map((step) => (
              <p key={step} style={{ fontSize: `var(--text-${step})`, lineHeight: `var(--lh-${step})`, fontWeight: step === '2xl' || step === 'xl' ? 700 : 400 }}>
                <span className="num">14</span> minutes gained on Water St
              </p>
            ))}
          </div>
        </Section>

        <Section title="Buttons">
          <div className={s.row}>
            <Button icon={Route}>Use safer route</Button>
            <Button aria-disabled="true" icon={ShieldCheck}>Using safer route</Button>
            <Button variant="secondary">View claim</Button>
            <Button variant="quiet">Remind me later</Button>
            <Button variant="emergency" icon={Phone}>Call 911</Button>
          </div>
          <div className={s.phoneCol}>
            <Button variant="safe" size="xl" icon={ShieldCheck} block>I'm safe</Button>
            <Button variant="critical" size="xl" icon={Hand} block>I need help</Button>
            <Button size="lg" block>Use safer route</Button>
          </div>
          <div className={`${s.darkRow} on-dark`}>
            <Button variant="onDark" size="lg" block>Show new route</Button>
          </div>
        </Section>

        <Section title="Status (icon, label and color, never color alone)">
          <div className={s.row}>
            <StatusBadge tone="critical" />
            <StatusBadge tone="caution" />
            <StatusBadge tone="safe" />
            <StatusBadge tone="info" label="Simulated" />
            <StatusBadge tone="critical" quiet label="Critical" />
          </div>
        </Section>

        <Section title="Banners">
          <div className={s.stack}>
            <Banner tone="caution" title="Flash flood warning">Kerr County until 2:15 AM. Simulated warning for this demo.</Banner>
            <Banner tone="safe" title="HiTide is on">No flood warnings near you.</Banner>
            <Banner tone="critical" title="Car stopped in floodwater">Water St at the Guadalupe River, about 20 in of water.</Banner>
            <Banner tone="info" title="Using safer route">Adds about 4 minutes.</Banner>
          </div>
        </Section>

        <Section title="Timeline">
          <div className={s.twoCol}>
            <Card>
              <Timeline
                showStatus
                items={[
                  { id: '1', time: '8:42 PM', title: 'We called you', status: 'done' },
                  { id: '2', time: '8:43 PM', title: 'We contacted Maria', detail: 'Emergency contact', status: 'done' },
                  { id: '3', time: '8:43 PM', title: 'Drone on the way', detail: 'Arriving in 2 min', status: 'active' },
                  { id: '4', title: 'Rescue team notified', status: 'waiting' },
                ]}
              />
            </Card>
            <Card>
              <Timeline
                size="sm"
                items={[
                  { id: 'a', time: '8:42 PM', title: 'Car stopped in floodwater' },
                  { id: 'b', time: '8:42 PM', title: 'Voice call to driver, no answer yet', tag: <StatusBadge tone="info" label="Mock" /> },
                  { id: 'c', time: '8:43 PM', title: 'Text to Maria Hale: read, replied "On my way"' },
                ]}
              />
            </Card>
          </div>
        </Section>

        <Section title="Counters and filters">
          <div className={s.row}>
            <Counter value={42} label="Warned" />
            <Counter value={17} label="Rerouted" />
            <Counter value={3} label="Stopped in water" />
            <Counter value={9} label="Confirmed safe" />
          </div>
          <div className={s.spaced}>
            <FilterTabs
              label="Filter cases"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'critical', label: 'Critical', count: 2 },
                { value: 'contacting', label: 'Contacting', count: 1 },
                { value: 'drone', label: 'Drone en route', count: 1 },
                { value: 'resolved', label: 'Resolved', count: 9 },
              ]}
            />
          </div>
        </Section>

        <Section title="Data states">
          <div className={s.twoCol}>
            <Card>
              <p className={s.groupTitle}>Loading</p>
              <Loading label="Loading cases">
              <div className={s.stack}>
                <Skeleton width="40%" height={14} />
                <Skeleton height={14} />
                <Skeleton width="70%" height={14} />
                <Skeleton height={120} radius="md" />
              </div>
              </Loading>
            </Card>
            <Card flush>
              <EmptyState title="No cars are stopped in water">Cases appear here when a trip stops on a flooded road.</EmptyState>
            </Card>
            <Card flush>
              <ErrorState what="Couldn't load road data" how="Check that the backend is running on port 8000, then retry." onRetry={() => toast('Retrying', 'Loading road data again.')} />
            </Card>
            <Card>
              <p className={s.groupTitle}>Freshness and connection</p>
              <div className={s.stack}>
                <StaleIndicator label="NWS" iso={new Date(now - 60_000).toISOString()} now={now} />
                <StaleIndicator label="USGS" iso={new Date(now - 6 * 60_000).toISOString()} now={now} />
                <StaleIndicator label="USGS impacts" iso={null} now={now} />
                <ConnectionChip status="live" />
                <ConnectionChip status="reconnecting" />
                <ConnectionChip status="offline_demo" />
              </div>
            </Card>
          </div>
        </Section>

        <Section title="Overlays">
          <div className={s.row}>
            <Button variant="secondary" onClick={() => toast('Using safer route', 'Your directions now avoid Water St.')}>Show a toast</Button>
            <Tip content="Water depth comes from the flood simulation, not a gauge on this road.">
              <Button variant="secondary">Hover for a tooltip</Button>
            </Tip>
          </div>
        </Section>
      </main>

      <footer className={s.footer}>
        <Disclaimer />
      </footer>
    </div>
  )
}
