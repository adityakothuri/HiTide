import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BAG_COUNTS, Lexicon } from './lexicon.js';
import { sampleStartingRacks, replayMatch, rivalMaximum, type ArchivedMatch } from './replay.js';
function fixture(): ArchivedMatch {
  const letters: string[]=[];
  BAG_COUNTS.forEach((n,s)=>{for(let j=0;j<n-(s===0?2:0);j++)letters.push(String.fromCharCode(65+s));});
  letters.splice(letters.indexOf('A'),1); letters.push('A');
  return { id:1, createdAt:0, startingRack:1, bots:[1,2], plays:[],
    auctions:letters.map((letter,i)=>({id:i+1,letter,winner:2,paid:1,top:2,time:i+1})) };
}
test('archived bids identify rival maximum with explicit reserve ambiguity',()=>{
  const a=fixture().auctions[0]!;
  assert.equal(rivalMaximum({...a,winner:1,paid:5,top:9},1,1),5);
  assert.equal(rivalMaximum({...a,winner:2,paid:5,top:9},1,1),9);
  assert.equal(rivalMaximum({...a,winner:1,paid:1},1,0),0);
  assert.equal(rivalMaximum({...a,winner:1,paid:1},1,1),1);
});
test('starting rack sampler conserves complete tile pool and rejects impossible histories',()=>{
  const m=fixture(), racks=sampleStartingRacks(m,7);
  assert.equal(racks.get(1)![0],1); assert.equal(racks.get(2)![0],1);
  assert.throws(()=>sampleStartingRacks({...m,auctions:m.auctions.slice(1)},7),/incomplete/);
  assert.throws(()=>sampleStartingRacks({...m,plays:[{bot:1,word:'AA',reward:2,time:0}]},7),/inconsistent/);
});
test('replay refills score and cash but cannot play a tile awarded at final close',()=>{
  const m=fixture(), initial=sampleStartingRacks(m,7).get(1)!, lex=new Lexicon(['AA']);
  const late={ name:'Late', bid:(v:{auctionsLeft:number})=>v.auctionsLeft===0?3:0,
    play:(v:{rack:Uint8Array})=>v.rack[0]!>=2?'AA':null };
  const result=replayMatch(m,1,initial,late,lex,{winTies:false,reserveRival:1});
  assert.equal(result.score,0);assert.equal(result.tilesWon,1);assert.equal(result.balance,98);assert.equal(result.tilesLeft,2);
  const early={...late,bid:(v:{auctionsLeft:number})=>v.auctionsLeft===95?3:0};
  const cash=replayMatch(m,1,initial,early,lex,{winTies:false,reserveRival:1});
  assert.equal(cash.score,2);assert.equal(cash.balance,100);assert.equal(cash.tilesPlayed,2);
});
test('tie sensitivity uses identical markets and changes only equal-bid allocation',()=>{
  const m=fixture(), initial=sampleStartingRacks(m,7).get(1)!, lex=new Lexicon(['AA']);
  const p={name:'Tie',bid:(v:{auctionsLeft:number})=>v.auctionsLeft===0?2:0,play:()=>null};
  assert.equal(replayMatch(m,1,initial,p,lex,{winTies:false,reserveRival:1}).tilesWon,0);
  assert.equal(replayMatch(m,1,initial,p,lex,{winTies:true,reserveRival:1}).tilesWon,1);
});

test('conditional rack sampling avoids a fixed-minimum allocation bias',()=>{
  const letters:string[]=[];
  BAG_COUNTS.forEach((n,s)=>{for(let j=0;j<n-(s===0?3:s===1?1:0);j++)letters.push(String.fromCharCode(65+s));});
  const m:ArchivedMatch={id:3,createdAt:0,startingRack:2,bots:[1,2],
    auctions:letters.map((letter,i)=>({id:i+1,letter,winner:i===0?1:2,paid:1,top:2,time:i+1})),
    plays:[{bot:1,word:'AA',reward:2,time:1}]};
  // Initial pool AAAB, conditioned on player 1 having at least one A:
  // AA and AB are equally likely in a random labeled deal.
  let aa=0;
  for(let seed=0;seed<200;seed++) if(sampleStartingRacks(m,seed).get(1)![0]===2) aa++;
  assert.ok(aa>70 && aa<130,`AA frequency ${aa}/200`);
});
