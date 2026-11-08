import assert from'node:assert/strict';
import{test}from'node:test';
import{readFileSync,readdirSync}from'node:fs';
import{createHash}from'node:crypto';
import{Lexicon,BAG_COUNTS,countsFromString}from'./lexicon.js';
import type{MatchView}from'./policy.js';
import{imitationPolicy,validateImitationModel,type ImitationModel}from'./fleetPolicy.js';
const manifest=JSON.parse(readFileSync('fleet/manifest.json','utf8'));
const lexicon=Lexicon.fromFile(new URL('../../spacetimedb/wordlist.txt',import.meta.url));
function view(over:Partial<MatchView>={}):MatchView{return{letter:'E',rack:countsFromString('RETAINSJOCKEYX'),balance:100,score:0,auctionsLeft:40,unseen:new Uint8Array(BAG_COUNTS),unseenTotal:98,opponents:[{balance:5,score:0}],firstPrice:false,history:[],lexicon,...over};}
test('fleet snapshots have ten distinct letter names, source bots, and immutable model hashes',()=>{
 assert.equal(manifest.entries.length,10);assert.equal(new Set(manifest.entries.map((e:any)=>e.name)).size,10);assert.equal(new Set(manifest.entries.map((e:any)=>e.sourceBotId)).size,10);
 for(const e of manifest.entries){assert.match(e.name,/^Pegasus-v[a-z]+$/);const text=readFileSync(e.modelPath,'utf8');assert.equal(createHash('sha256').update(text).digest('hex'),e.modelHash);validateImitationModel(JSON.parse(text));}
});
test('each fitted model makes deterministic affordable bids and legal word plays independently',()=>{
 for(const e of manifest.entries){const model=JSON.parse(readFileSync(e.modelPath,'utf8'))as ImitationModel;const policy=imitationPolicy(model);
  for(const balance of[0,1,10,100])for(const letter of'AEQXZ'){
   const v=view({balance,letter});const before=Array.from(v.rack),bid=policy.bid(v);assert.ok(Number.isInteger(bid)&&bid>=0&&bid<=balance);assert.equal(policy.bid(v),bid);assert.deepEqual(Array.from(v.rack),before);
   const word=policy.play(v);if(word){assert.ok(lexicon.has(word));const counts=new Uint8Array(v.rack);for(const c of word)assert.ok(counts[c.charCodeAt(0)-65]!-->0);}
  }
  assert.ok(policy.bid(view({firstPrice:true}))<=6);assert.equal(policy.bid(view({balance:0})),0);assert.ok(policy.play(view({rack:countsFromString('CAT'),auctionsLeft:0})));
 }
});
test('fleet cannot silently accept a renamed model or invalid coefficients',()=>{
 const model=JSON.parse(readFileSync(manifest.entries[0].modelPath,'utf8'))as ImitationModel;
 assert.throws(()=>validateImitationModel({...model,name:'../../token'}));
 assert.throws(()=>validateImitationModel({...model,bid:{...model.bid,scales:model.bid.scales.map(()=>0)}}));
});
