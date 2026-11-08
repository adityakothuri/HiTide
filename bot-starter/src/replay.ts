// Locked-market replay of finished real matches. Rivals' bids/plays do not
// react to counterfactual purchases. This is a diagnostic, not a live win-rate.
import { BAG_COUNTS, Lexicon, slotOf, totalOf, wordReward } from './lexicon.js';
import type { MatchView, Policy, AuctionRecord } from './policy.js';
import { mulberry32 } from './sim.js';
export interface ArchivedAuction { id: number; letter: string; winner: number | null; paid: number; top: number; time: number }
export interface ArchivedPlay { bot: number; word: string; reward: number; time: number }
export interface ArchivedMatch { id: number; createdAt: number; startingRack: number; bots: number[]; auctions: ArchivedAuction[]; plays: ArchivedPlay[] }

/** Exact rival maximum except a solo reserve-price win, which leaves 0 vs 1 ambiguous. */
export function rivalMaximum(a: ArchivedAuction, hero: number, reserveRival: 0 | 1): number {
  return a.winner === hero ? (a.paid === 1 ? reserveRival : a.paid) : a.top;
}

/** The complete auction sequence reveals the aggregate starting rack pool.
 * Prefix deficits reveal minimum starting counts for each player. Allocate the
 * remaining private tiles randomly subject to these constraints. Selection of
 * words can reveal additional information; this is not an exact posterior. */
export function sampleStartingRacks(m: ArchivedMatch, seed: number): Map<number, Uint8Array> {
  const pool = Int16Array.from(BAG_COUNTS);
  for (const a of m.auctions) pool[slotOf(a.letter)]!--;
  if (pool.some(n => n < 0) || pool.reduce((a,b) => a+b,0) !== m.bots.length * m.startingRack)
    throw new Error(`Match ${m.id}: incomplete auction sequence or unsupported bag configuration`);
  const net = new Map(m.bots.map(bot => [bot, new Int16Array(26)]));
  const racks = new Map(m.bots.map(bot => [bot, new Uint8Array(26)]));
  const events = [
    ...m.auctions.filter(a => a.winner !== null).map(a => ({ time: a.time, order: 0, bot: a.winner!, letters: a.letter, sign: 1 })),
    ...m.plays.map(p => ({ time: p.time, order: 1, bot: p.bot, letters: p.word, sign: -1 })),
  ].sort((a,b) => a.time-b.time || a.order-b.order);
  for (const e of events) {
    const held = net.get(e.bot), required = racks.get(e.bot);
    if (!held || !required) throw new Error('Unknown participant in public history');
    for (const c of e.letters) { const s = slotOf(c); held[s]! += e.sign; required[s] = Math.max(required[s]!, -held[s]!); }
  }
  for (const rack of racks.values()) {
    if (totalOf(rack) > m.startingRack) throw new Error(`Match ${m.id}: inconsistent public word history`);
    for (let s=0;s<26;s++) pool[s]! -= rack[s]!;
  }
  if (pool.some(n=>n<0)) throw new Error(`Match ${m.id}: impossible starting rack allocation`);
  const minimum = new Map([...racks].map(([bot,rack])=>[bot,new Uint8Array(rack)]));
  const rng = mulberry32(seed);
  for (const rack of racks.values()) {
    while (totalOf(rack) < m.startingRack) {
      let pick = Math.floor(rng() * pool.reduce((a,b)=>a+b,0));
      for (let s=0;s<26;s++) { pick -= pool[s]!; if (pick < 0) { pool[s]!--; rack[s]!++; break; } }
    }
  }
  // Symmetric swaps over labeled dealt tiles avoid the allocation-order bias
  // of treating required minima as permanently fixed tiles. Finite burn-in
  // approximates conditioning on the prefix constraints, not word-choice odds.
  const owners: number[] = [], letters: number[] = [];
  for (const [bot,rack] of racks) for (let s=0;s<26;s++) for(let n=0;n<rack[s]!;n++) { owners.push(bot); letters.push(s); }
  for (let step=0;step<2000;step++) {
    const i=Math.floor(rng()*letters.length), j=Math.floor(rng()*letters.length);
    const a=owners[i]!, b=owners[j]!, x=letters[i]!, y=letters[j]!;
    if (a===b || x===y) continue;
    const ra=racks.get(a)!, rb=racks.get(b)!;
    if (ra[x]!<=minimum.get(a)![x]! || rb[y]!<=minimum.get(b)![y]!) continue;
    ra[x]!--;ra[y]!++;rb[y]!--;rb[x]!++;[letters[i],letters[j]]=[y,x];
  }
  return racks;
}

export function replayMatch(m: ArchivedMatch, hero: number, initial: Uint8Array, policy: Policy, lexicon: Lexicon,
  scenario: { winTies: boolean; reserveRival: 0 | 1 }) {
  let rack = new Uint8Array(initial), balance = 100, score = 0, tilesPlayed = 0, tilesWon = 0, spent = 0;
  let starvedRounds = 0, ties = 0, calls = 0;
  const words: string[] = [], history: AuctionRecord[] = [], drawn = new Uint8Array(26);
  const rivals = new Map(m.bots.filter(b=>b!==hero).map(bot=>[bot,{ balance:100, score:0 }]));
  const events = [
    ...m.auctions.filter(a=>a.winner!==null && a.winner!==hero).map(a=>({ time:a.time, order:0, bot:a.winner!, paid:a.paid, reward:0 })),
    ...m.plays.filter(p=>p.bot!==hero).map(p=>({ time:p.time, order:1, bot:p.bot, paid:0, reward:p.reward })),
  ].sort((a,b)=>a.time-b.time || a.order-b.order);
  let eventIndex = 0;
  for (let round=0;round<m.auctions.length;round++) {
    const a = m.auctions[round]!, opened = round ? m.auctions[round-1]!.time : m.createdAt;
    while (eventIndex < events.length && events[eventIndex]!.time <= opened) {
      const e = events[eventIndex++]!, rival = rivals.get(e.bot)!;
      rival.balance += e.reward-e.paid; rival.score += e.reward;
    }
    const slot = slotOf(a.letter); drawn[slot]!++;
    const unseen = Uint8Array.from(BAG_COUNTS, (n,s)=>Math.max(0,n-drawn[s]!-initial[s]!));
    const view: MatchView = {
      letter:a.letter, auctionsLeft:m.auctions.length-round-1, balance, score, rack,
      opponents:[...rivals.values()], unseen, unseenTotal:totalOf(unseen), firstPrice:false, history, lexicon,
    };
    for (let plays=0;plays<30;plays++) {
      const word = policy.play({ ...view, letter:'', rack, balance, score }); calls++;
      if (!word) break;
      if (!lexicon.has(word)) throw new Error(`Invalid word ${word}`);
      const next = new Uint8Array(rack);
      for (const c of word) { const s=slotOf(c); if (!next[s]) throw new Error(`Missing letters for ${word}`); next[s]!--; }
      rack=next; const reward=wordReward(word); balance+=reward; score+=reward; tilesPlayed+=word.length; words.push(word);
    }
    const bid = policy.bid({ ...view, rack, balance, score }); calls++;
    if (!Number.isInteger(bid) || bid<0 || bid>balance) throw new Error(`Illegal bid ${bid}`);
    const rival = rivalMaximum(a,hero,scenario.reserveRival);
    if (balance<rival) starvedRounds++;
    if (bid>0 && bid===rival) ties++;
    const won = bid>0 && (bid>rival || (bid===rival && scenario.winTies));
    const paid = won ? Math.max(1,rival) : a.paid;
    if (won) { balance-=paid; spent+=paid; rack[slot]!++; tilesWon++; }
    history.push({ slot, paid, mine:won });
    // No word callback after the final auction awards its tile.
  }
  return { score, balance, tilesPlayed, tilesWon, spent, starvedRounds, ties, words:words.length,
    tilesLeft:totalOf(rack), pointsPerPlayedTile:tilesPlayed ? score/tilesPlayed : 0, calls };
}
