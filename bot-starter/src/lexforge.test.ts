import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Lexicon,BAG_COUNTS,countsFromString } from './lexicon.js';
import type { MatchView } from './policy.js';
import { lexforge } from './strategies/lexforge.js';
import { LEXFORGE_MODEL } from './strategies/lexforgeModel.js';
import { LEXFORGE_FEATURE_NAMES } from './strategies/lexforgeFeatures.js';
const lexicon=new Lexicon(['AA','CAT','QUIZ','RETAIN','RETAINS','JOCKEY','JOCKEYS','AXIOLOGY','JAWBONE','JAWBONER']);
function view(over:Partial<MatchView>={}):MatchView{return{letter:'E',rack:countsFromString('RETAINS'),balance:100,score:0,auctionsLeft:40,
 unseen:new Uint8Array(BAG_COUNTS),unseenTotal:98,opponents:[{balance:100,score:0}],history:[],firstPrice:false,lexicon,...over};}
test('LexForge copy preserves observed 45-point seven-plus primary rule, including eight-letter words',()=>{
 const p=lexforge();
 assert.equal(p.play(view()),null); // A weak 21-point bingo is held while well funded.
 assert.equal(p.play(view({rack:countsFromString('JOCKEYS')})),'JOCKEYS');
 assert.equal(p.play(view({rack:countsFromString('AXIOLOGY')})),'AXIOLOGY');
 assert.equal(p.play(view({rack:countsFromString('JOCKEY')})),null); // Six letters do not trigger the primary rule.
});
test('LexForge recovers below 15 coins with five-plus letters and liquidates one auction early',()=>{
 const p=lexforge();
 assert.equal(p.play(view({balance:14,rack:countsFromString('RETAIN')})),'RETAIN');
 assert.equal(p.play(view({balance:15,rack:countsFromString('RETAIN')})),null);
 assert.equal(p.play(view({balance:10,rack:countsFromString('QUIZ')})),null);
 assert.equal(p.play(view({auctionsLeft:1,rack:countsFromString('QUIZ')})),'QUIZ');
 assert.equal(p.play(view({auctionsLeft:0,rack:countsFromString('CAT')})),'CAT');
});
test('LexForge fitted bids are repeatable, affordable, and capped against poor first-price rivals',()=>{
 const p=lexforge(),v=view();assert.equal(p.bid(v),p.bid(v));
 for(const balance of [0,1,7,100,500])for(const letter of 'AEQXZ'){
  const b=p.bid(view({balance,letter}));assert.ok(Number.isInteger(b)&&b>=0&&b<=balance);
 }
 assert.ok(p.bid(view({firstPrice:true,opponents:[{balance:1,score:0}]}))<=2);
 assert.equal(p.bid(view({balance:57,auctionsLeft:0})),57);
});
test('LexForge fitted model dimensions and chronological split match the runtime features',()=>{
 const n=LEXFORGE_FEATURE_NAMES.length;
 assert.equal(LEXFORGE_MODEL.weights.length,n+1);assert.equal(LEXFORGE_MODEL.means.length,n);assert.equal(LEXFORGE_MODEL.scales.length,n);
 assert.ok(LEXFORGE_MODEL.scales.every(x=>Number.isFinite(x)&&x>0));
 assert.ok(Math.max(...LEXFORGE_MODEL.trainingMatchIds)<Math.min(...LEXFORGE_MODEL.validationMatchIds));
});

test('LexForge primary word choice preserves useful tiles when extra common letters add no net utility',()=>{
 assert.equal(lexforge().play(view({rack:countsFromString('JAWBONER')})),'JAWBONE');
});
