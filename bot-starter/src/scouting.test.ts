import test from 'node:test';
import assert from 'node:assert/strict';
import { scoutingAnchor, applyScoutingBid, scoutingWord, type ScoutConfig } from './scouting.js';
import { Lexicon, countsFromString } from './lexicon.js';
import type { MatchView } from './policy.js';

function config(p50 = 25, count = 20): ScoutConfig {
  return { enabled:true, revision:'test', generatedAt:new Date().toISOString(), appliedAt:new Date().toISOString(), profiles:[{botId:62, perMechanism:{firstPrice:{perLetter:{E:{archivedBids:count,p50}}},vickrey:{perLetter:{E:{archivedBids:count,p50:10}}}}}] };
}
const view = { letter:'E',firstPrice:true,opponents:[{botId:62n,balance:100,score:0}] };
test('scouting is opt-in and bounded; auction mechanisms use separate evidence',()=>{
  assert.equal(scoutingAnchor(view,20,null),20);
  assert.equal(scoutingAnchor(view,20,{...config(),enabled:false}),20);
  assert.equal(scoutingAnchor(view,20,config()),23);
  assert.equal(scoutingAnchor({...view,firstPrice:false},20,config()),17);
});
test('unknown opponents, missing samples and stale snapshots retain the baseline',()=>{
  assert.equal(scoutingAnchor({...view,opponents:[{botId:999n,balance:100,score:0}]},20,config()),20);
  assert.equal(scoutingAnchor(view,20,config(30,7)),20);
  assert.equal(scoutingAnchor({...view,letter:'Q'},20,config()),20);
  assert.equal(scoutingAnchor(view,20,{...config(),generatedAt:'2020-01-01'}),20);
  assert.equal(scoutingAnchor(view,20,{...config(),generatedAt:'invalid'}),20);
});
test('unknown rivals prevent downward shading and budget caps affect known rivals',()=>{
  assert.equal(scoutingAnchor({...view,opponents:[...view.opponents,{botId:999n,balance:100,score:0}]},20,config(5)),20);
  assert.equal(scoutingAnchor({...view,opponents:[{botId:62n,balance:3,score:0}]},20,config()),17);
  assert.equal(scoutingAnchor(view,20,config(NaN)),20);
});
test('live integration only shades first-price bids within the original caps',()=>{
  const v = {...view,auctionsLeft:30};
  assert.equal(applyScoutingBid(v,20,config(5)),17);
  assert.equal(applyScoutingBid(v,20,config(100)),20);
  assert.equal(applyScoutingBid({...v,firstPrice:false},20,config(5)),20);
  assert.equal(applyScoutingBid({...v,auctionsLeft:0},20,config(5)),20);
  for (let bid=1;bid<100;bid++) { const actual=applyScoutingBid(v,bid,config(0)); assert.ok(actual<=bid && actual>=Math.ceil(.85*bid)); }
});
test('a chosen profile drives Pegasus regardless of who its opponents are',()=>{
  const cfg: ScoutConfig = {...config(32),mode:'imitate'};
  const v = {...view,auctionsLeft:30,opponents:[{botId:999n,balance:100,score:0}]};
  assert.equal(applyScoutingBid(v,5,cfg),32);
  assert.equal(applyScoutingBid({...v,firstPrice:false},5,cfg),10);
  assert.equal(applyScoutingBid({...v,opponents:[{botId:999n,balance:2,score:0}]},5,cfg),3);
  assert.equal(applyScoutingBid({...v,auctionsLeft:0},5,cfg),5);
});
test('imitation uses the chosen word style; disable restores the existing strategy',()=>{
  const cfg: ScoutConfig = {...config(),mode:'imitate'};
  cfg.profiles[0].playStyle={primaryLength:7,primaryMinReward:20,recoveryBalance:15,recoveryMinLength:3,liquidateAt:1};
  const v = {rack:countsFromString('RETAINS'),lexicon:new Lexicon(['CAT','RETAINS']),balance:100,auctionsLeft:30} as MatchView;
  assert.equal(scoutingWord(v,()=>null,cfg),'RETAINS');
  assert.equal(scoutingWord({...v,rack:countsFromString('CAT')},()=>null,cfg),null);
  assert.equal(scoutingWord({...v,rack:countsFromString('CAT'),balance:10},()=>null,cfg),'CAT');
  assert.equal(scoutingWord({...v,rack:countsFromString('CAT'),auctionsLeft:1},()=>null,cfg),'CAT');
  assert.equal(scoutingWord(v,()=> 'original',{...cfg,enabled:false}),'original');
});
