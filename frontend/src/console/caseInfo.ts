import type { Case, OutreachEvent, TimelineEntry, Town } from '../data/types'
import { humanize, personaFor } from '../data/personas'
import { ageBand } from '../lib/format'
import { nearestStreet, streetFromText } from '../lib/geo'

const SIM_MARK = /\s*\((?:mock|simulated)[^)]*\)/gi

/** "75+" from the persona, else the coarse band the backend puts in urgency_reasons. */
export function caseAgeBand(c: Case): string | null {
  const p = personaFor(c.driver_id)
  if (p) return ageBand(p.age)
  for (const r of c.urgency_reasons) {
    const m = /\((\d+\+|\d+[–-]\d+|under \d+)\)/i.exec(r)
    if (m) return m[1]
  }
  return null
}

export function caseVehicle(c: Case): string | null {
  return c.vehicle ?? personaFor(c.driver_id)?.vehicle ?? null
}

/** Street the car is on: named in the call copy, else the nearest named road. */
export function casePlace(c: Case, outreach: readonly OutreachEvent[], town: Town | null): string | null {
  for (const o of outreach) {
    if (o.case_id !== c.id) continue
    const s = streetFromText(o.body)
    if (s) return s
  }
  return nearestStreet(town, c.location.lat, c.location.lon)
}

export function isSimulatedText(text: string): boolean {
  return /\((?:mock|simulated)/i.test(text)
}

export interface TimelineRow {
  id: string
  ts: string
  text: string
  kind: string
  simulated: boolean
}

/** Case timeline with persona names and the "(mock)" markers lifted into a tag. */
export function timelineRows(c: Case): TimelineRow[] {
  return c.timeline.map((e: TimelineEntry, i) => {
    const raw = humanize(c.driver_id, e.text)
    const simulated = Boolean(e.simulated) || isSimulatedText(raw)
    const text = raw.replace(SIM_MARK, '').replace(/:\s*$/, '').trim()
    return { id: `${c.id}-${i}`, ts: e.ts, text: text || raw, kind: e.kind, simulated }
  })
}

const CHANNEL: Record<OutreachEvent['channel'], string> = {
  text: 'Text',
  voice: 'Voice call',
  poll: 'Poll',
  tts_in_app: 'Spoken in app',
}

export function recipientLabel(o: OutreachEvent): string {
  const p = personaFor(o.driver_id)
  if (o.recipient === 'driver') return p ? `${p.name.split(' ')[0]} (driver)` : 'Driver'
  if (o.recipient === 'parent') return 'Parent'
  return p ? `${p.contact.name} (${p.contact.relation})` : 'Emergency contact'
}

export function channelLabel(o: OutreachEvent): string {
  return CHANNEL[o.channel]
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)

/**
 * One plain sentence from the backend's urgency reasons:
 * "Stopped in 21 in of rising water at night. Older driver (65+), low-clearance vehicle."
 */
export function riskSummary(reasons: readonly string[]): string {
  if (reasons.length === 0) return ''
  const used = new Set<string>()
  const find = (re: RegExp) => {
    const r = reasons.find((x) => re.test(x))
    if (r) used.add(r)
    return r
  }
  const stopped = find(/stopped/i)
  const depth = find(/^\d+(?:\.\d+)? in of water$/i)?.replace(/ of water$/i, '')
  const rising = find(/rising/i)
  const night = find(/^night$/i)

  let first = ''
  if (stopped || depth || rising) {
    const water = depth ? `${depth} of ${rising ? 'rising ' : ''}water` : rising ? 'rising floodwater' : 'floodwater'
    first = `${stopped ? 'Stopped in' : 'In'} ${water}${night ? ' at night' : ''}.`
  } else if (night) {
    first = 'At night.'
  }
  const rest = reasons.filter((r) => !used.has(r))
  const second = rest.length ? `${cap(rest.join(', '))}.` : ''
  return [first, second].filter(Boolean).join(' ')
}
