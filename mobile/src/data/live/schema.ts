import { z } from 'zod';

/**
 * The slice of the backend's per-user Assessment the app reads (docs/api-contract.md, "Per-user danger").
 * Unknown fields are dropped. Anything that fails validation is rejected as a whole, never half-applied.
 */

export const DANGER_LEVELS = ['none', 'watch', 'warning', 'danger', 'critical'] as const;
const level = z.enum(DANGER_LEVELS);

const roadHit = z.object({
  edge_id: z.string(),
  road_name: z.string().nullish(),
  distance_m: z.number().nullish(),
  depth_in: z.number().nullish(),
  point_status: z.string().nullish(),
});

const worstPoint = z.object({
  id: z.string(),
  name: z.string().nullish(),
  kind: z.string().nullish(),
  status: z.string().nullish(),
  distance_m: z.number().nullish(),
  on_my_road: z.boolean().nullish(),
});

const hazard = z.object({
  road_name: z.string().nullish(),
  depth_in: z.number().nullish(),
  alert_headlines: z.array(z.string()).default([]),
  in_warning: z.boolean().nullish(),
  in_emergency: z.boolean().nullish(),
  worst_point: worstPoint.nullish(),
  ahead: z.array(roadHit).default([]),
  route: z.array(roadHit).default([]),
  degraded_sources: z.array(z.string()).default([]),
});

/** Epoch seconds, bounded so a corrupt value can't throw later in Date#toISOString. */
const epochSeconds = z.number().finite().min(0).max(4_102_444_800);

const location = z.object({
  lat: z.number().finite().min(-90).max(90),
  lon: z.number().finite().min(-180).max(180),
  /** Epoch seconds (replay clock in replay mode). */
  ts: epochSeconds.nullish(),
  // Non-essential: an unknown value degrades to null rather than rejecting a critical assessment.
  state: z.enum(['parked', 'driving', 'stopped']).nullish().catch(null),
  speed_mps: z.number().finite().nullish().catch(null),
});

const timelineEntry = z.object({ t: epochSeconds, what: z.string() });

const response = z.object({
  episode_level: level.nullish(),
  awaiting_reply: z.boolean().default(false),
  called: z.boolean().default(false),
  family_contacted: z.boolean().default(false),
  responders_flagged: z.boolean().default(false),
  case_open: z.boolean().default(false),
  need_help: z.boolean().default(false),
  timeline: z.array(timelineEntry).default([]),
});

export const assessmentSchema = z.object({
  user_id: z.string(),
  level,
  advice: z.string(),
  reasons: z.array(z.string()).default([]),
  confidence: z.enum(['high', 'medium', 'low']).nullish().catch(null),
  stopped_in_water: z.boolean().default(false),
  location_stale: z.boolean().default(false),
  assessed_at: z.iso.datetime({ offset: true }),
  location: location.nullish(),
  hazard: hazard,
  response: response.nullish(),
});

export type Assessment = z.infer<typeof assessmentSchema>;
export type RoadHit = z.infer<typeof roadHit>;
export type TimelineEntry = z.infer<typeof timelineEntry>;

/** Validates an untrusted payload. Returns null instead of throwing. */
export function parseAssessment(raw: unknown): Assessment | null {
  const result = assessmentSchema.safeParse(raw);
  return result.success ? result.data : null;
}

const gaugeSchema = z.object({
  site: z.string(),
  name: z.string(),
  stage_ft: z.number().finite().nullish(),
  observed_at: epochSeconds.nullish(),
  flood_category: z.string().nullish(),
  rate_ft_per_hr: z.number().nullish(),
  online: z.boolean().nullish(),
});

export type RemoteGauge = z.infer<typeof gaugeSchema>;

export function parseGauges(raw: unknown): RemoteGauge[] | null {
  const result = z.array(gaugeSchema).safeParse(raw);
  return result.success ? result.data : null;
}

/** WS envelope `{type, seq, ts, payload}`. Only `user.danger` for this user is used, as a cue to refetch. */
const envelopeSchema = z.object({ type: z.string(), payload: z.object({ user_id: z.string().nullish() }).passthrough() });

export function isDangerEventFor(raw: unknown, userId: string): boolean {
  const result = envelopeSchema.safeParse(raw);
  return result.success && result.data.type === 'user.danger' && result.data.payload.user_id === userId;
}

const summarySchema = z.object({ mode: z.enum(['replay', 'live']), ready: z.boolean() });

export type SafetySummary = z.infer<typeof summarySchema>;

/** `GET /api/safety/summary`: only the backend mode and readiness are used. */
export function parseSummary(raw: unknown): SafetySummary | null {
  const result = summarySchema.safeParse(raw);
  return result.success ? result.data : null;
}

// ---- flood layer, directions, assistant line --------------------------------------------------------------------
const lonLat = z.tuple([z.number().finite(), z.number().finite()]);
const floodStatus = z.enum(['confirmed_flooded', 'likely_flooded', 'unknown', 'open']).catch('unknown');

const floodLayerSchema = z.object({
  at: z.string().nullish(),
  mode: z.string().nullish(),
  segments: z
    .array(z.object({ id: z.string(), status: floodStatus, name: z.string().nullish(), coords: z.array(lonLat).min(2) }))
    .default([]),
  points: z
    .array(
      z.object({
        id: z.string(),
        name: z.string().nullish(),
        kind: z.string().nullish(),
        status: floodStatus,
        lon: z.number().finite(),
        lat: z.number().finite(),
      }),
    )
    .default([]),
  gauges: z
    .array(
      z.object({
        site: z.string(),
        name: z.string(),
        lon: z.number().finite(),
        lat: z.number().finite(),
        stage_ft: z.number().finite().nullish(),
        flood_category: z.string().nullish(),
      }),
    )
    .default([]),
  alerts: z.array(z.object({ headline: z.string().nullish() })).default([]),
});

export type RemoteFloodLayer = z.infer<typeof floodLayerSchema>;

export function parseFloodLayer(raw: unknown): RemoteFloodLayer | null {
  const result = floodLayerSchema.safeParse(raw);
  return result.success ? result.data : null;
}

const directionsSchema = z.object({
  text: z.string(),
  kind: z.enum(['route', 'stay', 'none']).catch('none'),
  road_names: z.array(z.string()).default([]),
  length_m: z.number().finite().default(0),
  coords: z.array(z.array(lonLat)).default([]),
  avoid: z.array(z.string()).default([]),
});

export type RemoteDirections = z.infer<typeof directionsSchema>;

export function parseDirections(raw: unknown): RemoteDirections | null {
  const result = directionsSchema.safeParse(raw);
  return result.success ? result.data : null;
}

const assistantSchema = z.object({
  mode: z.enum(['live', 'mock', 'unavailable']),
  phone: z
    .string()
    .regex(/^\+?[0-9]{7,15}$/)
    .nullish(),
  directions: directionsSchema.nullish(),
});

export type RemoteAssistant = z.infer<typeof assistantSchema>;

export function parseAssistant(raw: unknown): RemoteAssistant | null {
  const result = assistantSchema.safeParse(raw);
  return result.success ? result.data : null;
}

const routeOptionsSchema = z.object({
  options: z
    .array(
      z.object({
        id: z.string(),
        label: z.string(),
        via: z.array(z.string()).default([]),
        length_m: z.number().finite().nonnegative(),
        minutes: z.number().int().nonnegative(),
        status: z.enum(['flooded', 'likely', 'clear']).catch('likely'),
        flooded: z.array(z.string()).default([]),
        likely: z.array(z.string()).default([]),
        coords: z.array(z.array(lonLat)).default([]),
      }),
    )
    .max(5)
    .default([]),
});

export type RemoteRouteOptions = z.infer<typeof routeOptionsSchema>;

export function parseRouteOptions(raw: unknown): RemoteRouteOptions | null {
  const result = routeOptionsSchema.safeParse(raw);
  return result.success ? result.data : null;
}
