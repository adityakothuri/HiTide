import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Lexicon, BAG_COUNTS, countsFromString } from './lexicon.js';
import type { MatchView } from './policy.js';
import { conversion, MARKET7V_PARAMS } from './strategies/conversion.js';
import { market } from './strategies/market.js';
const lexicon = new Lexicon(['AA', 'CAT', 'QUIZ', 'RETAIN', 'RETAINS', 'JOCKEY', 'JOCKEYS', 'TRAINERS']);
function view(over: Partial<MatchView> = {}): MatchView {
  return { letter: 'S', auctionsLeft: 60, balance: 60, score: 0, rack: countsFromString('RETAIN'),
    opponents: [{ balance: 100, score: 0 }], unseen: new Uint8Array(BAG_COUNTS), unseenTotal: 98,
    firstPrice: false, history: [], lexicon, ...over };
}
const candidate = conversion();
test('conversion immediately cashes seven letters and high-yield six letters', () => {
  assert.equal(candidate.play(view({ rack: countsFromString('RETAINS') })), 'RETAINS');
  assert.equal(candidate.play(view({ rack: countsFromString('JOCKEY') })), 'JOCKEY');
});
test('conversion releases cash below 35 and liquidates small words near the end', () => {
  assert.equal(candidate.play(view({ balance: 34, rack: countsFromString('QUIZ') })), 'QUIZ');
  assert.equal(candidate.play(view({ auctionsLeft: 4, rack: countsFromString('CAT') })), 'CAT');
});
test('completion funding relaxes pacing only for a required letter', () => {
  const base = market({ ...MARKET7V_PARAMS, brokeBalance: 35, brokeMinLength: 4 });
  const completing = view();
  assert.ok(candidate.bid(completing) > base.bid(completing));
  assert.ok(candidate.bid(completing) <= Math.floor(completing.balance * .6));
  const irrelevant = view({ rack: countsFromString('RETAINS'), letter: 'X' });
  assert.equal(candidate.bid(irrelevant), base.bid(irrelevant));
});
test('first-price poverty cap and current cash limit remain binding', () => {
  const v = view({ firstPrice: true, opponents: [{ balance: 1, score: 0 }] });
  assert.ok(candidate.bid(v) <= 2);
  assert.equal(candidate.bid(view({ balance: 0 })), 0);
});
test('emergency cash-in respects seven-letter cap; final window still liquidates', () => {
  const v = view({ rack: countsFromString('TRAINERS'), balance: 10, lexicon: new Lexicon(['TRAINERS']) });
  const base = market({ ...MARKET7V_PARAMS, brokeBalance: 35, brokeMinLength: 4 });
  assert.equal(base.play(v), null);
  assert.equal(candidate.play(v), null);
  assert.equal(candidate.play({ ...v, auctionsLeft: 0 }), 'TRAINERS');
});

test('funding-only ablation preserves Market7V word decisions', () => {
  const funding = conversion({ cashInRegimes: 0, cashBalance: 12, cashMinLength: 5 }, 'Market7VF');
  const base = market(MARKET7V_PARAMS);
  for (const letters of ['RETAINS', 'RETAIN', 'JOCKEY', 'QUIZ', 'CAT', 'TRAINERS', '']) {
    for (const balance of [0, 10, 34, 100]) {
      for (const auctionsLeft of [0, 4, 12, 60]) {
        const v = view({ rack: countsFromString(letters), balance, auctionsLeft });
        assert.equal(funding.play(v), base.play(v), `${letters}/${balance}/${auctionsLeft}`);
      }
    }
  }
});
