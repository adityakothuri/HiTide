// Demo personas. The backend's demo drivers carry teammate placeholder names ("Teammate A (demo)").
// The UI shows these realistic Kerrville personas instead, keyed by driver id. Fictional people.

export interface Persona {
  name: string
  age: number
  vehicle: string
  contact: { name: string; relation: string; phone: string }
  trip: { label: string; destination: string }
  claim: { number: string; tow: string; towWhen: string; rental: string }
  aliases: string[] // placeholder strings in backend text to replace with contact.name
}

const PERSONAS: Record<string, Persona> = {
  'demo-a': {
    name: 'Dana Whitfield', age: 34, vehicle: '2018 Honda Civic',
    contact: { name: 'Chris Whitfield', relation: 'spouse', phone: '(830) 555-0101' },
    trip: { label: 'Work', destination: 'Peterson Regional Medical Center' },
    claim: { number: '31-8842-K11', tow: 'Select Service shop on Junction Hwy', towWhen: 'tomorrow at 8 AM', rental: 'Reserved near Sidney Baker St' },
    aliases: ['Emergency contact'],
  },
  'demo-b': {
    name: 'Luis Ortega', age: 27, vehicle: '2021 Toyota Camry',
    contact: { name: 'Ana Ortega', relation: 'sister', phone: '(830) 555-0102' },
    trip: { label: 'School', destination: 'Schreiner University' },
    claim: { number: '31-8842-K14', tow: 'Select Service shop on Junction Hwy', towWhen: 'tomorrow at 9 AM', rental: 'Reserved near Sidney Baker St' },
    aliases: ['Emergency contact'],
  },
  'demo-d': {
    name: 'Margaret Hale', age: 78, vehicle: '2019 Toyota Camry',
    contact: { name: 'Maria Hale', relation: 'daughter', phone: '(830) 555-0142' },
    trip: { label: 'Church', destination: 'Notre Dame Catholic Church' },
    claim: { number: '31-8842-K17', tow: 'Select Service shop on Junction Hwy', towWhen: 'tomorrow at 8 AM', rental: 'Reserved near Sidney Baker St' },
    aliases: ['Teammate C (demo relative)'],
  },
  'demo-t': {
    name: 'Jordan Ruiz', age: 17, vehicle: '2017 Hyundai Elantra',
    contact: { name: 'Dana Whitfield', relation: 'parent', phone: '(830) 555-0101' },
    trip: { label: 'School', destination: 'Tivy High School' },
    claim: { number: '31-8842-K19', tow: 'Select Service shop on Junction Hwy', towWhen: 'tomorrow at 10 AM', rental: 'Reserved near Sidney Baker St' },
    aliases: ['Teammate A (demo parent)'],
  },
}

export const DEFAULT_DRIVER_ID = 'demo-d'

export function personaFor(driverId: string): Persona | null {
  return PERSONAS[driverId] ?? null
}

/** Display name: persona name for demo drivers, otherwise the backend name. */
export function displayName(driverId: string, backendName: string): string {
  return personaFor(driverId)?.name ?? backendName
}

/** Swap teammate placeholders in backend text for persona names. */
export function humanize(driverId: string, text: string): string {
  const p = personaFor(driverId)
  if (!p) return text
  return p.aliases.reduce((t, alias) => t.split(alias).join(p.contact.name), text)
}

export function ageFromReasons(reasons: readonly string[]): number | null {
  for (const r of reasons) {
    const m = /^age (\d+)/.exec(r)
    if (m) return Number(m[1])
  }
  return null
}

// Backend demo narration names teammates. Swap in the persona names for the presenter caption.
const NARRATION_NAMES: [RegExp, string][] = [
  [/Teammate A('s)?/g, 'Dana$1'],
  [/Teammate B('s)?/g, 'Luis$1'],
  [/Teammate C('s)?/g, 'Maria$1'],
]

export function humanizeNarration(text: string): string {
  return NARRATION_NAMES.reduce((t, [re, name]) => t.replace(re, name), text)
}
