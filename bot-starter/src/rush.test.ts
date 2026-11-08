import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Lexicon, BAG_COUNTS, countsFromString } from './lexicon.js';
import type { MatchView } from './policy.js';
import { rush } from './strategies/rush.js';
import { conversion } from './strategies/conversion.js';
const lexicon = new Lexicon(['AA', 'CAT', 'QUIZ', 'RETAIN', 'RETAINS', 'TRAINERS']);
function view(over: Partial<MatchView> = {}): MatchView {
  return { letter:'E', rack:countsFromString('CAT'), balance:50, score:0, auctionsLeft:60,
    unseen:new Uint8Array(BAG_COUNTS), unseenTotal:98, opponents:[{balance:100,score:0}], firstPrice:false, history:[], lexicon, ...over };
}
test('rush cashes every available word without waiting for a multiplier or low balance',()=>{
  const p=rush();
  for(const [letters,word] of [['AA','AA'],['CAT','CAT'],['QUIZ','QUIZ'],['RETAIN','RETAIN'],['TRAINERS','TRAINERS']]) {
    assert.equal(p.play(view({rack:countsFromString(letters!),balance:200})),word);
  }
  assert.equal(p.play(view({rack:countsFromString('Q')})),null);
  assert.equal(p.play(view({rack:countsFromString('AAQUIZ')})),'QUIZ');
});
test('rush bids substantially above the old pacing limit with cash available',()=>{
  const before=conversion({cashInRegimes:0,cashBalance:12,cashMinLength:5},'Market7VF'), after=rush();
  for(const letter of ['E','C','H']) {
    const v=view({rack:countsFromString(''),letter});
    assert.ok(after.bid(v)>=before.bid(v)*1.5,`${letter}: ${before.bid(v)} -> ${after.bid(v)}`);
  }
});
test('rush respects cash and first-price opponent budgets',()=>{
  const p=rush();
  assert.equal(p.bid(view({balance:0})),0);
  assert.ok(p.bid(view({balance:3}))<=3);
  assert.ok(p.bid(view({firstPrice:true,opponents:[{balance:1,score:0}]}))<=2);
});

test('four-letter variant cashes four-plus words immediately and dumps short words near the end',()=>{
 const p=rush({},'MarketRush4',4);
 assert.equal(p.play(view({rack:countsFromString('QUIZ'),balance:200})),'QUIZ');
 assert.equal(p.play(view({rack:countsFromString('CAT'),balance:200})),null);
 assert.equal(p.play(view({rack:countsFromString('CAT'),auctionsLeft:4})),'CAT');
});
