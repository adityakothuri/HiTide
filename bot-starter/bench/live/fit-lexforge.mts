// Censored bid fit: wins expose exact bids; losses expose only an upper bound.
import {readFileSync,writeFileSync} from 'node:fs';
import {Lexicon} from '../../src/lexicon.js';
import {lexforgeFeatures,LEXFORGE_FEATURE_NAMES} from '../../src/strategies/lexforgeFeatures.js';
const began=performance.now(),data=JSON.parse(readFileSync('bench/results/viability/lexforge-observations.json','utf8'));
const lexicon=Lexicon.fromFile(new URL('../../../spacetimedb/wordlist.txt',import.meta.url));
const ids=[...new Set<number>(data.matches.map((m:any)=>m.id))].sort((a,b)=>a-b),cutoff=ids[23]!;
const rows=data.bids.filter((r:any)=>r.left>1&&r.balance>0).map((r:any)=>({
 ...r,features:lexforgeFeatures({letter:r.letter,rack:Uint8Array.from(r.rack),balance:r.balance,auctionsLeft:r.left,
 unseen:Uint8Array.from(r.unseen),unseenTotal:r.unseen.reduce((a:number,b:number)=>a+b,0),lexicon})}));
const train=rows.filter((r:any)=>r.match<=cutoff),test=rows.filter((r:any)=>r.match>cutoff),n=LEXFORGE_FEATURE_NAMES.length;
const means=Array.from({length:n},(_,j)=>train.reduce((s:number,r:any)=>s+r.features[j],0)/train.length);
const scales=means.map((mean,j)=>Math.max(.01,Math.sqrt(train.reduce((s:number,r:any)=>s+(r.features[j]-mean)**2,0)/train.length)));
for(const row of rows)row.x=[1,...row.features.map((v:number,j:number)=>(v-means[j]!)/scales[j]!)];
function cdf(z:number){const x=Math.abs(z),t=1/(1+.2316419*x),phi=.3989422804014327*Math.exp(-x*x/2);
 const p=1-phi*t*(.319381530+t*(-.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));return Math.max(1e-12,Math.min(1-1e-12,z>=0?p:1-p));}
function lossGradient(row:any,mu:number,sigma:number):[number,number]{
 if(row.won&&row.top<row.balance){const d=(mu-row.top)/sigma;return[.5*d*d+Math.log(sigma),d/sigma];}
 if(!row.won&&row.top>=row.balance)return[0,0];
 const z=((row.won?row.balance-.5:row.top+.5)-mu)/sigma,phi=.3989422804014327*Math.exp(-z*z/2);
 if(row.won){const survival=1-cdf(z);return[-Math.log(survival),-phi/(sigma*survival)];}
 const cumulative=cdf(z);return[-Math.log(cumulative),phi/(sigma*cumulative)];
}
function predict(row:any,weights:number[]){return row.x.reduce((s:number,x:number,j:number)=>s+x*weights[j]!,0);}
const fits=[];
for(const sigma of [2,4,6]){
 const weights=Array(n+1).fill(0);weights[0]=15;
 const first=Array(n+1).fill(0),second=Array(n+1).fill(0);
 for(let epoch=1;epoch<=1400;epoch++){
  const gradient=Array(n+1).fill(0);
  for(const row of train){const [,g]=lossGradient(row,predict(row,weights),sigma);for(let j=0;j<=n;j++)gradient[j]+=g*row.x[j]/train.length;}
  for(let j=0;j<=n;j++){
   gradient[j]+=(j? .002:0)*weights[j];first[j]=.9*first[j]+.1*gradient[j];second[j]=.999*second[j]+.001*gradient[j]**2;
   weights[j]-=.025*(first[j]/(1-.9**epoch))/(Math.sqrt(second[j]/(1-.999**epoch))+1e-8);
  }
 }
 function metrics(selected:any[]){const wins=selected.filter(r=>r.won),losses=selected.filter(r=>!r.won&&r.top<r.balance);
  return{rows:selected.length,wins:wins.length,winningBidMAE:wins.reduce((s,r)=>s+Math.abs(Math.max(0,Math.min(r.balance,predict(r,weights)))-r.top),0)/wins.length,
   censoredNLL:selected.reduce((s,r)=>s+lossGradient(r,predict(r,weights),sigma)[0],0)/selected.length,
   losingUpperBoundViolations:losses.filter(r=>Math.min(r.balance,predict(r,weights))>r.top+1).length/losses.length};}
 fits.push({sigma,weights,train:metrics(train),validation:metrics(test)});
 console.log(JSON.stringify(fits.at(-1)));
}
fits.sort((a,b)=>a.validation.censoredNLL-b.validation.censoredNLL);
const best=fits[0]!;
const model={sourceBotId:224,sourceName:'LexForge-Base-v1',trainingMatchIds:ids.filter(id=>id<=cutoff),validationMatchIds:ids.filter(id=>id>cutoff),
 featureNames:LEXFORGE_FEATURE_NAMES,means,scales,weights:best.weights,sigma:best.sigma,metrics:{train:best.train,validation:best.validation}};
writeFileSync('src/strategies/lexforgeModel.ts',`// Fitted from public finished-match records; behavioral reconstruction, not source code.\nexport const LEXFORGE_MODEL = ${JSON.stringify(model,null,2)};\n`);
writeFileSync('bench/results/viability/lexforge-bid-fit.json',JSON.stringify({elapsedSeconds:(performance.now()-began)/1000,model,fits},null,2)+'\n');
