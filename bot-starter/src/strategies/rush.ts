// User-selected aggressive mode: pay up for tiles and never hold a valid word.
import type { Policy } from '../policy.js';
import { market, type MarketParams } from './market.js';

export const RUSH_PARAMS: Partial<MarketParams> = {
  anchor: 1.35, anchor1pt: 0.95, anchorMid: 1.35, anchorHigh: 1.2,
  pointsToBid: 1.5, paceK: 24, paceFaceBoost: 0.75, maxBidShare: 0.85,
  duplicatePenalty: 0.12, reserveRounds: 0,
  plan: { maxWordLength: 7, playSearch: 0 },
};

export function rush(overrides: Partial<MarketParams> = {}, name = 'MarketRush', minWordLength = 2): Policy {
  const bidder = market({ ...RUSH_PARAMS, ...overrides }, `${name}-bids`);
  return {
    name,
    bid(v) {
      let amount = bidder.bid(v);
      if (v.firstPrice) amount = Math.min(amount, Math.max(0, ...v.opponents.map(o => o.balance)) + 1);
      return Math.max(0, Math.min(Math.floor(v.balance), amount));
    },
    play(v) {
      // Highest actual reward now, any valid length. The live loop repeats
      // after each confirmed reducer until no word remains; no hold threshold.
      const i = v.lexicon.best(v.rack, v.auctionsLeft <= 4 ? 2 : minWordLength);
      return i < 0 ? null : v.lexicon.words[i]!;
    },
  };
}
