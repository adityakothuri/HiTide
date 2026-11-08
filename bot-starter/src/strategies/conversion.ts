// A live-test candidate: Market7V pricing plus the useful cash-in/refund
// regimes from the earlier portfolio model. No leftover-potential search.
import type { MatchView, Policy } from '../policy.js';
import { wordReward } from '../lexicon.js';
import { market, type MarketParams } from './market.js';

export const MARKET7V_PARAMS: Partial<MarketParams> = {
  paceK: 12, paceFaceBoost: 0.5, brokeBalance: 12, brokeMinLength: 5,
  anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1,
  plan: { maxWordLength: 7, playSearch: 0 },
};
export const CONVERSION_PARAMS = {
  cashInRegimes: 1, // 0 isolates completion funding with unchanged base word play.
  cashBalance: 35, cashMinLength: 4, sixMinScore: 24,
  refundFraction: 0.95, cashBidShare: 0.6,
  firstPriceShade: 0.8,
};

export function conversion(overrides: Partial<typeof CONVERSION_PARAMS> = {}, name = 'Market7VC', marketOverrides: Partial<MarketParams> = {}): Policy {
  const p = { ...CONVERSION_PARAMS, ...overrides };
  const settings = { ...MARKET7V_PARAMS, ...marketOverrides, plan: { ...MARKET7V_PARAMS.plan, ...marketOverrides.plan }, brokeBalance: p.cashBalance, brokeMinLength: p.cashMinLength };
  const base = market(settings, `${name}-base`);
  // Removes only the pacing cap, retaining market valuation, budget share,
  // duplicates, vowel balance and first-price shading.
  const unpaced = market({ ...settings, paceK: 0 }, `${name}-completion`);

  function cashWord(v: MatchView): string | null {
    const lex = v.lexicon;
    let best = -1;
    const consider = (i: number) => {
      if (i >= 0 && (best < 0 || lex.reward[i]! > lex.reward[best]! ||
        (lex.reward[i] === lex.reward[best] && lex.length[i]! > lex.length[best]!))) best = i;
    };
    consider(lex.best(v.rack, 7, 7));
    const six = lex.best(v.rack, 6, 6);
    if (six >= 0 && lex.reward[six]! >= p.sixMinScore) consider(six);
    if (v.balance < p.cashBalance) consider(lex.best(v.rack, p.cashMinLength, 7));
    if (v.auctionsLeft <= 4) consider(lex.best(v.rack, 2, 7));
    else if (v.auctionsLeft <= 12) {
      consider(lex.best(v.rack, v.auctionsLeft <= 8 ? 4 : 5, 7));
      const any = lex.best(v.rack, 2, 7);
      if (any >= 0 && lex.reward[any]! >= (v.auctionsLeft <= 8 ? 8 : 14)) consider(any);
    }
    return best < 0 ? null : lex.words[best]!;
  }

  return {
    name,
    play(v) {
      // Preserve the existing last-chance liquidation, including >7 letters
      // if that is the only way to turn otherwise worthless tiles into points.
      if (v.auctionsLeft === 0) return base.play(v);
      return p.cashInRegimes >= 1 ? cashWord(v) ?? base.play(v) : base.play(v);
    },
    bid(v) {
      if (v.auctionsLeft === 0) return base.bid(v);
      const baseline = base.bid(v);
      if (v.balance <= 0) return 0;
      const slot = v.letter.charCodeAt(0) - 65;
      const afterRack = new Uint8Array(v.rack); afterRack[slot]!++;
      const after = { ...v, rack: afterRack };
      const word = p.cashInRegimes >= 1 ? cashWord(after) : base.play(after);
      let bid = baseline;
      if (word) {
        // Only relax pacing when this tile is actually required by the cash-in.
        let needed = 0;
        for (const c of word) if (c === v.letter) needed++;
        if (needed > v.rack[slot]!) {
          const refundCap = wordReward(word) * p.refundFraction * (v.firstPrice ? p.firstPriceShade : 1);
          bid = Math.max(bid, Math.floor(Math.min(unpaced.bid(v), v.balance * p.cashBidShare, refundCap)));
        }
      }
      // Earlier first-price candidate's safe affordability cap: preserve
      // Market7V's pricing, but never pay more than needed to beat all budgets.
      if (v.firstPrice) bid = Math.min(bid, Math.max(0, ...v.opponents.map(o => o.balance)) + 1);
      return Math.max(0, Math.min(Math.floor(v.balance), bid));
    },
  };
}
