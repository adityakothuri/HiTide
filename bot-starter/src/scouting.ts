import { existsSync, readFileSync, statSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
import type { MatchView } from './policy.js';

export const SCOUT_DIR = fileURLToPath(new URL('../bench/results/scouting/', import.meta.url));
export type ScoutConfig = { enabled: boolean; revision: string; generatedAt: string; appliedAt: string; profiles: any[]; mode?: 'imitate' | 'opponents' };
let config: ScoutConfig | null = null, checkedAt = 0, modified = -1;
export function loadScouting(): ScoutConfig | null {
  if (Date.now() - checkedAt < 1000) return config;
  checkedAt = Date.now();
  try {
    const file = process.env.SCOUT_CONFIG_PATH ?? SCOUT_DIR + 'active.json';
    if (!existsSync(file)) { config = null; return null; }
    const mtime = statSync(file).mtimeMs;
    if (mtime !== modified) {
      const parsed = JSON.parse(readFileSync(file, 'utf8'));
      if (typeof parsed.enabled !== 'boolean' || typeof parsed.revision !== 'string' || !Array.isArray(parsed.profiles)) throw Error('Invalid scouting configuration');
      config = parsed; modified = mtime;
    }
  } catch { config = null; }
  return config;
}

// Experimental market-anchor adaptation. Own-rack marginal value and all
// existing balance/pacing/completion caps are still computed by the strategy.
export function scoutingAnchor(view: Pick<MatchView, 'letter' | 'firstPrice' | 'opponents'>, baseline: number, settings = loadScouting()): number {
  if (!settings?.enabled || !Number.isFinite(baseline) || baseline <= 0) return baseline;
  const age = Date.now() - Date.parse(settings.generatedAt);
  if (!Number.isFinite(age) || age > 24 * 60 * 60 * 1000 || age < -60000) return baseline;
  const mechanism = view.firstPrice ? 'firstPrice' : 'vickrey';
  let highest = 0, matched = 0, unknown = false;
  for (const opponent of view.opponents) {
    const profile = settings.profiles.find(p => String(p.botId) === String(opponent.botId));
    const stats = profile?.perMechanism?.[mechanism]?.perLetter?.[view.letter];
    // Require eight observed winning bids for this exact letter/mechanism.
    if (!stats || stats.archivedBids < 8 || !Number.isFinite(stats.p50) || stats.p50 < 0) { unknown = true; continue; }
    matched++;
    highest = Math.max(highest, Math.min(opponent.balance, stats.p50));
  }
  if (!matched) return baseline;
  if (unknown) highest = Math.max(highest, baseline);
  return Math.max(baseline * .85, Math.min(baseline * 1.15, highest));
}

// First-price bid shading only: never exceed the strategy's own valuation,
// pacing or affordability cap. Keep Vickrey and final-auction decisions intact.
export function applyScoutingBid(view: Pick<MatchView, 'letter' | 'firstPrice' | 'opponents' | 'auctionsLeft'>, raw: number, settings = loadScouting()): number {
  if (settings?.enabled && settings.mode === 'imitate' && settings.profiles.length === 1 && view.auctionsLeft !== 0) {
    const profile = settings.profiles[0];
    const mechanism = profile.perMechanism?.[view.firstPrice ? 'firstPrice' : 'vickrey'];
    const letter = mechanism?.perLetter?.[view.letter];
    const stats = letter?.archivedBids >= 5 ? letter : mechanism?.archivedBids >= 10 ? mechanism : null;
    if (!stats || !Number.isFinite(stats.p50)) return raw;
    // This is an empirical imitation of observed wins, not the hidden source.
    const budgetCap = view.firstPrice ? Math.max(0,...view.opponents.map(p => p.balance)) + 1 : Infinity;
    return Math.max(0,Math.min(Math.round(stats.p50),budgetCap));
  }
  if (!view.firstPrice || view.auctionsLeft === 0 || raw <= 0) return raw;
  return Math.min(raw, Math.ceil(scoutingAnchor(view, raw, settings)));
}

export function scoutingWord(view: MatchView, fallback: () => string | null, settings = loadScouting()): string | null {
  if (!settings?.enabled || settings.mode !== 'imitate' || settings.profiles.length !== 1) return fallback();
  const style = settings.profiles[0].playStyle;
  if (!style || !Number.isInteger(style.primaryLength)) return fallback();
  if (view.auctionsLeft <= style.liquidateAt) {
    const i = view.lexicon.best(view.rack,2); return i < 0 ? null : view.lexicon.words[i]!;
  }
  let i = view.lexicon.best(view.rack,style.primaryLength);
  if (i >= 0 && view.lexicon.reward[i]! >= style.primaryMinReward) return view.lexicon.words[i]!;
  if (view.balance <= style.recoveryBalance) {
    i = view.lexicon.best(view.rack,style.recoveryMinLength);
    if (i >= 0) return view.lexicon.words[i]!;
  }
  return null;
}

export function writeScoutHeartbeat(state: Record<string, unknown>) {
  try {
    mkdirSync(SCOUT_DIR, { recursive: true });
    const current = loadScouting();
    const file = process.env.SCOUT_RUNTIME_PATH ?? SCOUT_DIR + 'runtime.json';
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file + '.tmp', JSON.stringify({ ...state, hookVersion: 3, pid: process.pid, heartbeatAt: new Date().toISOString(), revision: current?.revision ?? null, enabled: current?.enabled ?? false, profileName:current?.enabled && current.mode === 'imitate' ? current.profiles[0]?.name ?? null : null }));
    renameSync(file + '.tmp', file);
  } catch (e) { console.warn('[scout] heartbeat failed:', String(e)); }
}
