// Public completed-match scouting. Run with --watch for continuous updates.
// node --import tsx bench/live/scout.mts [--watch]
import { mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

type Row = Record<string, any>;
type Match = { state: Row; participants: Row[]; auctions: Row[]; tops: Row[]; plays: Row[] };
const root = fileURLToPath(new URL('../results/scouting/', import.meta.url));
mkdirSync(root, { recursive: true });
const ratingScale = 400 / (25 / 6 * Math.LN10 * Math.SQRT2);
const siteRating = (s: Row) => Math.round(1500 + ratingScale * (Number(s.openskill_mu) - 25));
const siteUncertainty = (s: Row) => Math.round(ratingScale * Number(s.openskill_sigma));
const topN = Number(process.env.SCOUT_TOP ?? 10), sample = Number(process.env.SCOUT_MATCHES ?? 40);
const interval = Number(process.env.SCOUT_INTERVAL_SECONDS ?? 60);
if (![topN, sample, interval].every(n => Number.isInteger(n) && n > 0) || topN > 30 || sample > 200 || interval < 15) throw Error('Invalid scouting limits');
const host = process.env.STDB_HOST ?? 'https://maincloud.spacetimedb.com';
const db = process.env.STDB_DB ?? 'scrabblebot';
const cache: Record<string, Match> = (() => { try { const saved = JSON.parse(readFileSync(root + 'matches.json', 'utf8')); return saved.source === `${host}/${db}` ? saved.matches : {}; } catch { return {}; } })();
async function query(statement: string): Promise<Row[]> {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(`${host}/v1/database/${db}/sql`, { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: statement, signal: AbortSignal.timeout(30000) });
      if (!response.ok) throw Error(`SQL ${response.status}: ${(await response.text()).slice(0, 150)}`);
      const [result] = await response.json() as any[];
      if (!result) return [];
      const cols = result.schema.elements.map((e: any, i: number) => e.name.some ?? `c${i}`);
      return result.rows.map((r: any[]) => Object.fromEntries(cols.map((c: string, i: number) => [c, r[i]])));
    } catch (e) { if (attempt === 2) throw e; await new Promise(r => setTimeout(r, 1000 * (attempt + 1))); }
  }
}
function save(name: string, data: unknown) {
  writeFileSync(root + name + '.tmp', typeof data === 'string' ? data : JSON.stringify(data, null, 2) + '\n');
  renameSync(root + name + '.tmp', root + name);
}
const mean = (xs: number[]) => xs.length ? xs.reduce((a,b) => a+b,0)/xs.length : null;
const quantile = (xs: number[], p: number) => xs.length ? [...xs].sort((a,b) => a-b)[Math.floor((xs.length-1)*p)]! : null;
const option = (v: any) => Array.isArray(v) && v[0] === 0 ? Number(v[1]) : null;
const fmt = (n: number | null) => n === null ? '—' : n.toFixed(1);
function bidStats(rows: any[]) {
  const bids = rows.flatMap(r => r.top === null ? [] : [r.top]);
  return { wins: rows.length, archivedBids: bids.length, meanPaid: mean(rows.map(r => r.paid)), meanWinningBid: mean(bids), p50: quantile(bids,.5), p80: quantile(bids,.8), p90: quantile(bids,.9) };
}
async function refresh() {
  const [bots, stats, states, versions] = await Promise.all([query('SELECT * FROM bot'), query('SELECT * FROM bot_stats'), query('SELECT * FROM match_state'),query('SELECT * FROM bot_version')]);
  const names = new Map(bots.map(b => [Number(b.id), b]));
  const leaders = stats.filter(s => names.has(Number(s.bot_id)) && siteUncertainty(s) <= 175).sort((a,b) => siteRating(b)-siteRating(a)).slice(0,topN);
  const finished = new Map(states.filter(s => Array.isArray(s.status) && s.status[0] === 2).map(s => [Number(s.id),s]));
  const selections = new Map<number,number[]>();
  // Query each target's history rather than assuming they all played recently.
  for (const leader of leaders) {
    const id = Number(leader.bot_id);
    const history = await query(`SELECT * FROM match_participant WHERE bot_id = ${id}`);
    const starts = versions.filter(v => Number(v.bot_id) === id).map(v => Number(v.started_at[0]));
    const versionStart = starts.length ? Math.max(...starts) : 0;
    selections.set(id, history.map(p => Number(p.match_id)).filter(m => finished.has(m) && Number(finished.get(m)!.created_at[0]) >= versionStart).sort((a,b) => b-a).slice(0,sample));
  }
  const wanted = [...new Set([...selections.values()].flat())];
  const missing = wanted.filter(id => !cache[id]);
  console.log(`${new Date().toISOString()}: tracking ${leaders.length} leaders; ${missing.length} new completed matches`);
  for (let offset = 0; offset < missing.length; offset += 50) {
    const batch = missing.slice(offset, offset+50);
    const condition = batch.map(id => `match_id = ${id}`).join(' OR ');
    const [participants, auctions, tops, plays] = await Promise.all(['match_participant','auction_result','auction_top_bid_archive','word_play'].map(t => query(`SELECT * FROM ${t} WHERE ${condition}`)));
    for (const id of batch) {
      const select = (rows: Row[]) => rows.filter(r => Number(r.match_id) === id);
      cache[id] = { state: finished.get(id)!, participants: select(participants!), auctions: select(auctions!), tops: select(tops!), plays: select(plays!) };
    }
    save('matches.json', { source: `${host}/${db}`, matches: cache });
    console.log(`  fetched ${Math.min(offset+50,missing.length)}/${missing.length}`);
  }
  const profiles = leaders.map((s, rank) => {
    const id = Number(s.bot_id), matchIds = selections.get(id)!;
    const matches = matchIds.map(m => cache[m]!);
    const ended = matches[0]?.state.ended_at;
    const latestMatchEndedAt = Array.isArray(ended) && ended[0] === 0 ? new Date(Number(ended[1][0])/1000).toISOString() : null;
    const wins: any[] = [], words: Row[] = [], scores: number[] = [], places: number[] = [], balances: number[] = [], wordDecisions: any[] = [];
    let outrightWins = 0, tiedFirsts = 0;
    for (const m of matches) {
      const me = m.participants.find(p => Number(p.bot_id) === id)!;
      const score = Number(me.score), ahead = m.participants.filter(p => Number(p.score) > score).length;
      scores.push(score); balances.push(Number(me.balance)); places.push(ahead+1);
      if (!ahead) { if (m.participants.filter(p => Number(p.score) === score).length === 1) outrightWins++; else tiedFirsts++; }
      words.push(...m.plays.filter(w => Number(w.bot_id) === id));
      const tops = new Map(m.tops.map(t => [Number(t.auction_id),Number(t.top_bid)]));
      const ordered = [...m.auctions].sort((a,b) => Number(a.auction_id)-Number(b.auction_id));
      const myWords = m.plays.filter(w => Number(w.bot_id) === id);
      const events = [...ordered.filter(a => option(a.winner_bot_id) === id).map(a => ({time:Number(a.closed_at[0]),kind:'buy',row:a})),...myWords.map(w => ({time:Number(w.played_at[0]),kind:'word',row:w}))].sort((a,b) => a.time-b.time);
      let cash = 100;
      for (const e of events) {
        if (e.kind === 'buy') cash -= Number(e.row.paid);
        else { wordDecisions.push({length:String(e.row.word).length,reward:Number(e.row.total_reward),balance:cash,left:ordered.filter(a => Number(a.closed_at[0]) >= e.time).length-1}); cash += Number(e.row.total_reward); }
      }
      ordered.forEach((a,i) => { if (option(a.winner_bot_id) === id) wins.push({ matchId: Number(m.state.id), auctionId: Number(a.auction_id), letter: String(a.letter), paid: Number(a.paid), top: tops.get(Number(a.auction_id)) ?? null, phase: ['early','middle','late'][Math.min(2,Math.floor(i*3/ordered.length))], mechanism: m.state.auction_type[0] === 1 ? 'vickrey' : 'firstPrice' }); });
    }
    const perLetter: Record<string, ReturnType<typeof bidStats>> = Object.fromEntries([...new Set(wins.map(w => String(w.letter)))].sort().map(l => [l,bidStats(wins.filter(w => w.letter === l))]));
    const perPhase = Object.fromEntries(['early','middle','late'].map(p => [p,bidStats(wins.filter(w => w.phase === p))]));
    const perMechanism = Object.fromEntries(['firstPrice','vickrey'].map(k => [k, { ...bidStats(wins.filter(w => w.mechanism === k)), perLetter: Object.fromEntries(Object.keys(perLetter).map(l => [l,bidStats(wins.filter(w => w.mechanism === k && w.letter === l))])) }]));
    const rewardByLength = new Map<number,number>();
    for (const w of words) { const len = String(w.word).length; rewardByLength.set(len,(rewardByLength.get(len) ?? 0)+Number(w.total_reward)); }
    const primaryLength = [...rewardByLength].sort((a,b) => b[1]-a[1])[0]?.[0] ?? 7;
    const recovery = wordDecisions.filter(w => w.length < primaryLength && w.left > 5 && w.balance >= 0);
    const playStyle = { primaryLength, primaryMinReward:Math.max(0,Math.floor(quantile(wordDecisions.filter(w => w.length >= primaryLength && w.left > 5).map(w => w.reward),.1) ?? 0)), recoveryBalance:Math.max(0,Math.min(100,Math.round(quantile(recovery.map(w => w.balance),.8) ?? 15))), recoveryMinLength:Math.max(2,Math.min(primaryLength,Math.round(quantile(recovery.map(w => w.length),.5) ?? 5))), liquidateAt:Math.max(0,Math.min(3,Math.round(quantile(wordDecisions.filter(w => w.length < primaryLength && w.left >= 0 && w.left <= 3).map(w => w.left),.8) ?? 1))), recoverySamples:recovery.length };
    return { rank: leaders.findIndex(other => siteRating(other) === siteRating(s))+1, botId:id, name:String(names.get(id)!.name), rating:siteRating(s), uncertainty:siteUncertainty(s), elo:Number(s.rating), matches:matches.length, matchIds, latestMatchEndedAt, playStyle, meanScore:mean(scores), recent10MeanScore:mean(scores.slice(0,10)), meanPlace:mean(places), outrightWins, tiedFirsts, meanEndingBalance:mean(balances), tilesWonPerMatch:matches.length ? wins.length/matches.length : null, wordsPerMatch:matches.length ? words.length/matches.length : null, meanWordLength:mean(words.map(w => String(w.word).length)), sevenPlusShare:words.length ? words.filter(w => String(w.word).length >= 7).length/words.length : null, bids:bidStats(wins), perLetter, perPhase, perMechanism, wordLengths:Object.fromEntries([...new Set(words.map(w => String(w.word).length))].sort((a,b) => a-b).map(l => [l,words.filter(w => String(w.word).length === l).length])), winningObservations:wins };
  });
  const generatedAt = new Date().toISOString();
  save('profiles.json', { generatedAt, source:`${host}/${db}`, profiles, caveats:['Only completed matches and public data. Losing bids and starting racks are unknown.', 'Winning-bid samples are selection-biased; quantiles do not predict unconditional bids.', 'Paid prices are not bids in Vickrey auctions. Missing archived bids stay missing.', 'Recent matches are observational; opponents, table sizes and strategy changes confound comparisons.'] });
  const report = [`# Live opponent scouting`, `Generated ${generatedAt}. Latest ${sample} completed matches per current top-${topN} bot.`, '', '| Rank | Bot | Rating | Matches | Avg score | Avg place | Tiles/match | Word length | 7+ words | Bid p50 / p80 |', '|---:|---|---:|---:|---:|---:|---:|---:|---:|---|'];
  for (const p of profiles) report.push(`| ${p.rank} | ${p.name.replaceAll('|','/')} (${p.botId}) | ${p.rating} | ${p.matches} | ${fmt(p.meanScore)} | ${fmt(p.meanPlace)} | ${fmt(p.tilesWonPerMatch)} | ${fmt(p.meanWordLength)} | ${p.sevenPlusShare === null ? '—' : (100*p.sevenPlusShare).toFixed(0)+'%'} | ${fmt(p.bids.p50)} / ${fmt(p.bids.p80)} |`);
  for (const p of profiles) {
    report.push('', `## ${p.name} (${p.botId})`, '', `${p.matches} matches; latest ended ${p.latestMatchEndedAt ?? "unknown"}; ${p.outrightWins} outright wins, ${p.tiedFirsts} tied firsts. Recent 10 average score ${fmt(p.recent10MeanScore)}; ending balance ${fmt(p.meanEndingBalance)}.`, '', `Winning bid means by phase: early ${fmt(p.perPhase.early!.meanWinningBid)}, middle ${fmt(p.perPhase.middle!.meanWinningBid)}, late ${fmt(p.perPhase.late!.meanWinningBid)}. These compare different letters and winning outcomes.`, '', '| Letter | Wins | Archived bids | Bid p50 | Bid p80 | Mean paid |', '|---|---:|---:|---:|---:|---:|');
    for (const [l,b] of Object.entries(p.perLetter)) report.push(`| ${l} | ${b.wins} | ${b.archivedBids} | ${fmt(b.p50)} | ${fmt(b.p80)} | ${fmt(b.meanPaid)} |`);
    report.push('', `Match evidence: ${p.matchIds.join(', ')}.`);
  }
  report.push('', '## Interpretation', '', 'Public completed matches only. Losing bids and initial racks are unknown. Bid percentiles describe wins, not all bids. Missing archives are excluded. Vickrey paid prices differ from winning bids; JSON includes separate mechanism profiles. Small samples and changing opponents limit conclusions. Do not blindly outbid these percentiles: value each tile for your own rack.');
  save('REPORT.md',report.join('\n')+'\n');
  console.log(`Saved ${root}REPORT.md and profiles.json`);
  console.log(profiles.map(p => `${p.rank}. ${p.name}: ${p.matches} matches, score ${fmt(p.meanScore)}, bid p50/p80 ${fmt(p.bids.p50)}/${fmt(p.bids.p80)}`).join('\n'));
}
do {
  try { await refresh(); }
  catch (e) { console.error(new Date().toISOString(), e); if (!process.argv.includes('--watch')) process.exitCode = 1; }
  if (!process.argv.includes('--watch')) break;
  await new Promise(r => setTimeout(r,interval*1000));
} while (true);
