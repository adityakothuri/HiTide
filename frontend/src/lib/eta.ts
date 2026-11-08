const ARRIVING_S = 10

/** Minutes the drone reaches the car ahead of the ground crew. Null if either ETA is unknown. */
export function minutesGained(crewEtaS: number | null | undefined, droneEtaS: number | null | undefined): number | null {
  if (crewEtaS == null || droneEtaS == null) return null
  return Math.max(0, Math.round((crewEtaS - droneEtaS) / 60))
}

/** "Arriving now", "42 s", "2 min", "1 hr 5 min". */
export function formatEta(seconds: number): string {
  if (seconds < ARRIVING_S) return 'Arriving now'
  if (seconds < 60) return `${Math.round(seconds)} s`
  const mins = Math.ceil(seconds / 60)
  if (mins < 60) return `${mins} min`
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m === 0 ? `${h} hr` : `${h} hr ${m} min`
}
