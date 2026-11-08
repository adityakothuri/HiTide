// Reproducible descriptive profile; does not change the playing bot.
import {readFileSync,writeFileSync} from 'node:fs';
const raw=JSON.parse(readFileSync('bench/results/viability/bron-input.json','utf8'));
const obs=JSON.parse(readFileSync('bench/results/viability/bron-observations.json','utf8'));
const names=new Map(JSON.parse(readFileSync('bench/results/viability/bron-bot-names.json','utf8')).map((b:any)=>[Number(b.id),String(b.name)]));
const target=114,face=[1,3,3,2,1,4,2,4,1,8,5,1,3,1,1,3,10,1,1,1,1,4,4,8,4,10];
const mean=(a:number[])=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
const q=(a:number[],p:number)=>{if(!a.length)return null;const b=[...a].sort((x,y)=>x-y);return b[Math.floor((b.length-1)*p)]!;};
const ci=(a:number[])=>{const m=mean(a)!;const se=Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/(a.length-1)/a.length);return[m-1.96*se,m+1.96*se];};
const stamp=(x:any)=>Number(Array.isArray(x)?x[0]:x),own=(a:any)=>Array.isArray(a.winner_bot_id)&&a.winner_bot_id[0]===0&&Number(a.winner_bot_id[1])===target;
const matches=obs.matches.sort((a:any,b:any)=>b.id-a.id),words=obs.plays,wins:any[]=[],opps=new Map<number,any[]>();
let outright=0,tiedFirst=0,winCredit=0;const gaps:any[]=[],timing:any[]=[],initialKnowledge:any[]=[];
for(const m of raw.matches){
 const id=Number(m.state.id),me=m.participants.find((p:any)=>Number(p.bot_id)===target);
 const ahead=m.participants.filter((p:any)=>Number(p.score)>Number(me.score)).length,tied=m.participants.filter((p:any)=>Number(p.score)===Number(me.score)).length;
 if(!ahead){if(tied===1)outright++;else tiedFirst++;winCredit+=1/tied;}
 for(const p of m.participants){if(Number(p.bot_id)===target)continue;const rows=opps.get(Number(p.bot_id))??[];rows.push({matchId:id,ours:Number(me.score),theirs:Number(p.score)});opps.set(Number(p.bot_id),rows);}
 const auctions=[...m.auctions].sort((a:any,b:any)=>Number(a.auction_id)-Number(b.auction_id));
 const tops=new Map(m.tops.map((r:any)=>[Number(r.auction_id),Number(r.top_bid)]));
 auctions.forEach((a:any,i:number)=>{if(own(a))wins.push({matchId:id,letter:a.letter,face:face[String(a.letter).charCodeAt(0)-65],paid:Number(a.paid),top:tops.has(Number(a.auction_id))?Number(tops.get(Number(a.auction_id))):null,phase:i===auctions.length-1?'final':i<23?'early':i<46?'middle':'late',firstPrice:m.state.auction_type[0]!==1});});
 for(const p of m.plays.filter((p:any)=>Number(p.bot_id)===target)){
  const previous=auctions.filter((a:any)=>own(a)&&stamp(a.closed_at)<=stamp(p.played_at)).at(-1);
  if(previous)timing.push((stamp(p.played_at)-stamp(previous.closed_at))/1000);
 }
 const events=[...auctions.filter(own).map((a:any)=>({time:stamp(a.closed_at),order:0,letters:String(a.letter),sign:1})),...m.plays.filter((p:any)=>Number(p.bot_id)===target).map((p:any)=>({time:stamp(p.played_at),order:1,letters:String(p.word),sign:-1}))].sort((a,b)=>a.time-b.time||a.order-b.order);
 const held=Array(26).fill(0),lower=Array(26).fill(0);
 for(const e of events)for(const c of e.letters){const s=c.charCodeAt(0)-65;held[s]+=e.sign;lower[s]=Math.max(lower[s],-held[s]);}
 initialKnowledge.push({matchId:id,forcedStartingTiles:lower.reduce((a,b)=>a+b,0)});
}
const byLetter=Array.from({length:26},(_,s)=>{const letter=String.fromCharCode(65+s),rows=wins.filter(w=>w.letter===letter&&w.phase!=='final'),b=rows.flatMap(w=>w.top===null?[]:[w.top]);
 return{letter,wins:rows.length,meanWinningBid:mean(b),bidP25:q(b,.25),bidP50:q(b,.5),bidP75:q(b,.75),meanPaid:mean(rows.map(w=>w.paid))};});
const byPhase=['early','middle','late','final'].map(phase=>{const rows=wins.filter(w=>w.phase===phase);return{phase,wins:rows.length,tilesPerMatch:rows.length/matches.length,meanWinningBid:mean(rows.flatMap(w=>w.top===null?[]:[w.top])),meanPaid:mean(rows.map(w=>w.paid))};});
const groups=[{name:'vowels',test:(w:any)=>'AEIOU'.includes(w.letter)},{name:'1-point consonants',test:(w:any)=>w.face===1&&!'AEIOU'.includes(w.letter)},{name:'2–5 point letters',test:(w:any)=>w.face>=2&&w.face<=5},{name:'8–10 point letters',test:(w:any)=>w.face>=8}].map(g=>{const rows=wins.filter(w=>w.phase!=='final'&&g.test(w));return{name:g.name,wins:rows.length,tilesPerMatch:rows.length/matches.length,meanWinningBid:mean(rows.flatMap(w=>w.top===null?[]:[w.top])),meanPaid:mean(rows.map(w=>w.paid))};});
const matchups=[...opps].map(([id,rows])=>({botId:id,name:names.get(id)??String(id),met:rows.length,meanBronScore:mean(rows.map(r=>r.ours)),meanOpponentScore:mean(rows.map(r=>r.theirs)),above:rows.filter(r=>r.ours>r.theirs).length,tied:rows.filter(r=>r.ours===r.theirs).length,rows})).sort((a,b)=>b.met-a.met);
const early=words.filter((p:any)=>p.left>5),shortEarly=early.filter((p:any)=>p.word.length<7),scores=matches.map((m:any)=>m.score);
const sortedRaw=[...raw.matches].sort((a:any,b:any)=>stamp(a.state.created_at)-stamp(b.state.created_at));
for(let i=1;i<sortedRaw.length;i++){const seconds=(stamp(sortedRaw[i].state.created_at)-stamp(sortedRaw[i-1].state.created_at))/1e6;if(seconds>600)gaps.push({before:sortedRaw[i-1].state.id,after:sortedRaw[i].state.id,seconds});}
const result={generatedAt:new Date().toISOString(),botId:target,name:'Bron',sourceMatches:matches.length,matchIds:matches.map((m:any)=>m.id),
 window:{start:new Date(stamp(sortedRaw[0].state.created_at)/1000).toISOString(),end:new Date(stamp(sortedRaw.at(-1).state.created_at)/1000).toISOString(),gaps},
 performance:{meanScore:mean(scores),score95NormalCI:ci(scores),medianScore:q(scores,.5),minScore:Math.min(...scores),maxScore:Math.max(...scores),latest10MeanScore:mean(scores.slice(0,10)),previous90MeanScore:mean(scores.slice(10)),meanPlace:mean(matches.map((m:any)=>m.place)),outright,tiedFirst,winShare:winCredit/matches.length,tilesWonPerMatch:mean(matches.map((m:any)=>m.won)),spendPerMatch:mean(matches.map((m:any)=>m.paid)),endingBalance:mean(matches.map((m:any)=>m.balance))},
 words:{count:words.length,lengths:Object.fromEntries(Array.from(new Set<number>(words.map((w:any)=>w.word.length))).sort((a,b)=>a-b).map(l=>[l,words.filter((w:any)=>w.word.length===l).length])),pointsPerPlayedTile:words.reduce((n:number,w:any)=>n+w.reward,0)/words.reduce((n:number,w:any)=>n+w.word.length,0),bestAvailableRewardMatches:words.filter((w:any)=>w.reward===w.bestScore).length,
 earlyCount:early.length,earlyShort:shortEarly,healthyWeakSevenPlus:early.filter((w:any)=>w.word.length>=7&&w.reward<35&&w.balance>=15),smallDumpRemaining:Object.fromEntries(Array.from(new Set<number>(words.filter((w:any)=>w.word.length<5).map((w:any)=>w.left))).map(left=>[left,words.filter((w:any)=>w.word.length<5&&w.left===left).length])),reactionFromPreviousOwnWinMs:{median:q(timing,.5),p90:q(timing,.9)}},
 initialKnowledge,byLetter,byPhase,groups,matchups,matches,
 caveats:['Descriptive observational profile, not original strategy source.','Winning bids are selection-biased. Losing bids remain unknown; Vickrey paid prices are not bids.','Initial racks are reconstructed only when forced by public consumption; otherwise feasible allocations are sampled.','No version reset is recorded for Bron, but unannounced code changes remain possible. Opponent fields and time confound comparisons.','The latest 10 are a subset of the 100, not an independent A/B test. Timing reflects network/server/word opportunity, not a pure reaction benchmark.']};
writeFileSync('bench/results/viability/bron-profile.json',JSON.stringify(result,null,2)+'\n');
const f=(x:number|null)=>x===null?'—':x.toFixed(2),N=matches.length;
const lex=JSON.parse(readFileSync('bench/results/viability/lexforge-observations.json','utf8'));
const lexScore=mean(lex.matches.map((m:any)=>m.score)),lexTiles=lex.plays.reduce((n:number,w:any)=>n+w.word.length,0);
const text=[`# Bron public-match profile`, ``, `Bot **Bron (114)**. Latest **${N} completed matches**, IDs ${Math.min(...result.matchIds)}–${Math.max(...result.matchIds)}, ${result.window.start} to ${result.window.end}. No bot-version reset rows were found. The profile describes observed behavior, not recovered source code.`, ``,
 `## Performance`, ``, `- Mean score **${f(result.performance.meanScore)}**, descriptive 95% normal interval [${result.performance.score95NormalCI.map(f).join(', ')}]; median ${f(result.performance.medianScore)}, range ${result.performance.minScore}–${result.performance.maxScore}.`,
 `- Latest 10 mean **${f(result.performance.latest10MeanScore)}**; previous 90 mean **${f(result.performance.previous90MeanScore)}**. Small recent samples and different opponents limit inference.`,
 `- Mean place **${f(result.performance.meanPlace)}**; ${outright} outright wins, ${tiedFirst} tied firsts; tie-split win share ${(100*result.performance.winShare).toFixed(1)}%.`,
 `- Mean auction tiles won **${f(result.performance.tilesWonPerMatch)}**, spend **${f(result.performance.spendPerMatch)}**, ending coins **${f(result.performance.endingBalance)}**.`,
 `- Pooled points per played tile **${f(result.words.pointsPerPlayedTile)}**, including the free starting rack.`, ``,
 `## Word timing and selection`, ``,
 `${words.length} observed word plays. Length histogram: ${JSON.stringify(result.words.lengths)}. ${result.words.bestAvailableRewardMatches}/${words.length} match the best available immediate reward in reconstructed racks. ${initialKnowledge.filter(x=>x.forcedStartingTiles===5).length}/${N} starting racks have all five letters forced by public prefix constraints; other rack states use feasible samples.`, ``,
 `Bron frequently plays seven-letter words well below 45 points, including healthy-cash plays such as GREENIE (24, 82 coins), DAILIES (24, 86), and ARTIEST (21, 42). LexForge-Base-v1's 45-point primary gate therefore does **not** describe Bron. Bron also plays 8/9-letter words; there is no universal seven-letter maximum in this sample.`, ``,
 `Only ${shortEarly.length} plays shorter than seven letters occurred with more than five future tiles: ${shortEarly.filter((p:any)=>p.balance<=10).length} had at most 10 coins, while DOUMA (16 points, 37 coins, 26 left) and ZOOTY (34, 41 coins, 22 left) are counterexamples to a simple low-cash-only rule. A dynamic future-word valuation or other state-dependent rule is plausible, but public evidence does not identify it uniquely.`, ``,
 `All ${words.filter((p:any)=>p.word.length<5).length} two-to-four-letter plays occurred with zero tiles behind the open auction. This differs from LexForge-Base-v1, whose small dumps usually occurred one auction earlier. Median elapsed time from the previous tile Bron won to a word play is ${f(result.words.reactionFromPreviousOwnWinMs.median)} ms (90th percentile ${f(result.words.reactionFromPreviousOwnWinMs.p90)} ms); these times mix opportunity, batching and latency.`, ``,
 `## Acquisition and budget pacing`, ``, `Last-auction wins are separated because an external client cannot play that tile and all-in bids distort normal price statistics.`, ``,
 `| Phase (auction indices) | Wins | Tiles/match | Mean winning bid | Mean paid |`, `|---|---:|---:|---:|---:|`,
 ...byPhase.map(p=>`| ${p.phase} | ${p.wins} | ${f(p.tilesPerMatch)} | ${f(p.meanWinningBid)} | ${f(p.meanPaid)} |`), ``,
 `| Tile group (excluding final auction) | Wins | Tiles/match | Mean winning bid | Mean paid |`, `|---|---:|---:|---:|---:|`,
 ...groups.map(g=>`| ${g.name} | ${g.wins} | ${f(g.tilesPerMatch)} | ${f(g.meanWinningBid)} | ${f(g.meanPaid)} |`), ``,
 `## Per-letter winning bids`, ``, `These describe tiles Bron **won**, not its unconditional bidding policy. Missing archives stay missing; paid is not substituted for a bid. Last auctions are excluded.`, ``,
 `| Letter | Wins | Bid P25 | Median bid | Bid P75 | Mean paid |`,`|---|---:|---:|---:|---:|---:|`,
 ...byLetter.map(b=>`| ${b.letter} | ${b.wins} | ${f(b.bidP25)} | ${f(b.bidP50)} | ${f(b.bidP75)} | ${f(b.meanPaid)} |`), ``,
 `## Actual shared matchups`, ``, `“Above” means a strictly higher score, with ties separate. Comparisons are paired within the same table; bots appear different numbers of times.`, ``,
 `| Opponent | Met | Bron mean | Opponent mean | Bron above | Tied |`, `|---|---:|---:|---:|---:|---:|`,
 ...matchups.filter(p=>p.met>=3||[208,224,18,171].includes(p.botId)).map(p=>`| ${p.name.replaceAll('|','/')} (${p.botId}) | ${p.met} | ${f(p.meanBronScore)} | ${f(p.meanOpponentScore)} | ${p.above}/${p.met} | ${p.tied} |`), ``,
 `## Comparison with the LexForge study`, ``, `Bron's sampled overall mean is ${f(result.performance.meanScore)} vs LexForge-Base-v1's earlier 34-match ${f(lexScore)}. Bron's pooled conversion is ${f(result.words.pointsPerPlayedTile)} vs ${f(lex.plays.reduce((n:number,w:any)=>n+w.reward,0)/lexTiles)}. These are **different match sets and periods**, so this is not a controlled ranking. Bron's latest-10 mean of ${f(result.performance.latest10MeanScore)} is closer to the 100-point goal than its full-window mean. The shared-table section is the appropriate direct evidence where overlap exists.`, ``,
 `Actionable research candidates: compare Bron's earlier/cheaper seven-letter cash-ins against the LexForge 45-point gate, and compare final-only small-word liquidation against the one-auction buffer. Neither change is adopted automatically. The playing bot is unchanged.`, ``,
 `## Evidence and reproduction`, ``, '```sh',
 `REPLAY_INPUT_OUT=bench/results/viability/bron-input.json node --import tsx bench/live/fetch-replay.mts 100 114`,
 `STUDY_BOT=114 STUDY_IN=bench/results/viability/bron-input.json STUDY_OUT=bench/results/viability/bron-observations.json node --import tsx bench/live/study-lexforge.mts`,
 `node --import tsx bench/live/profile-bron.mts`, '```', ``, `Pinned input, reconstructed observations and structured profile are under \`bench/results/viability/bron-*.json\`. Refetching changes the sample. No source-code or exact losing-bid recovery is claimed.`, ``];
writeFileSync('bench/BRON.md',text.join('\n'));
console.log(JSON.stringify({performance:result.performance,words:{count:words.length,lengths:result.words.lengths,pointsPerPlayedTile:result.words.pointsPerPlayedTile},phases:byPhase,sharedWithUs:matchups.find(p=>p.botId===208),sharedWithLexForge:matchups.find(p=>p.botId===224)}));
