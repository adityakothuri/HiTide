// Flood Watch primary database (SpacetimeDB 2.14, TypeScript module).
//
// The Python FastAPI backend is the only writer: it calls these reducers over HTTP with the database owner's token,
// and reads with SQL. Every write reducer checks that the caller is the owner recorded at first publish, so other
// clients on the network can only read the public tables (and can subscribe to them for live updates).
// Structured bodies are stored as JSON strings (body_json) next to the indexed columns Python filters on.
// Private tables (phones, profiles, positions, outreach ladders, key-value state) are readable only by the owner.

import { schema, table, t, SenderError, type InferSchema, type ReducerCtx } from 'spacetimedb/server';

// ---- configuration --------------------------------------------------------
const config = table(
  { name: 'config' },
  {
    id: t.u32().primaryKey(),
    owner: t.identity(),
    schemaVersion: t.u32(),
  }
);

// ---- evidence (was SQLite/Mongo: sources, raw_records, observations, ingestion_runs, settings, tasks) ----
const source = table(
  { name: 'source', public: true },
  {
    id: t.string().primaryKey(),
    name: t.string(),
    category: t.string(),
    attribution: t.string(),
    expectedUpdateS: t.u32(),
  }
);

const rawRecord = table(
  {
    name: 'raw_record',
    indexes: [{ accessor: 'by_source_hash', algorithm: 'btree', columns: ['sourceId', 'payloadHash'] }],
  },
  {
    seq: t.u64().primaryKey().autoInc(),
    sourceId: t.string(),
    payloadHash: t.string(),
    payloadJson: t.string(),
    receivedAt: t.string(),
  }
);

const observation = table(
  {
    name: 'observation',  // private: community reports can name people; ops reads via the backend
    indexes: [{ accessor: 'by_record', algorithm: 'btree', columns: ['sourceId', 'sourceRecordId'] }],
  },
  {
    seq: t.u64().primaryKey().autoInc(),
    id: t.string().unique(),
    sourceId: t.string(),
    sourceRecordId: t.string(),
    observedAt: t.option(t.string()),
    ingestedAt: t.string(),
    semanticHash: t.string().unique(),
    supersedesId: t.option(t.string()),
    rawSeq: t.u64(),
    kind: t.string(),
    roadId: t.option(t.string()),
    minLon: t.option(t.f64()),
    minLat: t.option(t.f64()),
    maxLon: t.option(t.f64()),
    maxLat: t.option(t.f64()),
    bodyJson: t.string(),
  }
);

const ingestionRun = table(
  { name: 'ingestion_run', public: true },
  {
    seq: t.u64().primaryKey().autoInc(),
    sourceId: t.string().index('btree'),
    status: t.string(),
    detail: t.string(),
    fetchedAt: t.string(),
    attemptedAt: t.string(),
  }
);

const setting = table(
  { name: 'setting' },  // private: dataset (roads, communities) is served through the backend API
  {
    key: t.string().primaryKey(),
    bodyJson: t.string(),
  }
);

const inspectionTask = table(
  { name: 'inspection_task' },  // private: tasks reference reports and assignees
  {
    id: t.string().primaryKey(),
    status: t.string().index('btree'),
    roadId: t.string().index('btree'),
    bodyJson: t.string(),
  }
);

// ---- people (was data/region_users.json, drivers.json, user_registry.json) ----
const appUser = table(
  { name: 'app_user', public: true },
  {
    id: t.string().primaryKey(),
    name: t.string(),            // enrolled (real) users: first name only
    age: t.option(t.u32()),      // enrolled users: hidden
    homeLat: t.f64(),            // enrolled users: rounded to ~1 km
    homeLon: t.f64(),
    simulated: t.bool(),
    consented: t.bool(),
    population: t.string().index('btree'),  // region | kerrville | enrolled
    tagsJson: t.string(),
  }
);

const userContact = table(
  { name: 'user_contact' },  // private: phone numbers never leave the owner
  {
    userId: t.string().primaryKey(),
    fullName: t.string(),
    age: t.option(t.u32()),
    homeLat: t.f64(),
    homeLon: t.f64(),
    phone: t.string(),
    contactName: t.option(t.string()),
    contactPhone: t.option(t.string()),
    parentPhone: t.option(t.string()),
  }
);

const userProfile = table(
  { name: 'user_profile' },  // private
  {
    userId: t.string().primaryKey(),
    profileJson: t.string(),
  }
);

// ---- live safety state (was data/safety_state.json + in-memory only) ----
const userTrack = table(
  { name: 'user_track' },  // private: precise positions
  {
    userId: t.string().primaryKey(),
    motionJson: t.string(),
    routeJson: t.string(),
    pinged: t.bool(),
    updatedAt: t.timestamp(),
  }
);

const responseState = table(
  { name: 'response_state' },  // private: the outreach ladder per user (survives restarts)
  {
    userId: t.string().primaryKey(),
    episodeLevel: t.string(),
    stateJson: t.string(),
    updatedAt: t.timestamp(),
  }
);

const dangerLatest = table(
  { name: 'danger_latest', public: true },  // live ops view; subscribe for real-time updates
  {
    userId: t.string().primaryKey(),
    level: t.string().index('btree'),
    hazardLevel: t.string(),
    topReason: t.string(),
    advice: t.string(),
    confidence: t.string(),
    lat: t.option(t.f64()),     // only for simulated users, or real users at danger+
    lon: t.option(t.f64()),
    vulnerabilityBand: t.string(),
    mode: t.string(),           // replay | live
    assessedAt: t.f64(),        // epoch seconds (sim clock in replay)
    updatedAt: t.timestamp(),
  }
);

// ---- outreach, cases, drone evidence, misc ----
const outreachEvent = table(
  { name: 'outreach_event' },  // private: message bodies name people and roads (never phone numbers)
  {
    id: t.string().primaryKey(),
    ts: t.string().index('btree'),
    driverId: t.string().index('btree'),
    recipient: t.string(),
    channel: t.string(),
    body: t.string(),
    mode: t.string(),
    status: t.string(),
    caseId: t.option(t.string()),
    provider: t.option(t.string()),
    callId: t.option(t.string()),
  }
);

const escalationCase = table(
  { name: 'escalation_case' },  // private: a case carries a person's position and contacts
  {
    id: t.string().primaryKey(),
    driverId: t.string().index('btree'),
    state: t.string().index('btree'),
    bodyJson: t.string(),
    updatedAt: t.timestamp(),
  }
);

const visionSnapshot = table(
  { name: 'vision_snapshot' },  // private: drone snapshots can include positions of people in water
  {
    id: t.string().primaryKey(),
    pointId: t.string().index('btree'),
    droneId: t.string(),
    time: t.string(),
    bodyJson: t.string(),
  }
);

const kv = table(
  { name: 'kv' },  // private: Photon2 inbound cursor, provider id mappings
  {
    key: t.string().primaryKey(),
    value: t.string(),
    updatedAt: t.timestamp(),
  }
);

const spacetimedb = schema({
  config, source, rawRecord, observation, ingestionRun, setting, inspectionTask,
  appUser, userContact, userProfile, userTrack, responseState, dangerLatest,
  outreachEvent, escalationCase, visionSnapshot, kv,
});
export default spacetimedb;

type Ctx = ReducerCtx<InferSchema<typeof spacetimedb>>;
const SCHEMA_VERSION = 1;
const MAX_BATCH = 2000;
const SEED_SOURCES: Array<[string, string, string, string, number]> = [
  ['nws_alerts', 'National Weather Service', 'warning', 'https://www.weather.gov/documentation/services-web-alerts', 120],
  ['usgs_gage', 'USGS Guadalupe River at Kerrville', 'gauge', 'https://api.waterdata.usgs.gov/docs/ogcapi', 300],
  ['usgs_flood_impacts', 'USGS flood impact reference points', 'context', 'https://api.waterdata.usgs.gov/rtfi-api/docs', 900],
  ['drivetexas', 'TxDOT DriveTexas', 'closure', 'https://api.drivetexas.org/api-docs', 300],
  ['local_reports', 'Local and community reports', 'report', 'Operator submissions', 300],
  ['drone', 'Drone inspections', 'drone', 'Mission evidence', 300],
];

// ---- helpers (not exported) ------------------------------------------------
function requireOwner(ctx: Ctx): void {
  const cfg = ctx.db.config.id.find(1);
  if (!cfg) throw new SenderError('database not initialised');
  if (!cfg.owner.isEqual(ctx.sender)) throw new SenderError('only the Flood Watch backend may write');
}

function parseArray(json: string, what: string): any[] {
  let v: unknown;
  try {
    v = JSON.parse(json);
  } catch {
    throw new SenderError(`${what}: invalid JSON`);
  }
  if (!Array.isArray(v)) throw new SenderError(`${what}: expected a JSON array`);
  if (v.length > MAX_BATCH) throw new SenderError(`${what}: batch larger than ${MAX_BATCH}`);
  return v;
}

function str(v: unknown, what: string): string {
  if (typeof v !== 'string' || v.length === 0) throw new SenderError(`${what} must be a non-empty string`);
  return v;
}

function optStr(v: unknown): string | undefined {
  return typeof v === 'string' && v.length > 0 ? v : undefined;
}

function optNum(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined;
}

function optAge(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 150 ? v : undefined;
}

function num(v: unknown, what: string): number {
  const n = Number(v);
  if (!Number.isFinite(n)) throw new SenderError(`${what} must be a finite number`);
  return n;
}

function ensureSource(ctx: Ctx, id: string): void {
  if (!ctx.db.source.id.find(id)) {
    ctx.db.source.insert({ id, name: id.replace(/_/g, ' '), category: 'report', attribution: 'Submitted evidence', expectedUpdateS: 300 });
  }
}

function latestRevision(ctx: Ctx, sourceId: string, sourceRecordId: string) {
  let best: { seq: bigint; id: string } | undefined;
  for (const row of ctx.db.observation.by_record.filter([sourceId, sourceRecordId])) {
    if (!best || row.seq > best.seq) best = { seq: row.seq, id: row.id };
  }
  return best;
}

// ---- lifecycle ---------------------------------------------------------------
export const init = spacetimedb.init(ctx => {
  ctx.db.config.insert({ id: 1, owner: ctx.sender, schemaVersion: SCHEMA_VERSION });
  for (const [id, name, category, attribution, expectedUpdateS] of SEED_SOURCES) {
    ctx.db.source.insert({ id, name, category, attribution, expectedUpdateS });
  }
});

// ---- evidence reducers ------------------------------------------------------------
export const upsertSource = spacetimedb.reducer(
  { id: t.string(), name: t.string(), category: t.string(), attribution: t.string(), expectedUpdateS: t.u32() },
  (ctx, a) => {
    requireOwner(ctx);
    const row = { id: str(a.id, 'id'), name: a.name, category: a.category, attribution: a.attribution, expectedUpdateS: a.expectedUpdateS };
    if (ctx.db.source.id.find(a.id)) ctx.db.source.id.update(row);
    else ctx.db.source.insert(row);
  }
);

// Atomic dedupe + revision chain (ported from backend/evidence/store.py add_observation).
// Python validates the observation and computes the semantic and raw hashes; this reducer decides
// whether it is new, which revision it supersedes, and stores it with its raw payload.
export const addObservation = spacetimedb.reducer(
  {
    semanticHash: t.string(),
    rawHash: t.string(),
    rawJson: t.string(),
    bodyJson: t.string(),
    minLon: t.option(t.f64()),
    minLat: t.option(t.f64()),
    maxLon: t.option(t.f64()),
    maxLat: t.option(t.f64()),
  },
  (ctx, a) => {
    requireOwner(ctx);
    if (ctx.db.observation.semanticHash.find(str(a.semanticHash, 'semanticHash'))) return; // duplicate: no-op
    let body: any;
    try {
      body = JSON.parse(a.bodyJson);
    } catch {
      throw new SenderError('bodyJson: invalid JSON');
    }
    const id = str(body.id, 'body.id');
    const sourceId = str(body.source_id, 'body.source_id');
    const sourceRecordId = str(body.source_record_id, 'body.source_record_id');
    if (ctx.db.observation.id.find(id)) throw new SenderError(`observation ${id} already exists with different content`);
    ensureSource(ctx, sourceId);
    const latest = latestRevision(ctx, sourceId, sourceRecordId);
    const given = optStr(body.supersedes_id);
    if (given && (!latest || given !== latest.id)) {
      throw new SenderError('supersedes_id must identify the latest revision of the same source record');
    }
    body.supersedes_id = given ?? (latest ? latest.id : null);
    let raw = ctx.db.rawRecord.by_source_hash.filter([sourceId, a.rawHash]).next();
    let rawSeq: bigint;
    if (!raw.done) {
      rawSeq = raw.value.seq;
    } else {
      rawSeq = ctx.db.rawRecord.insert({
        seq: 0n, sourceId, payloadHash: a.rawHash, payloadJson: a.rawJson, receivedAt: String(body.ingested_at ?? ''),
      }).seq;
    }
    ctx.db.observation.insert({
      seq: 0n, id, sourceId, sourceRecordId,
      observedAt: optStr(body.observed_at), ingestedAt: String(body.ingested_at ?? ''),
      semanticHash: a.semanticHash, supersedesId: body.supersedes_id ?? undefined, rawSeq,
      kind: String(body.kind ?? ''), roadId: optStr(body.road_id),
      minLon: a.minLon, minLat: a.minLat, maxLon: a.maxLon, maxLat: a.maxLat,
      bodyJson: JSON.stringify(body),
    });
  }
);

export const recordIngestion = spacetimedb.reducer(
  { sourceId: t.string(), status: t.string(), detail: t.string(), fetchedAt: t.string(), attemptedAt: t.string() },
  (ctx, a) => {
    requireOwner(ctx);
    ensureSource(ctx, str(a.sourceId, 'sourceId'));
    ctx.db.ingestionRun.insert({ seq: 0n, ...a });
  }
);

export const setSetting = spacetimedb.reducer(
  { key: t.string(), bodyJson: t.string() },
  (ctx, { key, bodyJson }) => {
    requireOwner(ctx);
    const row = { key: str(key, 'key'), bodyJson };
    if (ctx.db.setting.key.find(key)) ctx.db.setting.key.update(row);
    else ctx.db.setting.insert(row);
  }
);

export const saveTask = spacetimedb.reducer(
  { id: t.string(), status: t.string(), roadId: t.string(), bodyJson: t.string() },
  (ctx, a) => {
    requireOwner(ctx);
    const row = { id: str(a.id, 'id'), status: a.status, roadId: a.roadId, bodyJson: a.bodyJson };
    if (ctx.db.inspectionTask.id.find(a.id)) ctx.db.inspectionTask.id.update(row);
    else ctx.db.inspectionTask.insert(row);
  }
);

// ---- people ------------------------------------------------------------------------
// usersJson: [{id, name, age|null, home_lat, home_lon, simulated, consented, population, tags[],
//              public_name, public_age|null, public_lat, public_lon, phone, contact_name, contact_phone, parent_phone, profile{}}]
function putUser(ctx: Ctx, u: any): void {
  const id = str(u.id, 'user.id');
  const pub = {
    id, name: String(u.public_name ?? u.name ?? id), age: optAge(u.public_age),
    homeLat: num(u.public_lat, 'public_lat'), homeLon: num(u.public_lon, 'public_lon'),
    simulated: u.simulated === true, consented: u.consented === true,
    population: String(u.population ?? 'region'), tagsJson: JSON.stringify(u.tags ?? []),
  };
  const contact = {
    userId: id, fullName: String(u.name ?? id), age: optAge(u.age),
    homeLat: num(u.home_lat, 'home_lat'), homeLon: num(u.home_lon, 'home_lon'), phone: str(u.phone, 'user.phone'),
    contactName: optStr(u.contact_name), contactPhone: optStr(u.contact_phone), parentPhone: optStr(u.parent_phone),
  };
  const profile = { userId: id, profileJson: JSON.stringify(u.profile ?? {}) };
  if (ctx.db.appUser.id.find(id)) ctx.db.appUser.id.update(pub); else ctx.db.appUser.insert(pub);
  if (ctx.db.userContact.userId.find(id)) ctx.db.userContact.userId.update(contact); else ctx.db.userContact.insert(contact);
  if (ctx.db.userProfile.userId.find(id)) ctx.db.userProfile.userId.update(profile); else ctx.db.userProfile.insert(profile);
}

export const upsertUsers = spacetimedb.reducer(
  { usersJson: t.string() },
  (ctx, { usersJson }) => {
    requireOwner(ctx);
    for (const u of parseArray(usersJson, 'usersJson')) putUser(ctx, u);
  }
);

// Enrollment never overwrites anyone (no account takeover through the API).
export const enrollUser = spacetimedb.reducer(
  { userJson: t.string() },
  (ctx, { userJson }) => {
    requireOwner(ctx);
    const [u] = parseArray(`[${userJson}]`, 'userJson');
    if (ctx.db.appUser.id.find(str(u.id, 'user.id'))) throw new SenderError('id already enrolled');
    putUser(ctx, u);
  }
);

// ---- safety state ---------------------------------------------------------------------
// tracksJson: [{user_id, motion{}, route[], pinged}]
export const upsertTracks = spacetimedb.reducer(
  { tracksJson: t.string() },
  (ctx, { tracksJson }) => {
    requireOwner(ctx);
    for (const r of parseArray(tracksJson, 'tracksJson')) {
      const row = { userId: str(r.user_id, 'user_id'), motionJson: JSON.stringify(r.motion ?? null),
                    routeJson: JSON.stringify(r.route ?? []), pinged: r.pinged === true, updatedAt: ctx.timestamp };
      if (ctx.db.userTrack.userId.find(row.userId)) ctx.db.userTrack.userId.update(row); else ctx.db.userTrack.insert(row);
    }
  }
);

// responsesJson: [{user_id, episode_level, state{}}]
export const upsertResponses = spacetimedb.reducer(
  { responsesJson: t.string() },
  (ctx, { responsesJson }) => {
    requireOwner(ctx);
    for (const r of parseArray(responsesJson, 'responsesJson')) {
      const row = { userId: str(r.user_id, 'user_id'), episodeLevel: String(r.episode_level ?? 'none'),
                    stateJson: JSON.stringify(r.state ?? {}), updatedAt: ctx.timestamp };
      if (ctx.db.responseState.userId.find(row.userId)) ctx.db.responseState.userId.update(row); else ctx.db.responseState.insert(row);
    }
  }
);

// dangersJson: [{user_id, level, hazard_level, top_reason, advice, confidence, lat|null, lon|null, band, mode, assessed_at}]
export const upsertDangers = spacetimedb.reducer(
  { dangersJson: t.string() },
  (ctx, { dangersJson }) => {
    requireOwner(ctx);
    for (const d of parseArray(dangersJson, 'dangersJson')) {
      const row = {
        userId: str(d.user_id, 'user_id'), level: String(d.level), hazardLevel: String(d.hazard_level),
        topReason: String(d.top_reason ?? ''), advice: String(d.advice ?? 'none'), confidence: String(d.confidence ?? ''),
        lat: optNum(d.lat), lon: optNum(d.lon), vulnerabilityBand: String(d.band ?? ''), mode: String(d.mode ?? ''),
        assessedAt: num(d.assessed_at ?? 0, 'assessed_at'), updatedAt: ctx.timestamp,
      };
      if (ctx.db.dangerLatest.userId.find(row.userId)) ctx.db.dangerLatest.userId.update(row); else ctx.db.dangerLatest.insert(row);
    }
  }
);

// ---- outreach, cases, snapshots, kv -------------------------------------------------------
// eventsJson: [OutreachEvent payload] (backend/api/schemas.py OutreachEvent; no phone numbers)
export const logOutreach = spacetimedb.reducer(
  { eventsJson: t.string() },
  (ctx, { eventsJson }) => {
    requireOwner(ctx);
    for (const e of parseArray(eventsJson, 'eventsJson')) {
      const id = str(e.id, 'event.id');
      if (ctx.db.outreachEvent.id.find(id)) continue;  // idempotent (migration re-runs)
      ctx.db.outreachEvent.insert({
        id, ts: String(e.ts ?? ''), driverId: String(e.driver_id ?? ''), recipient: String(e.recipient ?? ''),
        channel: String(e.channel ?? ''), body: String(e.body ?? ''), mode: String(e.mode ?? ''), status: String(e.status ?? ''),
        caseId: optStr(e.case_id), provider: optStr(e.provider), callId: optStr(e.call_id),
      });
    }
  }
);

export const upsertCase = spacetimedb.reducer(
  { id: t.string(), driverId: t.string(), state: t.string(), bodyJson: t.string() },
  (ctx, a) => {
    requireOwner(ctx);
    const row = { id: str(a.id, 'id'), driverId: a.driverId, state: a.state, bodyJson: a.bodyJson, updatedAt: ctx.timestamp };
    if (ctx.db.escalationCase.id.find(a.id)) ctx.db.escalationCase.id.update(row); else ctx.db.escalationCase.insert(row);
  }
);

export const addSnapshot = spacetimedb.reducer(
  { id: t.string(), pointId: t.string(), droneId: t.string(), time: t.string(), bodyJson: t.string() },
  (ctx, a) => {
    requireOwner(ctx);
    const row = { id: str(a.id, 'id'), pointId: a.pointId, droneId: a.droneId, time: a.time, bodyJson: a.bodyJson };
    if (ctx.db.visionSnapshot.id.find(a.id)) ctx.db.visionSnapshot.id.update(row); else ctx.db.visionSnapshot.insert(row);
  }
);

export const kvSet = spacetimedb.reducer(
  { key: t.string(), value: t.string() },
  (ctx, { key, value }) => {
    requireOwner(ctx);
    const row = { key: str(key, 'key'), value, updatedAt: ctx.timestamp };
    if (ctx.db.kv.key.find(key)) ctx.db.kv.key.update(row); else ctx.db.kv.insert(row);
  }
);

// Clear runtime state (scenario reset, tests). scope: "safety" | "cases" | "outreach" | "all_runtime".
// Evidence and people are never wiped here.
export const wipeRuntime = spacetimedb.reducer(
  { scope: t.string() },
  (ctx, { scope }) => {
    requireOwner(ctx);
    const all = scope === 'all_runtime';
    if (all || scope === 'safety') {
      for (const r of [...ctx.db.userTrack.iter()]) ctx.db.userTrack.userId.delete(r.userId);
      for (const r of [...ctx.db.responseState.iter()]) ctx.db.responseState.userId.delete(r.userId);
      for (const r of [...ctx.db.dangerLatest.iter()]) ctx.db.dangerLatest.userId.delete(r.userId);
    }
    if (all || scope === 'cases') {
      for (const r of [...ctx.db.escalationCase.iter()]) ctx.db.escalationCase.id.delete(r.id);
    }
    if (all || scope === 'outreach') {
      for (const r of [...ctx.db.outreachEvent.iter()]) ctx.db.outreachEvent.id.delete(r.id);
    }
    if (!all && !['safety', 'cases', 'outreach'].includes(scope)) throw new SenderError(`unknown scope ${scope}`);
  }
);
