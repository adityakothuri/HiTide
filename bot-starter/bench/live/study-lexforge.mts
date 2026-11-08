import { readFileSync, writeFileSync } from 'node:fs';
import { Lexicon, countsFromString, totalOf, slotOf, BAG_COUNTS } from '../../src/lexicon.js';
import { sampleStartingRacks, type ArchivedMatch } from '../../src/replay.js';
const target=Number(process.env.STUDY_BOT ?? 224);
const data=JSON.parse(readFileSync(process.env.STUDY_IN ?? 'bench/results/viability/lexforge-base-input.json','utf8'));
if(data.hero !== target)throw new Error('Study bot does not match input archive');
const lex=Lexicon.fromFile(new URL('../../../spacetimedb/wordlist.txt',import.meta.url));
const bids:any[]=[], plays:any[]=[], matches:any[]=[];
for(const raw of data.matches){
 const tops=new Map(raw.tops.map((r:any)=>[Number(r.auction_id),Number(r.top_bid)]));
 const m:ArchivedMatch={id:Number(raw.state.id),createdAt:Number(raw.state.created_at[0]),startingRack:Number(raw.state.starting_rack_size),bots:raw.participants.map((p:any)=>Number(p.bot_id)),
 auctions:raw.auctions.map((a:any)=>({id:Number(a.auction_id),letter:String(a.letter),winner:a.winner_bot_id[0]===0?Number(a.winner_bot_id[1]):null,paid:Number(a.paid),top:Number(tops.get(Number(a.auction_id))),time:Number(a.closed_at[0])})).sort((a:any,b:any)=>a.id-b.id),
 plays:raw.plays.map((p:any)=>({bot:Number(p.bot_id),word:String(p.word),reward:Number(p.total_reward),time:Number(p.played_at[0])}))};
 const rack=sampleStartingRacks(m,m.id).get(target)!, initial=new Uint8Array(rack), drawn=new Uint8Array(26), own=m.plays.filter(p=>p.bot===target).sort((a,b)=>a.time-b.time);
 let balance=100,score=0,nextPlay=0,won=0,paid=0;
 function applyPlay(p:typeof own[number],round:number){
  const best=lex.best(rack,2),six=lex.best(rack,6),seven=lex.best(rack,7);
  let valid=true;const before=Array.from(rack);
  for(const c of p.word){if(!rack[slotOf(c)])valid=false;else rack[slotOf(c)]!--;}
  plays.push({match:m.id,round,left:m.auctions.length-round-1,word:p.word,reward:p.reward,balance,rack:before,size:before.reduce((a,b)=>a+b,0),
   best:best>=0?lex.words[best]:null,bestScore:best>=0?lex.reward[best]:0,best6:six>=0?lex.words[six]:null,best7:seven>=0?lex.words[seven]:null,valid});
  balance+=p.reward;score+=p.reward;
 }
 for(let round=0;round<m.auctions.length;round++){
  const a=m.auctions[round]!;
  while(nextPlay<own.length&&own[nextPlay]!.time<=a.time)applyPlay(own[nextPlay++]!,round);
  drawn[slotOf(a.letter)]!++;
  const unseen=Array.from(BAG_COUNTS,(n,s)=>Math.max(0,n-drawn[s]!-initial[s]!));
  const before=new Uint8Array(rack),plus=new Uint8Array(rack);plus[slotOf(a.letter)]!++;
  const b=lex.best(before,2),c=lex.best(plus,2),b6=lex.best(before,6),c6=lex.best(plus,6);
  bids.push({match:m.id,round,left:m.auctions.length-round-1,letter:a.letter,balance,score,rack:Array.from(before),unseen,
   won:a.winner===target,top:a.top,paid:a.paid,best:b>=0?lex.reward[b]:0,after:c>=0?lex.reward[c]:0,
   best6:b6>=0?lex.reward[b6]:0,after6:c6>=0?lex.reward[c6]:0});
  if(a.winner===target){rack[slotOf(a.letter)]!++;balance-=a.paid;won++;paid+=a.paid;}
 }
 while(nextPlay<own.length)applyPlay(own[nextPlay++]!,m.auctions.length-1);
 const me=raw.participants.find((p:any)=>Number(p.bot_id)===target);
 const place=1+raw.participants.filter((p:any)=>Number(p.score)>Number(me.score)).length;
 matches.push({id:m.id,score:Number(me.score),balance:Number(me.balance),place,won,paid,
  reconciles:balance===Number(me.balance)&&score===Number(me.score),table:raw.participants.map((p:any)=>({bot:Number(p.bot_id),score:Number(p.score)}))});
}
writeFileSync(process.env.STUDY_OUT ?? 'bench/results/viability/lexforge-observations.json',JSON.stringify({bids,plays,matches},null,2)+'\n');
console.log(JSON.stringify({matches:matches.length,allAccountsReconcile:matches.every(m=>m.reconciles),
 invalidRack:plays.filter(p=>!p.valid).length,scoreBest:plays.filter(p=>p.reward===p.bestScore).length,totalPlays:plays.length,
 earlyPlays:plays.filter(p=>p.left>8).map(p=>({left:p.left,word:p.word,reward:p.reward,balance:p.balance,size:p.size,best:p.best,bestScore:p.bestScore}))}));
