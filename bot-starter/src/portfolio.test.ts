import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Lexicon, BAG_COUNTS, countsFromString, wordReward } from './lexicon.js';
import { evaluateRackPortfolio, findPlayableWords } from './dict.js';
import { reconstructPublicState } from './stateTracker.js';
import { portfolio } from './strategies/portfolio.js';
import type { MatchView } from './policy.js';
import type { LiveSnapshot } from './live.js';
const lexicon = new Lexicon(['AA', 'CAT', 'QUIZ', 'RETAIN', 'RETAINS', 'STAINER']);
function view(over: Partial<MatchView> = {}): MatchView {
  return { letter: 'S', auctionsLeft: 30, balance: 100, score: 0, rack: countsFromString('RETAIN'),
    opponents: Array.from({ length: 5 }, () => ({ balance: 100, score: 0 })),
    unseen: new Uint8Array(BAG_COUNTS), unseenTotal: 98, firstPrice: false, history: [], lexicon, ...over };
}
test('one-away EV counts a letter once across anagrams and ignores exhausted letters', () => {
  const bag = new Uint8Array(26); bag[18] = 1;
  const result = evaluateRackPortfolio(lexicon, countsFromString('RETAIN'), bag);
  assert.equal(result.nearBingoEV, 21);
  assert.equal(result.bingoAvailable, true);
  assert.equal(evaluateRackPortfolio(lexicon, countsFromString('RETAIN'), new Uint8Array(26)).nearBingoEV, 0);
  assert.equal(evaluateRackPortfolio(lexicon, countsFromString('RETIN'), bag).bingoAvailable, false);
});
test('playable queries check duplicate multiplicities and sort by reward', () => {
  assert.deepEqual(findPlayableWords(lexicon, countsFromString('AQ')).map(i => lexicon.words[i]), []);
  assert.deepEqual(findPlayableWords(lexicon, countsFromString('AAQUIZ')).map(i => lexicon.words[i]), ['QUIZ', 'AA']);
});
test('public tracking keeps starting racks unknown and removes discarded auctions', () => {
  const snapshot: LiveSnapshot = { myBotId: 1n, matchId: 1n, startingRackSize: 5,
    rack: new Map([['A', 5]]), participants: [{ botId: 1n, balance: 100, score: 0 }, { botId: 2n, balance: 90, score: 0 }],
    letter: 'E', auctionsLeft: 85, firstPrice: false, openLetters: ['E'],
    results: [{ auctionId: 1n, letter: 'Z', paid: 0n }, { auctionId: 2n, letter: 'S', winnerBotId: 2n, paid: 10n }], plays: [] };
  const state = reconstructPublicState(snapshot);
  assert.equal(state.remainingUpper[25], 0);
  assert.equal(state.remainingUpper[0], 4);
  assert.equal(state.opponents[0]!.knownRack[18], 1);
  assert.equal(state.opponents[0]!.unknownTiles, 5);
  assert.equal(state.opponents[0]!.balance, 90);
  assert.ok(Math.abs(state.remainingEstimate.reduce((a, b) => a + b, 0) - 85) < 1e-10);
  assert.deepEqual(reconstructPublicState(snapshot), state);
});
test('endgame liquidates before the last close and never pays for its unusable tile', () => {
  const bot = portfolio();
  assert.equal(bot.play(view({ rack: countsFromString('CAT'), auctionsLeft: 4 })), 'CAT');
  assert.equal(bot.bid(view({ auctionsLeft: 0 })), 0);
  assert.equal(bot.play(view({ rack: countsFromString('RETAINS') })), 'RETAINS');
});
test('liquidity crisis recovers cash and poverty caps first-price bids', () => {
  const bot = portfolio();
  assert.equal(bot.play(view({ rack: countsFromString('QUIZ'), balance: 10 })), 'QUIZ');
  const bid = bot.bid(view({ firstPrice: true, opponents: [{ balance: 1, score: 0 }] }));
  assert.ok(bid <= 2);
  assert.equal(bot.bid(view({ balance: 0 })), 0);
});

import { runMatch, mulberry32 } from './sim.js';
test('simulator discards unbid tiles and gives clients no final-close callback', () => {
  let bids = 0, plays = 0;
  const passive = {
    name: 'Passive', bid: () => { bids++; return 0; },
    play: () => { plays++; return null; },
  };
  const result = runMatch(Array.from({ length: 6 }, () => ({ kind: 'policy' as const, policy: passive })),
    mulberry32(12), { lexicon, firstPrice: false, startingRack: 5, startingBalance: 100 });
  assert.equal(bids, 6 * 68);
  assert.equal(plays, 6 * 68); // No extra play round after the final close.
  assert.ok(result.every(r => r.tilesWon === 0 && r.score === 0 && r.balance === 100 && r.tilesLeft === 5));
});

test('fractional length multipliers truncate exactly like bigint server arithmetic', () => {
  assert.equal(wordReward('AXES'), 16); // (1+8+1+1)*3/2
  assert.equal(wordReward('AXISES'), 32); // (1+8+1+1+1+1)*5/2
});
