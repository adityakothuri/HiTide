// Scoutroom: scout the leaderboard, clone bots, and run/manage the whole fleet.
//   node --import tsx bench/live/dashboard.mts      → http://127.0.0.1:4317
import { createServer } from 'node:http';
import { readFileSync, openSync, closeSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { CWD, DATA, copies, fleetState, reconcile, refreshRatings, refreshLobbies, fleetBotIds, deleteBot, teamStats, setBidDelay, setAlias, renameOnServer, rebrain, relaunchAfterMatch, autoUpdate, upkeep, queueClones, previewModel, start, stop, archive, bulk, stopExternal, tail } from './fleet-manager.mjs';

const html = CWD + 'scout-dashboard/index.html';
const port = Number(process.env.SCOUT_PORT ?? 4317);
const origin = `http://127.0.0.1:${port}`;
const MAX_BATCH = 20;
const RECONCILE_MS = 2000, RATINGS_MS = 30000, LOBBY_MS = 3000;
const MODEL_REFRESH_MS = Number(process.env.MODEL_REFRESH_MINUTES ?? 20) * 60 * 1000;
let lastError: string | null = null, refreshBusy = false;
let watcher: ReturnType<typeof spawn> | null = null;

const read = (name: string, fallback: any = null) => { try { return JSON.parse(readFileSync(DATA + name, 'utf8')); } catch { return fallback; } };

function startWatcher() {
  if (watcher && watcher.exitCode === null) return;
  const fd = openSync(DATA + 'watcher.log', 'a');
  watcher = spawn(process.execPath, ['--import', 'tsx', 'bench/live/scout.mts', '--watch'], { cwd: CWD, stdio: ['ignore', fd, fd] });
  closeSync(fd);
  watcher.on('error', e => { lastError = `Scout failed: ${e.message}`; });
}

const idList = (v: unknown) => Array.isArray(v) && v.length <= 200 && v.every(x => typeof x === 'string') ? v as string[] : undefined;
const copyId = (body: any) => { if (typeof body.copyId !== 'string') throw Error('Choose a bot.'); return body.copyId as string; };

async function post(url: string, body: any): Promise<[number, unknown]> {
  switch (url) {
    case '/api/preview': {
      if (!Number.isSafeInteger(body.botId)) throw Error('Choose a bot.');
      const model = await previewModel(body.botId);
      return [200, { source: model.source, style: model.style, sigma: model.bid.sigma, validation: model.validation, evidence: model.evidence, fittedAt: model.fittedAt }];
    }
    case '/api/clone': {
      const snapshot = read('profiles.json');
      const ids = body.botIds, count = body.count ?? 1;
      if (!Array.isArray(ids) || !ids.length || ids.some((id: unknown) => !Number.isSafeInteger(id))) throw Error('Select at least one bot to clone.');
      if (!Number.isInteger(count) || count < 1 || ids.length * count > MAX_BATCH) throw Error(`Launch at most ${MAX_BATCH} clones per batch.`);
      if (body.generatedAt && body.generatedAt !== snapshot?.generatedAt) throw Error('Profiles updated. Review the newest snapshot first.');
      const sources = ids.map((id: number) => snapshot?.profiles?.find((p: any) => p.botId === id));
      if (sources.some((s: unknown) => !s)) throw Error('A selected bot left the snapshot. Reload.');
      const made = queueClones(sources.flatMap((s: any) => Array.from({ length: count }, () => ({ botId: s.botId, name: s.name }))));
      return [202, { message: `Queued ${made.length} clone${made.length === 1 ? '' : 's'}. Each gets its own team, credential and process.` }];
    }
    case '/api/bot/start': return [200, { message: start(copyId(body)) }];
    case '/api/bot/stop': return [200, { message: stop(copyId(body), 'now') }];
    case '/api/bot/drain': return [200, { message: stop(copyId(body), 'drain') }];
    case '/api/bot/remove': return [200, { message: archive(copyId(body)) }];
    case '/api/bot/bid-delay': return [200, { message: setBidDelay(copyId(body), Number(body.ms)) }];
    case '/api/bot/alias': {
      if (typeof body.botId !== 'string' || typeof body.alias !== 'string') throw Error('Choose a bot and a nickname.');
      return [200, { message: setAlias(body.botId, body.alias) }];
    }
    case '/api/bot/rename': {
      if (typeof body.name !== 'string') throw Error('Enter a new name.');
      return [200, { message: await renameOnServer(copyId(body), body.name) }];
    }
    case '/api/bot/delete': return [200, { message: deleteBot(copyId(body)) }];
    case '/api/bot/rebrain': {
      if (!Number.isSafeInteger(body.sourceBotId)) throw Error('Choose a source bot.');
      return [200, { message: await rebrain(copyId(body), body.sourceBotId) }];
    }
    case '/api/bot/relaunch': return [200, { message: relaunchAfterMatch(copyId(body)) }];
    case '/api/fleet/update': {
      if (upkeep.running) throw Error('Models are already being updated.');
      void autoUpdate(MODEL_REFRESH_MS);
      return [202, { message: 'Refitting every live clone on its source\'s newest matches.' }];
    }
    case '/api/fleet': {
      if (!['stop', 'drain', 'start', 'delete'].includes(body.action)) throw Error('Unknown fleet action.');
      if (body.action === 'delete' && !idList(body.copyIds)?.length) throw Error('Select the bots to delete.');
      return [200, { message: bulk(body.action, idList(body.copyIds)) }];
    }
    case '/api/external/stop': {
      if (!Number.isSafeInteger(body.pid)) throw Error('Choose a process.');
      return [200, { message: stopExternal(body.pid) }];
    }
    case '/api/refresh': {
      if (watcher && watcher.exitCode === null) return [200, { message: 'Continuous scout is running; profiles refresh about every minute.' }];
      if (refreshBusy) throw Error('A refresh is already running.');
      refreshBusy = true;
      const child = spawn(process.execPath, ['--import', 'tsx', 'bench/live/scout.mts'], { cwd: CWD, stdio: 'ignore' });
      child.on('exit', code => { refreshBusy = false; if (code) lastError = 'Scout refresh failed. Try again.'; });
      child.on('error', e => { refreshBusy = false; lastError = e.message; });
      return [202, { message: 'Fetching the latest completed matches.' }];
    }
  }
  return [404, { error: 'Not found' }];
}

const server = createServer(async (req, res) => {
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  const send = (code: number, body: unknown) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(body)); };
  try {
    // Reject DNS-rebinding and cross-site requests: this server can start and stop processes.
    if (req.headers.host !== `127.0.0.1:${port}`) { send(403, { error: 'Open the dashboard at ' + origin }); return; }
    const url = new URL(req.url ?? '/', origin);
    if (req.method === 'GET') {
      if (url.pathname === '/') { res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(readFileSync(html)); return; }
      if (url.pathname === '/themes.css') { res.writeHead(200, { 'Content-Type': 'text/css; charset=utf-8' }); res.end(readFileSync(CWD + 'scout-dashboard/themes.css')); return; }
      if (url.pathname === '/api/state') { send(200, { ...read('profiles.json', {}), fleet: fleetState(), stats: teamStats(), lastError, refreshBusy, watcherRunning: !!watcher && watcher.exitCode === null }); return; }
      if (url.pathname === '/api/logs') {
        const c = copies.find(x => x.copyId === url.searchParams.get('copyId'));
        if (!c) { send(404, { error: 'Unknown bot' }); return; }
        send(200, { name: c.name, log: tail(c.logPath, 24000) }); return;
      }
      send(404, { error: 'Not found' }); return;
    }
    if (req.method !== 'POST') { send(405, { error: 'Method not allowed' }); return; }
    if (req.headers.origin !== origin || !req.headers['content-type']?.startsWith('application/json')) { send(403, { error: 'Use the local dashboard to make changes.' }); return; }
    let raw = '';
    for await (const chunk of req) { raw += chunk; if (raw.length > 20000) throw Error('Request too large'); }
    const [code, body] = await post(url.pathname, raw ? JSON.parse(raw) : {});
    if (code < 400) lastError = null;
    send(code, body);
  } catch (e) { send(400, { error: e instanceof Error ? e.message : String(e) }); }
});

reconcile(); void refreshRatings();
upkeep.nextRunAt = new Date(Date.now() + MODEL_REFRESH_MS).toISOString();
const timers = [setInterval(reconcile, RECONCILE_MS), setInterval(() => void refreshRatings(), RATINGS_MS), setInterval(() => void refreshLobbies(fleetBotIds()), LOBBY_MS), setInterval(() => void autoUpdate(MODEL_REFRESH_MS), MODEL_REFRESH_MS)];
server.listen(port, '127.0.0.1', () => { console.log(`Scoutroom: ${origin}`); startWatcher(); });

// Bots are detached: they keep playing when the dashboard stops, and are re-adopted on restart.
function shutdown() { timers.forEach(clearInterval); watcher?.kill('SIGTERM'); server.close(); process.exit(0); }
process.on('SIGTERM', shutdown); process.on('SIGINT', shutdown);
