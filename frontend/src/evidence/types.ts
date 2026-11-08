export type Access = 'open' | 'closed' | 'restricted' | 'unknown'
export interface Observation {
  id: string; source_id: string; observed_at: string | null; ingested_at: string
  kind: string; road_id?: string | null; access: Access; quality: string; simulated: boolean
  source_mode?: 'live' | 'cached' | 'unavailable' | 'simulated' | 'manual'
  raw: Record<string, unknown>; value?: number | null; unit?: string | null
}
export interface Road {
  id: string; name: string; geometry: GeoJSON.LineString; access: Access
  freshness: 'current' | 'stale' | 'missing'; agreement: 'consistent' | 'conflicting'
  evidence_ids: string[]; reasons?: string[]
}
export interface Task {
  id: string; road_id: string; road_name: string; status: 'queued' | 'assigned' | 'completed' | 'inconclusive'
  priority: number; reasons: string[]; affected_communities: string[]
  /** Observations the backend cited when ranking this task (includes area context such as warnings). */
  evidence_ids?: string[]
}
export interface Community {
  id: string; name: string; node_id: string; optimistic_access: boolean
  conservative_access: boolean; remaining_exits?: number
}
export interface Source {
  id?: string; source_id?: string; name?: string; status?: string; last_status?: string
  last_success_at?: string | null; last_fetched_at?: string | null; detail?: string
  fetched_at?: string | null
  last_successful_fetch_at?: string | null; last_attempt_at?: string | null
}
export interface EvidenceState {
  generated_at: string; dataset: { id: string; name: string; simulated: boolean; description?: string }
  observations: Observation[]; roads: Road[]; tasks: Task[]; communities: Community[]; sources: Source[]
  /** Known gaps in the analysis, stated by the backend. */
  limitations?: string[]
}
