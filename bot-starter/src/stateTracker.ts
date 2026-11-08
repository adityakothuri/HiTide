// Rebuilt from a complete per-match cache, so snapshots/reconnects are idempotent.
// Starting racks are private: these are lower bounds, never exact opponent racks.
import { BAG_COUNTS, countsFromMap, slotOf, totalOf } from './lexicon.js';
import type { LiveSnapshot } from './live.js';

export function reconstructPublicState(s: LiveSnapshot) {
  const byBot = new Map(s.participants.map(p => [p.botId, {
    ...p, knownRack: new Uint8Array(26), unknownTiles: 0,
    won: new Int16Array(26), spent: new Int16Array(26),
  }]));
  const remainingUpper = new Uint8Array(BAG_COUNTS);
  const subtract = (slot: number, n = 1) => { remainingUpper[slot] = Math.max(0, remainingUpper[slot]! - n); };
  for (const r of s.results) {
    const slot = slotOf(r.letter);
    subtract(slot); // Includes unsold/discarded tiles.
    if (r.winnerBotId != null) {
      const p = byBot.get(r.winnerBotId);
      if (p) p.won[slot]!++;
    }
  }
  for (const letter of s.openLetters) subtract(slotOf(letter));
  for (const play of s.plays) {
    const p = byBot.get(play.botId);
    if (p) for (const c of play.word) p.spent[slotOf(c)]!++;
  }
  const mine = countsFromMap(s.rack);
  for (const [id, p] of byBot) {
    let minimumInitial = 0;
    for (let slot = 0; slot < 26; slot++) {
      const initial = id === s.myBotId
        ? Math.max(0, mine[slot]! + p.spent[slot]! - p.won[slot]!)
        : Math.max(0, p.spent[slot]! - p.won[slot]!);
      minimumInitial += initial;
      subtract(slot, initial);
      p.knownRack[slot] = id === s.myBotId ? mine[slot]! : Math.max(0, p.won[slot]! - p.spent[slot]!);
    }
    p.unknownTiles = id === s.myBotId ? 0 : Math.max(0, (s.startingRackSize ?? 5) - minimumInitial);
  }
  const upperTotal = totalOf(remainingUpper);
  // Exchangeable allocation estimate, not an exact composition or posterior.
  const remainingEstimate = Float64Array.from(remainingUpper, n => upperTotal ? n * s.auctionsLeft / upperTotal : 0);
  return {
    remainingUpper, remainingEstimate, totalTilesRemaining: s.auctionsLeft,
    opponents: [...byBot.values()].filter(p => p.botId !== s.myBotId).map(({ won, spent, ...p }) => p),
    recentClearingPrices: s.results.slice(-20).map(r => Number(r.paid)),
  };
}
