// Tune acquisition around Market7VF, retaining seven-letter planner play.
// Training is the earlier archive; validation is newer matches excluded from it.
import { readFileSync, writeFileSync } from 'node:fs';
import { Lexicon } from '../../src/lexicon.js';
import { conversion } from '../../src/strategies/conversion.js';
import { sampleStartingRacks, replayMatch, type ArchivedMatch } from '../../src/replay.js';
import { mulberry32 } from '../../src/sim.js';
import type { MarketParams } from '../../src/strategies/market.js';
const began=performance.now();
const old=JSON.parse(readFileSync('bench/results/viability/live-replay-input.json','utf8'));
const recent=JSON.parse(readFileSync('bench/results/viability/improvement-input.json','utf8'));
function decode(raw:any):ArchivedMatch {
 if(raw.state.auction_type[0]!==1)throw new Error('Non-Vickrey match');
 const tops=new Map(raw.tops.map((r:any)=>[Number(r.auction_id),Number(r.top_bid)]));
 const m:ArchivedMatch={id:Number(raw.state.id),createdAt:Number(raw.state.created_at[0]),startingRack:Number(raw.state.starting_rack_size),
 bots:raw.participants.map((p:any)=>Number(p.bot_id)),
 auctions:raw.auctions.map((a:any)=>({id:Number(a.auction_id),letter:String(a.letter),winner:a.winner_bot_id[0]===0?Number(a.winner_bot_id[1]):null,
 paid:Number(a.paid),top:tops.get(Number(a.auction_id)),time:Number(a.closed_at[0])})).sort((a:any,b:any)=>a.id-b.id),
 plays:raw.plays.map((p:any)=>({bot:Number(p.bot_id),word:String(p.word),reward:Number(p.total_reward),time:Number(p.played_at[0])}))};
 if(m.auctions.some(a=>a.top===undefined))throw new Error('Missing archived bid');
 for(const p of raw.participants){const score=m.plays.filter(w=>w.bot===Number(p.bot_id)).reduce((n,w)=>n+w.reward,0);
  const paid=m.auctions.filter(a=>a.winner===Number(p.bot_id)).reduce((n,a)=>n+a.paid,0);
  if(score!==Number(p.score)||100+score-paid!==Number(p.balance))throw new Error('Financial reconciliation failed');}
 sampleStartingRacks(m,m.id);return m;
}
const training:ArchivedMatch[]=old.matches.map(decode).sort((a,b)=>a.id-b.id);
const maxTraining=Math.max(...training.map(m=>m.id));
const validation:ArchivedMatch[]=recent.matches.filter((m:any)=>Number(m.state.id)>maxTraining).map(decode).sort((a:ArchivedMatch,b:ArchivedMatch)=>a.id-b.id);
if(validation.length<8)throw new Error(`Only ${validation.length} fresh validation matches`);
const lexicon=Lexicon.fromFile(new URL('../../../spacetimedb/wordlist.txt',import.meta.url));
type Config={market:Partial<MarketParams>;cashBidShare:number};
const configs:Config[]=[{market:{},cashBidShare:.6},
 {market:{paceK:16,pointsToBid:1.5},cashBidShare:.8},
 {market:{paceK:16,anchor1pt:.65,anchorMid:1.5,pointsToBid:2},cashBidShare:.8},
 {market:{paceK:20,anchor1pt:.65,anchorMid:1.5,pointsToBid:2},cashBidShare:.8},
 {market:{paceK:10,paceFaceBoost:1,anchor1pt:.65,anchorMid:1.5,pointsToBid:2},cashBidShare:.8},
 {market:{paceK:12,paceFaceBoost:1,anchor1pt:.65,anchorMid:1.5,pointsToBid:2},cashBidShare:.8},
 {market:{paceK:16,anchor:1.15,anchor1pt:.7,anchorMid:1.5,pointsToBid:1.5},cashBidShare:.8}];
const rng=mulberry32(97137), pick=<T>(xs:T[]):T=>xs[Math.floor(rng()*xs.length)]!;
while(configs.length<32)configs.push({market:{anchor:pick([.8,1,1.15]),anchor1pt:pick([.55,.7,.85]),anchorMid:pick([1.2,1.5,1.8]),anchorHigh:pick([.9,1.1,1.3]),
 paceK:pick([10,12,16,20]),paceFaceBoost:pick([.5,.75,1]),maxBidShare:pick([.6,.75]),pointsToBid:pick([.75,1.5,2.25]),duplicatePenalty:pick([.15,.25])},cashBidShare:pick([.6,.8])});
const scenarios=[{winTies:false,reserveRival:1 as const},{winTies:true,reserveRival:0 as const}];
function evaluate(config:Config,matches:ArchivedMatch[],deals:number){
 const perMatch=matches.map(m=>{
  const totals=scenarios.map(scenario=>{let score=0,tiles=0,won=0,starved=0;
   for(let d=0;d<deals;d++){
    const initial=sampleStartingRacks(m,m.id*1009+d).get(old.hero)!;
    const policy=conversion({cashInRegimes:0,cashBalance:12,cashMinLength:5,cashBidShare:config.cashBidShare},'FundingTune',config.market);
    const out=replayMatch(m,old.hero,initial,policy,lexicon,scenario);
    score+=out.score;tiles+=out.tilesPlayed;won+=out.tilesWon;starved+=out.starvedRounds;
   }
   return {score:score/deals,tilesPlayed:tiles/deals,tilesWon:won/deals,starvedRounds:starved/deals};
  });return{matchId:m.id,scenarios:totals};
 });
 const means=scenarios.map((_,i)=>perMatch.reduce((n,m)=>n+m.scenarios[i]!.score,0)/matches.length);
 return {means,robustScore:Math.min(...means),perMatch};
}
const train=configs.map((config,id)=>{const out=evaluate(config,training,2);console.log(JSON.stringify({phase:'train',id,means:out.means}));return{id,config,...out};});
const ranked=train.filter(r=>r.id!==0).sort((a,b)=>b.robustScore-a.robustScore).slice(0,3);
const validationRows=[train[0]!,...ranked].map(row=>{const out=evaluate(row.config,validation,8);console.log(JSON.stringify({phase:'validation',id:row.id,means:out.means}));return{id:row.id,config:row.config,...out};});
const baseline=validationRows[0]!;
for(const row of validationRows){
 (row as any).paired= scenarios.map((_,i)=>{
  const differences=row.perMatch.map((m,k)=>m.scenarios[i]!.score-baseline.perMatch[k]!.scenarios[i]!.score);
  const rand=mulberry32(19731),boot:number[]=[];
  for(let b=0;b<10000;b++){let sum=0;for(let k=0;k<differences.length;k++)sum+=differences[Math.floor(rand()*differences.length)]!;boot.push(sum/differences.length);}
  boot.sort((a,b)=>a-b);
  return{difference:differences.reduce((a,b)=>a+b,0)/differences.length,interval95:[boot[250],boot[9750]]};
 });
}
const result={trainingMatchIds:training.map(m=>m.id),validationMatchIds:validation.map(m=>m.id),trainingDeals:2,validationDeals:8,
 elapsedSeconds:(performance.now()-began)/1000,train,validation:validationRows,
 caveat:'Frozen-market replay with approximate private-rack samples. Validation histories were newer than every training history, but were used to compare three finalists. No causal live performance or 100-point average is established.'};
writeFileSync('bench/results/viability/funding-tune.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({elapsedSeconds:result.elapsedSeconds,training:training.length,validation:validation.length,finalists:validationRows.map(r=>({id:r.id,means:r.means,config:r.config,paired:(r as any).paired}))}));
