import { Info, OctagonAlert, ShieldCheck, TriangleAlert, type LucideIcon } from 'lucide-react'

export type Tone = 'safe' | 'caution' | 'critical' | 'info'

export const TONE_ICON: Record<Tone, LucideIcon> = {
  safe: ShieldCheck,
  caution: TriangleAlert,
  critical: OctagonAlert,
  info: Info,
}

export const TONE_LABEL: Record<Tone, string> = {
  safe: 'Safe',
  caution: 'Caution',
  critical: 'Critical',
  info: 'Info',
}
