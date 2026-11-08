// Offline use of the read-only archive fetched by fetch-replay.mts.
import { readFileSync, writeFileSync } from 'node:fs';
import { Lexicon } from '../../src/lexicon.js';
import { CHOICES } from '../../src/strategy.js';
import { sampleStartingRacks, replayMatch, type ArchivedMatch } from '../../src/replay.js';
import { mulberry32 } from '../../src/sim.js';
const started = performance.now();
const input = JSON.parse(readFileSync(process.env.REPLAY_IN ?? 'bench/results/viability/live-replay-input.json','utf8'));
const samples = Number(process.env.REPLAY_DEALS ?? 8);
const strategies = (process.env.REPLAY_STRATEGIES ?? 'market7v,market7vf,market7vb,market7vc,portfolioTuned').split(',');
if (!Number.isInteger(samples) || samples<1 || strategies.some(s=>!CHOICES[s])) throw new Error('Invalid replay configuration');
const lexicon = Lexicon.fromFile(new URL('../../../spacetimedb/wordlist.txt',import.meta.url));
const opt = (v:any):number|null => Array.isArray(v) && v[0]===0 ? Number(v[1]) : null;
const timestamp = (v:any):number => Number(Array.isArray(v) ? v[0] : v);
const matches: ArchivedMatch[] = [], skipped: {id:number;reason:string}[] = [];
for (const raw of input.matches) {
  if (Number(raw.state.id) <= Number(process.env.REPLAY_AFTER ?? 0)) continue;
  try {
    if (raw.state.auction_type[0]!==1) throw new Error('Only Vickrey rival bids are identifiable');
    const tops = new Map(raw.tops.map((a:any)=>[Number(a.auction_id),Number(a.top_bid)]));
    const auctions = raw.auctions.map((a:any)=>({id:Number(a.auction_id),letter:String(a.letter),winner:opt(a.winner_bot_id),
      paid:Number(a.paid),top:tops.get(Number(a.auction_id)),time:timestamp(a.closed_at)})).sort((a:any,b:any)=>a.id-b.id);
    if (auctions.some((a:any)=>a.top===undefined)) throw new Error('Missing archived winning bid');
    const m: ArchivedMatch = {id:Number(raw.state.id), createdAt:timestamp(raw.state.created_at),startingRack:Number(raw.state.starting_rack_size),
      bots:raw.participants.map((p:any)=>Number(p.bot_id)), auctions,
      plays:raw.plays.map((p:any)=>({bot:Number(p.bot_id),word:String(p.word),reward:Number(p.total_reward),time:timestamp(p.played_at)}))};
    // Validate the archive against actual final accounts before replaying it.
    for (const participant of raw.participants) {
      const bot=Number(participant.bot_id);
      const rewards=m.plays.filter(p=>p.bot===bot).reduce((sum,p)=>sum+p.reward,0);
      const paid=m.auctions.filter(a=>a.winner===bot).reduce((sum,a)=>sum+a.paid,0);
      if (rewards!==Number(participant.score) || 100+rewards-paid!==Number(participant.balance))
        throw new Error('Archived plays/payments do not reproduce final accounts');
    }
    sampleStartingRacks(m,m.id); matches.push(m);
  } catch(e) { skipped.push({id:Number(raw.state.id),reason:String(e)}); }
}
if (matches.length<2) throw new Error(`Too few usable matches: ${JSON.stringify(skipped)}`);
const metricNames = ['score','tilesWon','spent','starvedRounds','tilesLeft','pointsPerPlayedTile'] as const;
const all: any[] = [];
for (const scenario of [{name:'ties-lose/reserve-1',winTies:false,reserveRival:1 as const}, {name:'ties-win/reserve-0',winTies:true,reserveRival:0 as const}]) {
  const byMatch: any[] = [];
  for (const m of matches) {
    const runs: any[] = [];
    for (let sample=0;sample<samples;sample++) {
      const initial=sampleStartingRacks(m,m.id*1009+sample).get(input.hero)!;
      for (const strategy of strategies) runs.push({strategy,...replayMatch(m,input.hero,initial,CHOICES[strategy]!(),lexicon,scenario)});
    }
    const row:any={matchId:m.id};
    for (const strategy of strategies) {
      const selected=runs.filter(r=>r.strategy===strategy);
      row[strategy]=Object.fromEntries(metricNames.map(k=>[k,selected.reduce((n,r)=>n+r[k],0)/samples]));
    }
    byMatch.push(row);
  }
  const summaries = strategies.map(strategy=>({strategy,...Object.fromEntries(metricNames.map(k=>[k,byMatch.reduce((n,r)=>n+r[strategy][k],0)/byMatch.length]))}));
  const baseline=strategies[0]!;
  const comparisons=strategies.slice(1).map(strategy=>{
    const differences=byMatch.map(r=>r[strategy].score-r[baseline].score);
    const rng=mulberry32(17713),boot:number[]=[];
    for(let b=0;b<10000;b++){let sum=0;for(let i=0;i<differences.length;i++)sum+=differences[Math.floor(rng()*differences.length)]!;boot.push(sum/differences.length);}
    boot.sort((a,b)=>a-b);
    return {strategy,scoreDifference:differences.reduce((a,b)=>a+b,0)/differences.length,
      matchClusterBootstrap95:[boot[250],boot[9750]]};
  });
  all.push({scenario:scenario.name,summaries,comparisons,byMatch});
  console.log(JSON.stringify(all.at(-1)));
}
const result={hero:input.hero,archiveMatches:matches.length,skipped,dealsPerMatch:samples,strategies,
  elapsedSeconds:(performance.now()-started)/1000,
  caveats:['Frozen rival bids and public income: rivals cannot react to changed tile allocation.',
    'Private starting racks are sampled subject to public prefix constraints, not observed or an exact posterior.',
    'Tie/reserve cases are sensitivity scenarios, not rigorous score bounds.',
    'Intervals resample matches after averaging rack samples; they quantify archive variability, not causal live superiority.',
    'No network latency or end-to-end event processing is modeled. No live win rate is inferred.'],scenarios:all};
writeFileSync(process.env.REPLAY_OUT ?? 'bench/results/viability/live-replay-results.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({...result,scenarios:undefined}));
