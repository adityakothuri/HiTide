// Scoutroom fleet manager: clone jobs, runner lifecycle, discovery and live stats.
// Every clone is its own registered team + bot + credential + OS process. The fleet
// is capped (FLEET_CAP, default 5, counting every runner on this machine); bots are
// improved in place (same bot id, so the rating carries over) rather than multiplied.
import { readFileSync, writeFileSync, renameSync, existsSync, openSync, closeSync, mkdirSync, statSync, readSync, copyFileSync } from 'node:fs';
import { basename } from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { randomUUID, createHash } from 'node:crypto';
import { dirname } from 'node:path';
import { copyName, registerCopy } from './copy-bot.mjs';
import { DbConnection } from '../../src/module_bindings/index.js';
import { sql } from './sql.mjs';

export const CWD = new URL('../../', import.meta.url).pathname;
export const DATA = CWD + 'bench/results/scouting/';
const MODELS = DATA + 'models/';
const HEARTBEAT_MS = 12000;
const RUNNER = /node .*--import tsx src\/index\.ts$/;
const RATING_SCALE = 400 / (25 / 6 * Math.LN10 * Math.SQRT2);
export const FLEET_CAP = Number(process.env.FLEET_CAP ?? 5);
const WATCHDOG_WINDOW_MS = 10 * 60 * 1000, WATCHDOG_MAX_RESTARTS = 3;
const FIDELITY_TOLERANCE = 0.02; // an auto-update may not lose more outcome agreement than this
mkdirSync(MODELS, { recursive: true });

export type CopyState = 'queued' | 'fitting' | 'registering' | 'starting' | 'running' | 'draining' | 'stopped' | 'exited' | 'failed';
export interface CopyRecord {
  copyId: string; name: string; kind: 'clone-v2' | 'legacy-median' | 'strategy'; sourceBotId: number; sourceName: string; createdAt: string;
  state: CopyState; botId: string | null; pid: number; error: string | null; archived?: boolean;
  folder: string; runtimePath: string; logPath: string; resultsPath: string; controlPath: string;
  modelPath?: string; configPath?: string; baseStrategy?: string; fidelity?: Record<string, number | null>;
  startedAt?: string; stoppedAt?: string; restarts?: number;
  // Roster upkeep
  bidDelayMs?: number;
  relaunchAfterDrain?: boolean; deleteAfterDrain?: boolean; renameTo?: string | null; renameRelaunch?: boolean; formerNames?: { name: string; botId: string | null; until: string }[]; deletedAt?: string; crashTimes?: number[]; rebraining?: string | null;
  modelKey?: string; modelVersion?: number; modelUpdatedAt?: string; modelFittedAt?: string;
}

const readJson = (file: string, fallback: any = null) => { try { return JSON.parse(readFileSync(file, 'utf8')); } catch { return fallback; } };
function writeJson(file: string, value: unknown) { writeFileSync(file + '.tmp', JSON.stringify(value, null, 2) + '\n'); renameSync(file + '.tmp', file); }
const errorText = (e: unknown) => e instanceof Error ? e.message : String(e);

/** Load the registry, upgrading pre-v2 copies (median profile + LexForge base) in place. */
function loadRegistry(): CopyRecord[] {
  return (readJson(DATA + 'copies.json', []) as any[]).map(c => {
    const folder = c.folder ?? dirname(c.configPath ?? c.runtimePath) + '/';
    return { kind: 'legacy-median', resultsPath: folder + 'results.jsonl', controlPath: folder + 'control.json', logPath: folder + 'bot.log', ...c, folder };
  });
}
export const copies: CopyRecord[] = loadRegistry();
const save = () => writeJson(DATA + 'copies.json', copies);

// ---------- process discovery ----------
interface Proc { pid: number; env: string; elapsed: string }
let procs = new Map<number, Proc>();
function scanProcesses() {
  try {
    const out = execFileSync('ps', ['eww', '-Ao', 'pid=,etime=,command='], { encoding: 'utf8', maxBuffer: 32 << 20 });
    const next = new Map<number, Proc>();
    for (const line of out.split('\n')) {
      const m = line.match(/^\s*(\d+)\s+(\S+)\s+(.*)$/);
      if (!m || !/--import tsx src\/index\.ts/.test(m[3]!)) continue;
      next.set(Number(m[1]), { pid: Number(m[1]), elapsed: m[2]!, env: m[3]! });
    }
    procs = next;
  } catch { /* keep the previous scan */ }
}
const envOf = (p: Proc, key: string) => [...p.env.matchAll(new RegExp(`(?:^|\\s)${key}=(\\S+)`, 'g'))].map(m => m[1]!);
/** A pid belongs to a copy only if it is a bot runner launched with that copy's name. */
const ownsPid = (c: CopyRecord) => { const p = procs.get(c.pid); return !!p && envOf(p, 'BOT_NAME').includes(c.name); };
const heartbeat = (file: string, pid: number) => { const r = readJson(file); return r && r.pid === pid && Date.now() - Date.parse(r.heartbeatAt) < HEARTBEAT_MS ? r : null; };

// ---------- live leaderboard ----------
interface BotStatRow { id: string; rating: number; uncertainty: number; matches: number; wins: number; elo: number; totalScore: number; lastPlayed: string | null; rank: number | null }
let ratings = new Map<string, BotStatRow>();
let botNames = new Map<string, string>();
let ratingsAt: string | null = null;
const TEAM_PREFIX = process.env.TEAM_PREFIX ?? 'Pegasus';
export async function refreshRatings() {
  try {
    const [stats, bots] = await Promise.all([sql('SELECT * FROM bot_stats'), sql('SELECT * FROM bot')]);
    botNames = new Map(bots.map(b => [String(b.id), String(b.name)]));
    const rows = stats.map(s => {
      const last = s.last_played as [number, [number]] | undefined;
      return { id: String(s.bot_id), rating: Math.round(1500 + RATING_SCALE * (Number(s.openskill_mu) - 25)), uncertainty: Math.round(RATING_SCALE * Number(s.openskill_sigma)), matches: Number(s.matches_played), wins: Number(s.wins),
        elo: Math.round(Number(s.rating)), totalScore: Number(s.total_score), lastPlayed: last?.[0] === 0 ? new Date(Number(last[1][0]) / 1000).toISOString() : null };
    });
    const ranked = rows.filter(r => r.uncertainty <= 175).sort((a, b) => b.rating - a.rating);
    ratings = new Map(rows.map(r => [r.id, { ...r, rank: r.uncertainty <= 175 ? 1 + ranked.filter(o => o.rating > r.rating).length : null }]));
    ratingsAt = new Date().toISOString();
  } catch { /* stale ratings are still useful */ }
}

// ---------- lobby / upcoming match ----------
export interface LobbyInfo { lobbyId: string; status: 'open' | 'resolved' | 'cancelled'; members: number; maxSize: number; closesAt: string; matchId: string | null }
let lobbies = new Map<string, LobbyInfo>();
let lobbyWatermark = 0;
const LOBBY_STATUS = ['open', 'resolved', 'cancelled'] as const;
const micros = (t: unknown) => Number((t as number[])[0]) / 1000;
/** Each bot's most recent lobby: who else joined, when it closes, and the match it became. */
export async function refreshLobbies(botIds: string[]) {
  const ids = [...new Set(botIds.filter(id => /^\d+$/.test(id)))];
  if (!ids.length) return;
  try {
    const rows = await sql(`SELECT * FROM lobby_member WHERE lobby_id >= ${lobbyWatermark} AND (${ids.map(id => `bot_id = ${id}`).join(' OR ')})`);
    const latest = new Map<string, number>();
    for (const r of rows) { const bot = String(r.bot_id), lobby = Number(r.lobby_id); if (lobby > (latest.get(bot) ?? -1)) latest.set(bot, lobby); }
    if (!latest.size) return;
    const wanted = [...new Set(latest.values())];
    const [states, members] = await Promise.all([
      sql(`SELECT * FROM lobby WHERE ${wanted.map(id => `id = ${id}`).join(' OR ')}`),
      sql(`SELECT * FROM lobby_member WHERE ${wanted.map(id => `lobby_id = ${id}`).join(' OR ')}`),
    ]);
    const info = new Map(states.map(l => {
      const resolved = l.resolved_match_id as [number, unknown];
      return [Number(l.id), { lobbyId: String(l.id), status: LOBBY_STATUS[(l.status as [number])[0]] ?? 'open', members: members.filter(m => Number(m.lobby_id) === Number(l.id)).length,
        maxSize: Number(l.max_size), closesAt: new Date(micros(l.closes_at)).toISOString(), matchId: resolved?.[0] === 0 ? String(resolved[1]) : null } as LobbyInfo];
    }));
    lobbies = new Map([...latest].flatMap(([bot, lobby]) => info.has(lobby) ? [[bot, info.get(lobby)!]] : []));
    // Older lobby rows can never become a bot's latest again; skip them next time.
    lobbyWatermark = Math.max(0, Math.min(...latest.values()) - 50);
  } catch { /* keep the last view */ }
}
/** Match number now (from the runner) or next (from the lobby). */
function matchInfo(hb: any, botId: string | null, lastMatchId: string | null) {
  const current = hb?.match?.matchId ?? hb?.runningMatches?.[0] ?? null;
  if (current) return { currentMatchId: String(current), lobby: null, lastMatchId };
  // Lobby data polls a few seconds behind the runner: only trust a lobby that is still
  // open, or one that resolved into a match newer than anything this bot has finished.
  const lobby = botId ? lobbies.get(String(botId)) ?? null : null;
  const fresh = lobby && (lobby.status === 'open' || (lobby.status === 'resolved' && Number(lobby.matchId) > Number(lastMatchId ?? hb?.lastMatchId ?? 0)));
  return { currentMatchId: null, lobby: fresh ? lobby : null, lastMatchId, lobbyWait: hb?.lobbyWait ?? null };
}
export function fleetBotIds(): string[] {
  const managed = copies.filter(c => !c.archived && c.botId && isLive(c)).map(c => String(c.botId));
  const external = [...procs.values()].map(p => heartbeat(envOf(p, 'SCOUT_RUNTIME_PATH').at(-1) ?? DATA + 'runtime.json', p.pid)?.botId ?? envOf(p, 'SCOUT_BOT_ID').at(-1)).filter(Boolean).map(String);
  return [...managed, ...external];
}

function results(c: CopyRecord) {
  let rows: any[] = [];
  try { rows = readFileSync(c.resultsPath, 'utf8').trim().split('\n').filter(Boolean).map(l => JSON.parse(l)); } catch { /* none yet */ }
  const mean = (xs: number[]) => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  return { lastMatchId: rows.at(-1)?.matchId ?? null, matches: rows.length, wins: rows.filter(r => r.won && !r.tiedFirst).length, meanPlace: mean(rows.map(r => r.place)), meanScore: mean(rows.map(r => r.score)), recentPlaces: rows.slice(-12).map(r => r.place) };
}

// ---------- lifecycle ----------
/** Observe processes and settle any state the processes have moved past. */
export function reconcile() {
  scanProcesses();
  let changed = false;
  for (const c of copies) {
    // A deletion interrupted by a dashboard restart resumes here.
    if (c.deleteAfterDrain && !c.archived && !['running', 'draining', 'starting'].includes(c.state)) { void finishDelete(c); continue; }
    if (c.renameTo && !c.archived && !['running', 'draining', 'starting'].includes(c.state)) { void finishRename(c); continue; }
    if (!['running', 'draining', 'starting'].includes(c.state)) continue;
    if (c.pid && ownsPid(c)) {
      if (c.state === 'starting') { c.state = 'running'; changed = true; }
      // Runners started before drain support: the manager waits for the match to end, then stops them.
      const hb = c.state === 'draining' ? heartbeat(c.runtimePath, c.pid) : null;
      if (hb && !hb.supportsDrain && !(hb.runningMatches?.length > 0)) { try { process.kill(c.pid, 'SIGTERM'); } catch { /* already gone */ } }
      continue;
    }
    if (c.state === 'starting' && c.startedAt && Date.now() - Date.parse(c.startedAt) < 5000) continue;
    changed = true;
    c.stoppedAt = new Date().toISOString();
    try {
      if (c.state === 'draining' && c.relaunchAfterDrain) { c.relaunchAfterDrain = false; launch(c); continue; }
      if (c.state === 'draining' && c.deleteAfterDrain) { c.state = 'stopped'; void finishDelete(c); continue; }
      if (c.state === 'draining' && c.renameTo) { c.state = 'stopped'; void finishRename(c); continue; }
      if (c.state === 'draining') { c.state = 'stopped'; continue; }
      // Unexpected exit: restart unless it keeps crashing.
      c.error = lastLogLine(c) ?? 'Runner exited';
      c.crashTimes = (c.crashTimes ?? []).filter(t => Date.now() - t < WATCHDOG_WINDOW_MS);
      if (c.crashTimes.length < WATCHDOG_MAX_RESTARTS) {
        c.crashTimes.push(Date.now()); launch(c);
        c.error = `Auto-restarted after exit (${c.crashTimes.length}/${WATCHDOG_MAX_RESTARTS} in 10 min)`;
      } else c.state = 'exited';
    } catch (e) { c.state = 'failed'; c.error = errorText(e); }
  }
  if (changed) save();
}

function lastLogLine(c: CopyRecord): string | null {
  const lines = tail(c.logPath, 4000).trim().split('\n').filter(l => /error|exit|fail/i.test(l));
  return lines.at(-1)?.slice(0, 200) ?? null;
}

export function tail(file: string, bytes = 16000): string {
  try {
    const size = statSync(file).size, start = Math.max(0, size - bytes), fd = openSync(file, 'r');
    const buf = Buffer.alloc(size - start); readSync(fd, buf, 0, buf.length, start); closeSync(fd);
    const text = buf.toString('utf8');
    return start ? text.slice(text.indexOf('\n') + 1) : text;
  } catch { return ''; }
}

/** The runner's control file: drain flag plus the bot's configured bid delay. */
function writeControl(c: CopyRecord, drain: boolean) { writeJson(c.controlPath, { drain, bidDelayMs: c.bidDelayMs ?? 0 }); }

export function setBidDelay(copyId: string, ms: number): string {
  if (!Number.isInteger(ms) || ms < 0 || ms > 900) throw Error('Bid delay must be 0-900 ms.');
  const c = find(copyId);
  c.bidDelayMs = ms;
  if (existsSync(c.controlPath)) writeControl(c, c.state === 'draining');
  save();
  return ms ? `${c.name} now waits ${ms} ms before each bid (auctions close after 1000 ms).` : `${c.name} bids immediately again.`;
}

// Scoutroom nicknames. The server has no way to rename a bot; these are display-only.
const ALIASES = DATA + 'aliases.json';
let aliases: Record<string, string> = readJson(ALIASES, {});
export function setAlias(botId: string, alias: string): string {
  if (!/^\d+$/.test(botId)) throw Error('Unknown bot.');
  const clean = alias.trim().replace(/\s+/g, ' ');
  if (clean.length > 40) throw Error('Keep nicknames to 40 characters.');
  aliases = { ...aliases };
  if (clean) aliases[botId] = clean; else delete aliases[botId];
  writeJson(ALIASES, aliases);
  return clean ? `Nickname set to "${clean}" in Scoutroom. The leaderboard name is unchanged.` : 'Nickname cleared.';
}
const aliasOf = (botId: string | null) => (botId && aliases[String(botId)]) || null;

function launch(c: CopyRecord) {
  if (!existsSync(CWD + '.token-' + c.name)) throw Error(`${c.name} has no saved credential; it cannot be restarted.`);
  writeControl(c, false);
  const env: NodeJS.ProcessEnv = { ...process.env, BOT_NAME: c.name, SCOUT_RUNTIME_PATH: c.runtimePath, RESULTS_PATH: c.resultsPath, CONTROL_PATH: c.controlPath };
  delete env.BOT_TOKEN; delete env.BOT_NONCE; delete env.TOURNAMENT_ID; delete env.CLONE_MODEL_PATH;
  if (c.kind === 'clone-v2') { env.CLONE_MODEL_PATH = c.modelPath; env.SCOUT_CONFIG_PATH = c.folder + 'no-scouting.json'; }
  else { env.STRATEGY = c.baseStrategy ?? 'lexforge'; env.SCOUT_CONFIG_PATH = c.kind === 'strategy' ? c.folder + 'no-scouting.json' : c.configPath; }
  const fd = openSync(c.logPath, 'a');
  const child = spawn(process.execPath, ['--import', 'tsx', 'src/index.ts'], { cwd: CWD, env, detached: true, stdio: ['ignore', fd, fd] });
  closeSync(fd); child.unref();
  child.on('error', e => { c.state = 'failed'; c.error = e.message; save(); });
  c.pid = child.pid ?? 0; c.state = 'starting'; c.error = null; c.startedAt = new Date().toISOString(); c.stoppedAt = undefined;
  save();
}

function terminate(c: CopyRecord) {
  scanProcesses();
  if (!c.pid || !procs.has(c.pid)) return;
  if (!ownsPid(c)) throw Error(`Process ${c.pid} is no longer ${c.name}; refused to signal it.`);
  process.kill(c.pid, 'SIGTERM');
}

/** Slots in use: live or launching managed bots, queued clones, and runners Scoutroom did not launch. */
export function occupancy(): number {
  const managedPids = new Set(copies.filter(c => isLive(c)).map(c => c.pid));
  const creating = copies.filter(c => !c.archived && ['queued', 'fitting', 'registering'].includes(c.state)).length;
  return managedPids.size + creating + [...procs.keys()].filter(pid => !managedPids.has(pid)).length;
}
function assertCapacity(extra: number) {
  scanProcesses();
  const used = occupancy();
  if (used + extra > FLEET_CAP) throw Error(`Fleet is capped at ${FLEET_CAP} bots (${used} in use). Drain or stop one first, or rebrain an existing bot instead.`);
}

const find = (copyId: string) => { const c = copies.find(x => x.copyId === copyId && !x.archived); if (!c) throw Error('Unknown bot'); return c; };
const isLive = (c: CopyRecord) => ['running', 'draining', 'starting'].includes(c.state) && ownsPid(c);

export function stop(copyId: string, mode: 'now' | 'drain'): string {
  const c = find(copyId);
  if (!isLive(c)) { if (['running', 'starting'].includes(c.state)) { c.state = 'stopped'; save(); } return `${c.name} is not running.`; }
  c.relaunchAfterDrain = false;
  if (mode === 'drain') {
    writeControl(c, true); c.state = 'draining'; save();
    return `${c.name} will finish its current match, then stop.`;
  }
  terminate(c); c.state = 'stopped'; c.stoppedAt = new Date().toISOString(); save();
  return `Stopped ${c.name}.`;
}

export function start(copyId: string): string {
  const c = find(copyId);
  if (isLive(c)) {
    if (c.state === 'draining') { writeControl(c, false); c.state = 'running'; save(); return `${c.name} will keep playing.`; }
    return `${c.name} is already running.`;
  }
  if (['queued', 'fitting', 'registering'].includes(c.state)) throw Error(`${c.name} is still being created.`);
  assertCapacity(1);
  c.restarts = (c.restarts ?? 0) + 1; c.crashTimes = []; launch(c);
  return `Started ${c.name}.`;
}

export function archive(copyId: string): string {
  const c = find(copyId);
  if (isLive(c)) throw Error(`Stop ${c.name} before removing it.`);
  if (['queued', 'fitting', 'registering'].includes(c.state)) throw Error(`${c.name} is still being created.`);
  c.archived = true; save();
  return `Removed ${c.name} from the fleet list. Its credential and files are kept.`;
}

export function bulk(action: 'stop' | 'drain' | 'start' | 'delete', copyIds?: string[]): string {
  const targets = copies.filter(c => !c.archived && (!copyIds || copyIds.includes(c.copyId)));
  const done: string[] = [], failed: string[] = [];
  for (const c of targets) {
    try {
      if (action === 'delete') { if (copyIds) { deleteBot(c.copyId); done.push(c.name); } continue; }
      if (action === 'start') { if (!isLive(c) && ['stopped', 'exited', 'failed'].includes(c.state) && c.botId) { start(c.copyId); done.push(c.name); } }
      else if (isLive(c) && !(action === 'drain' && c.state === 'draining')) { stop(c.copyId, action === 'drain' ? 'drain' : 'now'); done.push(c.name); }
    } catch (e) { failed.push(`${c.name}: ${errorText(e)}`); }
  }
  const verb = action === 'start' ? 'Started' : action === 'drain' ? 'Draining' : action === 'delete' ? 'Deleting' : 'Stopped';
  return `${verb} ${done.length} bot${done.length === 1 ? '' : 's'}.${failed.length ? ' Failed: ' + failed.join('; ') : ''}`;
}

// ---------- permanent deletion ----------
/**
 * Delete a bot from the server for good: its saved identity is the team's only member,
 * and the last member leaving dissolves the team and deletes its bot and credentials.
 * A running bot is drained first so no live match is left with a dead seat.
 */
export function deleteBot(copyId: string): string {
  const c = find(copyId);
  if (!c.botId) { c.archived = true; save(); return `Removed ${c.name} (it was never registered).`; }
  if (isLive(c)) {
    writeControl(c, true);
    Object.assign(c, { state: 'draining', deleteAfterDrain: true, relaunchAfterDrain: false }); save();
    return `${c.name} will be deleted after its current match.`;
  }
  void finishDelete(c);
  return `Deleting ${c.name}.`;
}
// ---------- leaderboard rename ----------
/**
 * The server cannot rename a bot: its name is fixed at registration. A leaderboard rename
 * therefore registers a NEW team + bot under the new name, then deletes the old one.
 * The new bot starts with a fresh rating. Registration happens first, so a failure
 * leaves the old bot untouched.
 */
const NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 ._-]{1,38}[A-Za-z0-9]$/;
export async function renameOnServer(copyId: string, newName: string): Promise<string> {
  const c = find(copyId), name = newName.trim();
  if (!c.botId || ['queued', 'fitting', 'registering'].includes(c.state)) throw Error(`${c.name} is still being created.`);
  if (c.renameTo || c.deleteAfterDrain) throw Error(`${c.name} already has a pending change.`);
  if (!NAME_PATTERN.test(name)) throw Error('Names are 3-40 characters: letters, numbers, spaces, dot, dash or underscore.');
  if (name === c.name) throw Error('That is already its name.');
  const [bots, teams] = await Promise.all([sql('SELECT * FROM bot'), sql('SELECT * FROM team')]);
  const taken = new Set([...bots.map(b => String(b.name).toLowerCase()), ...teams.map(t => String(t.name).toLowerCase()), ...copies.filter(x => x !== c && !x.archived).map(x => x.name.toLowerCase())]);
  if (taken.has(name.toLowerCase())) throw Error(`"${name}" is already taken on the leaderboard.`);
  if (existsSync(CWD + '.token-' + name)) throw Error(`A saved login for "${name}" already exists here; pick another name.`);
  c.renameTo = name;
  if (isLive(c)) {
    writeControl(c, true);
    Object.assign(c, { state: 'draining', renameRelaunch: true, relaunchAfterDrain: false }); save();
    return `${c.name} becomes "${name}" after its current match. The new bot starts with a fresh Elo.`;
  }
  c.renameRelaunch = false; save();
  void finishRename(c);
  return `Registering "${name}" and retiring ${c.name}. The new bot starts with a fresh Elo.`;
}
const renaming = new Set<string>();
async function finishRename(c: CopyRecord) {
  if (renaming.has(c.copyId) || !c.renameTo) return;
  renaming.add(c.copyId);
  const oldName = c.name, oldBotId = c.botId, newName = c.renameTo;
  try {
    const botId = await registerCopy(newName, CWD + '.token-' + newName);
    try { await leaveTeamAs(CWD + '.token-' + oldName); }
    catch (e) { c.error = `Registered "${newName}", but deleting old ${oldName} failed: ${errorText(e)}. Delete it from the Stats tab.`; }
    c.formerNames = [...(c.formerNames ?? []), { name: oldName, botId: oldBotId, until: new Date().toISOString() }];
    Object.assign(c, { name: newName, botId, renameTo: null });
    if (oldBotId && aliases[oldBotId]) setAlias(oldBotId, '');
    if (c.renameRelaunch) { c.renameRelaunch = false; launch(c); }
  } catch (e) {
    // Registration failed: the old bot is untouched. Resume it if it was running.
    Object.assign(c, { renameTo: null, error: `Rename failed, kept ${oldName}: ${errorText(e)}` });
    if (c.renameRelaunch) { c.renameRelaunch = false; try { launch(c); } catch { /* reported by state */ } }
  } finally { renaming.delete(c.copyId); save(); }
}

const deleting = new Set<string>();
async function finishDelete(c: CopyRecord) {
  if (deleting.has(c.copyId)) return;
  deleting.add(c.copyId);
  try {
    await leaveTeamAs(CWD + '.token-' + c.name);
    Object.assign(c, { archived: true, deleteAfterDrain: false, deletedAt: new Date().toISOString(), error: null });
  } catch (e) { c.error = `Delete failed: ${errorText(e)}`; c.deleteAfterDrain = false; }
  finally { deleting.delete(c.copyId); save(); }
}
function leaveTeamAs(tokenFile: string): Promise<void> {
  const token = readFileSync(tokenFile, 'utf8').trim();
  return new Promise((resolve, reject) => {
    let conn: DbConnection | null = null;
    const done = (e?: Error) => { clearTimeout(timer); conn?.disconnect(); e ? reject(e) : resolve(); };
    const timer = setTimeout(() => done(Error('Timed out talking to the server')), 20000);
    DbConnection.builder().withUri(process.env.STDB_HOST ?? 'https://maincloud.spacetimedb.com').withDatabaseName(process.env.STDB_DB ?? 'scrabblebot').withToken(token)
      .onConnect(c => { conn = c; c.reducers.leaveTeam({}).then(() => done(), e => done(e instanceof Error ? e : Error(String(e)))); })
      .onConnectError((_ctx, e) => done(Error(`Connection failed: ${e.message}`))).build();
  });
}

/** Stop a bot runner the dashboard did not launch (e.g. original Pegasus). */
export function stopExternal(pid: number): string {
  scanProcesses();
  const p = procs.get(pid);
  if (!p || copies.some(c => c.pid === pid && ownsPid(c))) throw Error('Not an unmanaged bot runner.');
  const command = execFileSync('ps', ['-p', String(pid), '-o', 'command='], { encoding: 'utf8' }).trim();
  if (!RUNNER.test(command)) throw Error('Process changed; refused to stop it.');
  process.kill(pid, 'SIGTERM');
  return `Stopped ${envOf(p, 'BOT_NAME').at(-1) ?? 'bot'} (pid ${pid}).`;
}

// ---------- clone jobs ----------
const jobs: string[] = [];
let working = false;
let fitChain: Promise<unknown> = Promise.resolve();
const fitsInFlight = new Map<string, Promise<string>>();

/** Fits run one at a time (each is CPU-heavy) and are cached by the exact source match set. */
function fitModel(profile: { botId: number; matchIds: number[] }): Promise<string> {
  const key = `${profile.botId}-${createHash('sha1').update(profile.matchIds.join(',')).digest('hex').slice(0, 12)}`;
  const path = `${MODELS}${key}.json`;
  if (existsSync(path)) return Promise.resolve(path);
  const pending = fitsInFlight.get(key);
  if (pending) return pending;
  const job = fitChain.then(() => existsSync(path) ? path : runFit(profile.botId, path)).finally(() => fitsInFlight.delete(key));
  fitChain = job.catch(() => undefined);
  fitsInFlight.set(key, job);
  return job;
}

function runFit(botId: number, path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ['--import', 'tsx', 'bench/live/clone-engine.mts', '--bot', String(botId), '--out', path], { cwd: CWD, stdio: ['ignore', 'ignore', 'pipe'] });
    let err = '';
    child.stderr.on('data', d => { err += d; });
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve(path) : reject(Error(err.trim().split('\n').at(-1) || `Clone fit failed (${code})`)));
  });
}

async function runJob(c: CopyRecord) {
  const snapshot = readJson(DATA + 'profiles.json');
  const profile = snapshot?.profiles?.find((p: any) => p.botId === c.sourceBotId);
  if (!profile) throw Error(`${c.sourceName} is no longer in the scouting snapshot.`);
  c.state = 'fitting'; save();
  const shared = await fitModel(profile);
  const model = readJson(shared);
  writeFileSync(c.modelPath!, JSON.stringify(model, null, 2) + '\n', { flag: 'wx' });
  c.fidelity = model.validation; c.modelKey = basename(shared, '.json'); c.modelVersion = 1; c.modelUpdatedAt = new Date().toISOString(); c.modelFittedAt = model.fittedAt;
  c.state = 'registering'; save();
  const [bots, teams] = await Promise.all([sql('SELECT * FROM bot'), sql('SELECT * FROM team')]);
  c.name = copyName([...bots.map(b => String(b.name)), ...teams.map(t => String(t.name)), ...copies.filter(x => x !== c).map(x => x.name)]);
  save();
  c.botId = await registerCopy(c.name, CWD + '.token-' + c.name);
  save();
  launch(c);
}

async function work() {
  if (working) return;
  working = true;
  try {
    while (jobs.length) {
      const c = copies.find(x => x.copyId === jobs[0]);
      jobs.shift();
      if (!c || c.state !== 'queued') continue;
      try { await runJob(c); }
      catch (e) { c.state = 'failed'; c.error = errorText(e); save(); }
    }
  } finally { working = false; }
}

/** Queue one clone per requested source bot (repeats allowed: each is a separate bot). */
export function queueClones(sources: { botId: number; name: string }[]): CopyRecord[] {
  assertCapacity(sources.length);
  const created = sources.map(s => {
    const copyId = randomUUID(), folder = `${DATA}copies/${copyId}/`;
    mkdirSync(folder, { recursive: true });
    const c: CopyRecord = {
      copyId, name: `pending-${copyId.slice(0, 6)}`, kind: 'clone-v2', sourceBotId: s.botId, sourceName: s.name, createdAt: new Date().toISOString(),
      state: 'queued', botId: null, pid: 0, error: null, folder, modelPath: folder + 'model.json', runtimePath: folder + 'runtime.json',
      logPath: folder + 'bot.log', resultsPath: folder + 'results.jsonl', controlPath: folder + 'control.json',
    };
    copies.push(c); jobs.push(copyId); return c;
  });
  save(); void work();
  return created;
}

/** Fit (or reuse) a model for preview without registering anything. */
export async function previewModel(botId: number) {
  const snapshot = readJson(DATA + 'profiles.json');
  const profile = snapshot?.profiles?.find((p: any) => p.botId === botId);
  if (!profile) throw Error('Pick a bot from the current snapshot.');
  return readJson(await fitModel(profile));
}

// Interrupted jobs (dashboard restarted mid-creation) resume where possible.
for (const c of copies) {
  if (c.state === 'queued' || c.state === 'fitting') { c.state = 'queued'; jobs.push(c.copyId); }
  else if (c.state === 'registering') { c.state = 'failed'; c.error = 'Dashboard restarted during registration. Its saved identity is kept.'; }
}
if (jobs.length) { save(); void work(); }

// ---------- roster upkeep: improve bots in place ----------
/**
 * Give an existing bot a freshly fitted model, optionally from a different source bot.
 * The bot keeps its id, so its leaderboard rating carries over (no new version is started).
 * v2 runners hot-reload the model between matches; older runners are drained and relaunched.
 */
export async function rebrain(copyId: string, sourceBotId: number, opts: { auto?: boolean } = {}): Promise<string> {
  const c = find(copyId);
  if (!c.botId || ['queued', 'fitting', 'registering'].includes(c.state)) throw Error(`${c.name} is still being created.`);
  if (c.rebraining) throw Error(`${c.name} is already being retrained.`);
  if (sourceBotId === OWN_STRATEGY_ID) return useOwnStrategy(c);
  const profile = readJson(DATA + 'profiles.json')?.profiles?.find((p: any) => p.botId === sourceBotId);
  if (!profile) throw Error('That source bot is not in the current scouting snapshot.');
  c.rebraining = profile.name; save();
  try {
    const shared = await fitModel(profile), key = basename(shared, '.json'), model = readJson(shared);
    if (opts.auto) {
      if (key === c.modelKey) return `${c.name}: no new matches from ${profile.name}; model unchanged.`;
      const before = c.fidelity?.outcomeAgreement, after = model.validation.outcomeAgreement;
      if (before != null && after != null && after < before - FIDELITY_TOLERANCE) return `${c.name}: refit scored ${Math.round(after * 100)}% vs ${Math.round(before * 100)}%; kept the current model.`;
    }
    const target = c.folder + 'model.json';
    if (existsSync(target)) copyFileSync(target, `${c.folder}model-v${c.modelVersion ?? 1}.json`);
    writeFileSync(target + '.tmp', JSON.stringify(model, null, 2) + '\n'); renameSync(target + '.tmp', target);
    const wasLegacy = c.kind !== 'clone-v2';
    Object.assign(c, { kind: 'clone-v2', modelPath: target, modelKey: key, modelVersion: (c.modelVersion ?? (wasLegacy ? 0 : 1)) + 1, modelUpdatedAt: new Date().toISOString(),
      modelFittedAt: model.fittedAt, fidelity: model.validation, sourceBotId: profile.botId, sourceName: profile.name });
    const hb = isLive(c) ? heartbeat(c.runtimePath, c.pid) : null;
    // A runner that cannot hot-reload (legacy strategy, or pre-reload code) switches over after its match.
    if (isLive(c) && (wasLegacy || !hb?.supportsDrain)) {
      writeControl(c, true);
      Object.assign(c, { state: 'draining', relaunchAfterDrain: true });
      return `${c.name} now imitates ${profile.name} (model v${c.modelVersion}); it switches over after its current match.`;
    }
    return `${c.name} now imitates ${profile.name} (model v${c.modelVersion}); ${isLive(c) ? 'it loads the model before its next match' : 'start it to play'}.`;
  } finally { c.rebraining = null; save(); }
}

/** Source id 0 = our own LexForge strategy (no imitation). Needs a relaunch: the runner's strategy is fixed at start. */
export const OWN_STRATEGY_ID = 0;
function useOwnStrategy(c: CopyRecord): string {
  Object.assign(c, { kind: 'strategy', baseStrategy: 'lexforge', sourceBotId: OWN_STRATEGY_ID, sourceName: 'Pegasus LexForge', fidelity: undefined, modelKey: undefined, modelFittedAt: undefined });
  if (isLive(c)) { writeControl(c, true); Object.assign(c, { state: 'draining', relaunchAfterDrain: true }); }
  save();
  return `${c.name} switches to our LexForge strategy ${isLive(c) ? 'after its current match' : 'when started'}; its rating carries over.`;
}

/** Bots drained only to pick up new runner code: same model, same bot id. */
export function relaunchAfterMatch(copyId: string): string {
  const c = find(copyId);
  if (!isLive(c)) throw Error(`${c.name} is not running.`);
  writeControl(c, true);
  Object.assign(c, { state: 'draining', relaunchAfterDrain: true }); save();
  return `${c.name} will restart on the latest code after its current match.`;
}

export const upkeep = { lastRunAt: null as string | null, nextRunAt: null as string | null, running: false, log: [] as string[] };
/** Refit every live clone on its source's newest matches; keep a refit only if fidelity holds. */
export async function autoUpdate(intervalMs: number) {
  if (upkeep.running) return;
  upkeep.running = true;
  const log: string[] = [];
  try {
    for (const c of copies.filter(x => !x.archived && x.kind === 'clone-v2' && isLive(x) && !x.rebraining)) {
      try { log.push(await rebrain(c.copyId, c.sourceBotId, { auto: true })); } catch (e) { log.push(`${c.name}: ${errorText(e)}`); }
    }
  } finally {
    Object.assign(upkeep, { running: false, lastRunAt: new Date().toISOString(), nextRunAt: new Date(Date.now() + intervalMs).toISOString(), log });
  }
}

// ---------- team statistics ----------
/** Every one of our bots on the server (by name prefix), with leaderboard stats and where it runs. */
export function teamStats() {
  const managedLive = new Map(copies.filter(c => isLive(c) && c.botId).map(c => [String(c.botId), c]));
  const externalLive = new Set(fleetBotIds().filter(id => !managedLive.has(id)));
  const recentMs = 5 * 60 * 1000;
  return [...botNames].filter(([, name]) => name.startsWith(TEAM_PREFIX)).map(([id, name]) => {
    const s = ratings.get(id), c = managedLive.get(id);
    // Deletable only if Scoutroom holds the team's sole-member identity (bots it registered).
    const owned = copies.find(x => !x.archived && String(x.botId) === id && existsSync(CWD + '.token-' + x.name));
    const where = c ? (c.state === 'draining' ? (c.deleteAfterDrain ? 'deleting' : 'draining') : 'running here') : externalLive.has(id) ? 'running here' : s?.lastPlayed && Date.now() - Date.parse(s.lastPlayed) < recentMs ? 'active elsewhere' : 'idle';
    return { botId: id, name, alias: aliasOf(id), elo: s?.rating ?? null, uncertainty: s?.uncertainty ?? null, rank: s?.rank ?? null, matches: s?.matches ?? 0, wins: s?.wins ?? 0,
      winRate: s?.matches ? s.wins / s.matches : null, avgPoints: s?.matches ? s.totalScore / s.matches : null, lastPlayed: s?.lastPlayed ?? null, status: where,
      copyId: owned?.copyId ?? null, deleting: !!owned?.deleteAfterDrain, renameTo: owned?.renameTo ?? null };
  });
}

// ---------- snapshot for the UI ----------
export function fleetState() {
  const managed = copies.filter(c => !c.archived).map(c => {
    const live = isLive(c), record = results(c), hb = live ? heartbeat(c.runtimePath, c.pid) : null, rating = c.botId ? ratings.get(String(c.botId)) : undefined;
    return {
      copyId: c.copyId, name: c.name, kind: c.kind, sourceBotId: c.sourceBotId, sourceName: c.sourceName, createdAt: c.createdAt, startedAt: c.startedAt ?? null,
      state: c.state, botId: c.botId, pid: live ? c.pid : null, uptime: live ? procs.get(c.pid)?.elapsed ?? null : null, error: c.error, restarts: c.restarts ?? 0,
      connected: !!hb?.connected, inMatch: !!hb?.match || hb?.runningMatches?.length > 0, match: hb?.match ?? null, fidelity: c.fidelity ?? null, rating: rating ?? null, record,
      ...(live ? matchInfo(hb, c.botId, record.lastMatchId) : { currentMatchId: null, lobby: null, lastMatchId: record.lastMatchId }), canRestart: !!c.botId && existsSync(CWD + '.token-' + c.name),
      model: c.kind === 'clone-v2' ? { version: c.modelVersion ?? 1, updatedAt: c.modelUpdatedAt ?? c.createdAt, pendingReload: !!hb?.modelFittedAt && !!c.modelFittedAt && hb.modelFittedAt !== c.modelFittedAt, hotReload: !!hb?.supportsDrain } : null,
      lateRate: hb?.lateRate ?? null, bidsSampled: hb?.bidsSampled ?? 0, bidDelayMs: c.bidDelayMs ?? 0, alias: aliasOf(c.botId), rebraining: c.rebraining ?? null, relaunchAfterDrain: !!c.relaunchAfterDrain, deleteAfterDrain: !!c.deleteAfterDrain, renameTo: c.renameTo ?? null, oldCode: live && !!hb && !hb.supportsDrain,
    };
  });
  const managedPids = new Set(copies.filter(c => isLive(c)).map(c => c.pid));
  const external = [...procs.values()].filter(p => !managedPids.has(p.pid)).map(p => {
    const name = envOf(p, 'BOT_NAME').at(-1) ?? 'bot', hbPath = envOf(p, 'SCOUT_RUNTIME_PATH').at(-1) ?? DATA + 'runtime.json';
    const hb = heartbeat(hbPath, p.pid);
    // ps splits env on spaces ("larper v2" -> "larper"), and a shared heartbeat file can
    // belong to another runner: prefer the heartbeat's own name, then SCOUT_BOT_ID.
    const botId = hb?.botId ?? envOf(p, 'SCOUT_BOT_ID').at(-1) ?? null, rating = botId ? ratings.get(String(botId)) : undefined;
    return { lateRate: hb?.lateRate ?? null, bidsSampled: hb?.bidsSampled ?? 0, alias: aliasOf(botId), pid: p.pid, name: hb?.botName ?? name, strategy: envOf(p, 'STRATEGY').at(-1) ?? 'lexforge', uptime: p.elapsed, botId, connected: !!hb?.connected, inMatch: !!hb?.match || hb?.runningMatches?.length > 0, match: hb?.match ?? null, rating: rating ?? null, ...matchInfo(hb, botId, null) };
  });
  return { managed, external, jobsQueued: jobs.length, ratingsAt, cap: FLEET_CAP, used: occupancy(), upkeep };
}
