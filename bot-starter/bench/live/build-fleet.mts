// Freeze the current top ten and fit one independent behavioral model per bot.
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {gzipSync} from 'node:zlib';
import {createHash} from 'node:crypto';
import {Lexicon,maskOf,totalOf,BAG_COUNTS} from '../../src/lexicon.js';
import {sampleStartingRacks,type ArchivedMatch} from '../../src/replay.js';
import {lexforgeFeatures} from '../../src/strategies/lexforgeFeatures.js';
import {chooseImitationWord,validateImitationModel,type ImitationStyle,type ImitationModel} from '../../src/fleetPolicy.js';
import type{MatchView}from'../../src/policy.js';
const began=performance.now();mkdirSync('fleet/models',{recursive:true});mkdirSync('fleet/work',{recursive:true});
const source=JSON.parse(readFileSync('bench/results/scouting/profiles.json','utf8'));
const cache=JSON.parse(readFileSync('bench/results/scouting/matches.json','utf8'));
const profiles=source.profiles.slice(0,10);if(profiles.length!==10)throw Error('Need ten source profiles');
if(existsSync('fleet/manifest.json'))throw Error('Fleet manifest already exists; immutable iterations require a fresh batch');
const lexicon=Lexicon.fromFile(new URL('../../../spacetimedb/wordlist.txt',import.meta.url));
const wanted=Object.fromEntries([...new Set<number>(profiles.flatMap((p:any)=>p.matchIds))].map(id=>[id,cache.matches[id]]));
if(Object.values(wanted).some(v=>!v))throw Error('Scout cache is missing a pinned match');
writeFileSync('fleet/source-matches.json.gz',gzipSync(JSON.stringify({source:cache.source,matches:wanted})),{mode:0o644});
writeFileSync('fleet/source-profiles.json',JSON.stringify({generatedAt:source.generatedAt,profiles},null,2)+'\n');
const snapshotHash=createHash('sha256').update(readFileSync('fleet/source-matches.json.gz')).digest('hex');
const entries:any[]=[];
function decode(raw:any):ArchivedMatch{
 const tops=new Map(raw.tops.map((t:any)=>[Number(t.auction_id),Number(t.top_bid)]));
 const count=raw.participants.length,derived=(98-raw.auctions.length)/count;
 const starting=Number.isInteger(derived)&&derived>=0?derived:Number(raw.state.starting_rack_size);
 const m:ArchivedMatch={id:Number(raw.state.id),createdAt:Number(raw.state.created_at[0]),startingRack:starting,bots:raw.participants.map((p:any)=>Number(p.bot_id)),
 auctions:raw.auctions.map((a:any)=>({id:Number(a.auction_id),letter:String(a.letter),winner:a.winner_bot_id[0]===0?Number(a.winner_bot_id[1]):null,paid:Number(a.paid),top:Number(tops.get(Number(a.auction_id))),time:Number(a.closed_at[0])})).sort((a:any,b:any)=>a.id-b.id),
 plays:raw.plays.map((p:any)=>({bot:Number(p.bot_id),word:String(p.word),reward:Number(p.total_reward),time:Number(p.played_at[0])}))};
 if(m.auctions.some(a=>!Number.isFinite(a.top)))throw Error('Missing archived bid');
 return m;
}
function observations(profile:any){
 const bidRows:any[]=[],wordRows:any[]=[],skipped:any[]=[];
 for(const id of [...profile.matchIds].sort((a,b)=>a-b)){
  const raw=wanted[id];try{
   const m=decode(raw),rack=sampleStartingRacks(m,m.id).get(profile.botId)!,initial=new Uint8Array(rack),drawn=new Uint8Array(26);
   const own=m.plays.filter(p=>p.bot===profile.botId).sort((a,b)=>a.time-b.time);let balance=100,score=0,index=0;
   for(let round=0;round<m.auctions.length;round++){
    const a=m.auctions[round]!;
    while(index<own.length&&own[index]!.time<=a.time){
     const p=own[index++]!;wordRows.push({match:id,rack:new Uint8Array(rack),balance,left:m.auctions.length-round-1,reward:p.reward,word:p.word});
     for(const c of p.word){const s=c.charCodeAt(0)-65;if(!rack[s])throw Error('Impossible word consumption');rack[s]!--;}
     balance+=p.reward;score+=p.reward;
    }
    drawn[a.letter.charCodeAt(0)-65]!++;
    const unseen=Uint8Array.from(BAG_COUNTS,(n,s)=>Math.max(0,n-drawn[s]!-initial[s]!));
    bidRows.push({match:id,rack:new Uint8Array(rack),balance,score,left:m.auctions.length-round-1,letter:a.letter,unseen,won:a.winner===profile.botId,top:a.top});
    if(a.winner===profile.botId){rack[a.letter.charCodeAt(0)-65]!++;balance-=a.paid;}
   }
   const me=raw.participants.find((p:any)=>Number(p.bot_id)===profile.botId);
   if(balance!==Number(me.balance)||score!==Number(me.score))throw Error('Final account mismatch');
  }catch(e){skipped.push({match:id,reason:String(e)});}
 }
 const bad=new Set(skipped.map(s=>s.match));return{bids:bidRows.filter(r=>!bad.has(r.match)),words:wordRows.filter(r=>!bad.has(r.match)),skipped};
}
const scoreCache=new Map<string,number[]>();
function scores(rack:Uint8Array){const key=Array.from(rack).join(',');let values=scoreCache.get(key);if(values)return values;
 values=Array(10).fill(0);const mask=maskOf(rack);
 for(let i=lexicon.startAt(totalOf(rack));i<lexicon.words.length;i++){
  if((lexicon.mask[i]!&~mask)!==0||!lexicon.spells(i,rack))continue;
  for(let len=2;len<=Math.min(9,lexicon.length[i]!);len++)values[len]=Math.max(values[len]!,lexicon.reward[i]!);
 }
 if(scoreCache.size>15000)scoreCache.clear();scoreCache.set(key,values);return values;
}
function fitStyle(bids:any[],words:any[],cut:number):ImitationStyle{
 const negatives=bids.filter(r=>r.match<=cut).map(r=>({...r,best:scores(r.rack)})),positives=words.filter(r=>r.match<=cut).map(r=>({...r,best:scores(r.rack)}));
 let chosen:ImitationStyle={primaryLength:7,primaryMinReward:0,recoveryBalance:15,recoveryMinLength:5,liquidateAt:0,primaryTileCost:0},best=Infinity;
 for(const primaryLength of [7,6,8,5])for(const primaryMinReward of [0,20,25,30,35,40,45,50,55,60])for(const recoveryBalance of [0,10,15,20,30,40,50])for(const recoveryMinLength of [5,4,6,3])for(const liquidateAt of [0,1,2]){
  const active=(r:any)=>r.left<=liquidateAt?r.best[2]>0:r.best[primaryLength]>=primaryMinReward&&r.best[primaryLength]>0||r.balance<recoveryBalance&&r.best[recoveryMinLength]>0;
  let misses=0,falsePlays=0;for(const r of positives)if(!active(r))misses++;for(const r of negatives)if(active(r))falsePlays++;
  const error=misses/Math.max(1,positives.length)+falsePlays/Math.max(1,negatives.length);
  if(error<best){best=error;chosen={primaryLength,primaryMinReward,recoveryBalance,recoveryMinLength,liquidateAt,primaryTileCost:0};}
 }
 let hits=-1;
 for(const primaryTileCost of [0,1,2,3]){
  const style={...chosen,primaryTileCost};let hit=0;
  for(const r of words.filter(r=>r.match<=cut)){const word=chooseImitationWord(view(r),style);if(word&&word.length===r.word.length&&reward(word)===r.reward)hit++;}
  if(hit>hits){hits=hit;chosen=style;}
 }
 return chosen;
}
function reward(word:string){let base=0;for(const c of word)base+=[1,3,3,2,1,4,2,4,1,8,5,1,3,1,1,3,10,1,1,1,1,4,4,8,4,10][c.charCodeAt(0)-65]!;const len=word.length;return len<=3?base:len===4?Math.floor(base*1.5):len===5?base*2:len===6?Math.floor(base*2.5):base*3;}
function view(r:any):MatchView{return{letter:r.letter??'E',rack:r.rack,balance:r.balance,score:r.score??0,auctionsLeft:r.left,unseen:r.unseen??new Uint8Array(BAG_COUNTS),unseenTotal:r.unseen?totalOf(r.unseen):98,opponents:[],firstPrice:false,history:[],lexicon};}
function cdf(z:number){const x=Math.abs(z),t=1/(1+.2316419*x),phi=.3989422804014327*Math.exp(-x*x/2);const p=1-phi*t*(.319381530+t*(-.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));return Math.max(1e-12,Math.min(1-1e-12,z>=0?p:1-p));}
function fitBid(rows:any[],style:ImitationStyle,cut:number){
 const selected=rows.filter(r=>r.left>1&&r.balance>0).map(r=>({...r,features:lexforgeFeatures(view(r),style)}));
 const train=selected.filter(r=>r.match<=cut),test=selected.filter(r=>r.match>cut),n=train[0].features.length;
 const means=Array.from({length:n},(_,j)=>train.reduce((s,r)=>s+r.features[j],0)/train.length),scales=means.map((m,j)=>Math.max(.01,Math.sqrt(train.reduce((s,r)=>s+(r.features[j]-m)**2,0)/train.length)));
 for(const r of selected)r.x=[1,...r.features.map((x:number,j:number)=>(x-means[j]!)/scales[j]!)];
 function loss(r:any,mu:number,s:number):[number,number]{if(r.won&&r.top<r.balance){const e=(mu-r.top)/s;return[.5*e*e+Math.log(s),e/s];}if(!r.won&&r.top>=r.balance)return[0,0];const z=((r.won?r.balance-.5:r.top+.5)-mu)/s,phi=.3989422804014327*Math.exp(-z*z/2);if(r.won){const p=1-cdf(z);return[-Math.log(p),-phi/(s*p)];}const p=cdf(z);return[-Math.log(p),phi/(s*p)];}
 const fits=[];
 for(const sigma of [2,4,6]){
  const w=Array(n+1).fill(0),a=Array(n+1).fill(0),b=Array(n+1).fill(0);w[0]=12;
  const predict=(r:any)=>r.x.reduce((s:number,x:number,j:number)=>s+x*w[j],0);
  for(let epoch=1;epoch<=900;epoch++){const g=Array(n+1).fill(0);
   for(const r of train){const d=loss(r,predict(r),sigma)[1];for(let j=0;j<=n;j++)g[j]+=d*r.x[j]/train.length;}
   for(let j=0;j<=n;j++){g[j]+=(j?.002:0)*w[j];a[j]=.9*a[j]+.1*g[j];b[j]=.999*b[j]+.001*g[j]**2;w[j]-=.03*(a[j]/(1-.9**epoch))/(Math.sqrt(b[j]/(1-.999**epoch))+1e-8);}
  }
  const winners=test.filter(r=>r.won),mae=winners.length?winners.reduce((s,r)=>s+Math.abs(Math.max(0,Math.min(r.balance,predict(r)))-r.top),0)/winners.length:null;
  fits.push({kind:'censored-normal' as const,means,scales,weights:w,sigma,mae,nll:test.reduce((s,r)=>s+loss(r,predict(r),sigma)[0],0)/Math.max(1,test.length)});
 }
 fits.sort((a,b)=>a.nll-b.nll);return fits[0]!;
}
for(let i=0;i<profiles.length;i++){
 const profile=profiles[i],name=`Pegasus-v${String.fromCharCode(97+i)}`,obs=observations(profile),ids=[...new Set<number>(obs.bids.map(r=>r.match))].sort((a,b)=>a-b);
 if(ids.length<8)throw Error(`${profile.name}: fewer than eight usable source matches; refusing unsupported clone`);
 const cut=ids[Math.max(0,Math.floor(ids.length*.7)-1)]!,style=fitStyle(obs.bids,obs.words,cut),fit=fitBid(obs.bids,style,cut);
 const testWords=obs.words.filter(r=>r.match>cut),agree=testWords.length?testWords.filter(r=>{const word=chooseImitationWord(view(r),style);return word&&reward(word)===r.reward;}).length/testWords.length:null;
 const model:ImitationModel={schemaVersion:1,name,source:{botId:profile.botId,name:profile.name,rank:profile.rank,snapshotAt:source.generatedAt,matchIds:ids,latestMatchEndedAt:profile.latestMatchEndedAt},style,
 bid:{kind:fit.kind,means:fit.means,scales:fit.scales,weights:fit.weights,sigma:fit.sigma},validation:{matches:ids.filter(id=>id>cut).length,winningBidMAE:fit.mae,wordRewardAgreement:agree},evidence:{trainingMatches:ids.filter(id=>id<=cut).length,usableMatches:ids.length,skippedMatches:obs.skipped.length,sourceMeanScore:profile.meanScore,sourceMeanPlace:profile.meanPlace}};
 validateImitationModel(model);const path=`fleet/models/${name}.json`;if(existsSync(path))throw Error(`Refusing overwrite: ${path}`);writeFileSync(path,JSON.stringify(model,null,2)+'\n');
 entries.push({name,sourceBotId:profile.botId,sourceName:profile.name,modelPath:path,modelHash:createHash('sha256').update(readFileSync(path)).digest('hex'),status:'prepared'});
 writeFileSync('fleet/manifest.json',JSON.stringify({schemaVersion:1,createdAt:new Date().toISOString(),sourceSnapshotAt:source.generatedAt,sourceSnapshotHash:snapshotHash,entries},null,2)+'\n');
 console.log(JSON.stringify({name,source:profile.name,matches:ids.length,style,validation:model.validation,skipped:obs.skipped}));
}
console.log(`Prepared ${entries.length} frozen models in ${((performance.now()-began)/1000).toFixed(1)} seconds`);
