import type { Case, DroneCommand, Reply, TimelineEntry } from './types'

// Client-side stand-ins for actions the backend may not support yet (see "Proposed additions" in
// docs/api-contract.md). Every entry is marked simulated so the UI labels it.

function entry(c: Case, kind: string, text: string, now: Date): TimelineEntry {
  const t = (now.getTime() - Date.parse(c.opened_at)) / 1000
  return { ts: now.toISOString(), t_case_s: Math.max(0, Math.round(t)), kind, text, simulated: true }
}

export function caseAfterReply(c: Case, reply: Reply, now = new Date()): Case {
  if (reply === 'safe') {
    return { ...c, state: 'resolved', timeline: [...c.timeline, entry(c, 'reply', 'Driver replied: I\'m safe', now), entry(c, 'state', 'Resolved', now)] }
  }
  return { ...c, responder_flag: true, timeline: [...c.timeline, entry(c, 'reply', 'Driver replied: I need help', now)] }
}

const COMMAND_TEXT: Record<DroneCommand, string> = {
  speak: 'Drone spoke to driver: "Help is coming. Stay on the roof."',
  drop_jacket: 'Drone dropped a life jacket next to the car',
  return: 'Drone returning to Kerrville Fire Station 1',
}

export function caseAfterDroneCommand(c: Case, cmd: DroneCommand, now = new Date()): Case {
  return { ...c, timeline: [...c.timeline, entry(c, 'drone', COMMAND_TEXT[cmd], now)] }
}
