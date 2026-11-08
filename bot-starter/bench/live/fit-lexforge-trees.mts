// Nonlinear censored imitation, using the same chronological source split.
import{readFileSync,writeFileSync}from'node:fs';
import{Lexicon}from'../../src/lexicon.js';
import{lexforgeFeatures}from'../../src/strategies/lexforgeFeatures.js';
const began=performance.now(),data=JSON.parse(readFileSync('bench/results/viability/lexforge-observations.json','utf8'));
const lexicon=Lexicon.fromFile(new URL('../../../spacetimedb/wordlist.txt',import.meta.url));
const rows=data.bids.filter((r:any)=>r.left>1&&r.balance>0).map((r:any)=>({...r,x:lexforgeFeatures({letter:r.letter,rack:Uint8Array.from(r.rack),balance:r.balance,auctionsLeft:r.left,unseen:Uint8Array.from(r.unseen),unseenTotal:r.unseen.reduce((a:number,b:number)=>a+b,0),lexicon})}));
const train=rows.filter((r:any)=>r.match<=45320),test=rows.filter((r:any)=>r.match>45320),n=train.length,d=train[0].x.length;
const orders=Array.from({length:d},(_,f)=>Array.from({length:n},(_,i)=>i).sort((a,b)=>train[a].x[f]-train[b].x[f]));
type Tree={value:number;feature?:number;cut?:number;left?:Tree;right?:Tree};
function predict(t:Tree,x:number[]):number{while(t.feature!==undefined)t=x[t.feature]!<=t.cut!?t.left!:t.right!;return t.value;}
function cdf(z:number){const x=Math.abs(z),t=1/(1+.2316419*x),phi=.3989422804014327*Math.exp(-x*x/2);const p=1-phi*t*(.319381530+t*(-.356563782+t*(1.781477937+t*(-1.821255978+t*1.330274429))));return Math.max(1e-10,Math.min(1-1e-10,z>=0?p:1-p));}
function loss(row:any,mu:number,s:number):[number,number,number]{
 if(row.won&&row.top<row.balance){const e=mu-row.top;return[.5*(e/s)**2+Math.log(s),e/s**2,1/s**2];}
 if(!row.won&&row.top>=row.balance)return[0,0,0];
 const z=((row.won?row.balance-.5:row.top+.5)-mu)/s,phi=.3989422804014327*Math.exp(-z*z/2);
 if(row.won){const p=1-cdf(z),a=phi/p;return[-Math.log(p),-a/s,Math.max(.0001,a*(a-z)/s**2)];}
 const p=cdf(z),a=phi/p;return[-Math.log(p),a/s,Math.max(.0001,a*(z+a)/s**2)];
}
const fits:any[]=[];
for(const sigma of [2,4,6]){
 const initial=12,rate=.08,trees:Tree[]=[],mu=Array(n).fill(initial),tv=Array(test.length).fill(initial);
 let bestLoss=Infinity,bestTrees:Tree[]=[];
 for(let epoch=0;epoch<220;epoch++){
  const g=new Float64Array(n),h=new Float64Array(n);
  for(let i=0;i<n;i++){const v=loss(train[i],mu[i],sigma);g[i]=v[1];h[i]=v[2];}
  function build(ids:number[],depth:number):Tree{
   let G=0,H=0;for(const i of ids){G+=g[i]!;H+=h[i]!;}
   const node:Tree={value:Math.max(-8,Math.min(8,-G/(H+.8)))};
   if(!depth||ids.length<50)return node;
   const member=new Uint8Array(n);for(const i of ids)member[i]=1;
   let bestGain=0,feature=-1,cut=0;
   for(let f=0;f<d;f++){
    let lg=0,lh=0,count=0,last=-Infinity;
    for(const i of orders[f]!){if(!member[i])continue;const x=train[i].x[f];
     if(x!==last&&count>=22&&ids.length-count>=22){
      const gain=lg*lg/(lh+.8)+(G-lg)**2/(H-lh+.8)-G*G/(H+.8);
      if(gain>bestGain){bestGain=gain;feature=f;cut=(last+x)/2;}
     }
     lg+=g[i]!;lh+=h[i]!;count++;last=x;
    }
   }
   if(feature<0)return node;
   const a=ids.filter(i=>train[i].x[feature]<=cut),b=ids.filter(i=>train[i].x[feature]>cut);
   return{value:node.value,feature,cut,left:build(a,depth-1),right:build(b,depth-1)};
  }
  const tree=build(Array.from({length:n},(_,i)=>i),2);trees.push(tree);
  for(let i=0;i<n;i++)mu[i]+=rate*predict(tree,train[i].x);
  for(let i=0;i<test.length;i++)tv[i]+=rate*predict(tree,test[i].x);
  if(epoch%10===9){const validation=test.reduce((sum:number,r:any,i:number)=>sum+loss(r,tv[i],sigma)[0],0)/test.length;
   if(validation<bestLoss){bestLoss=validation;bestTrees=structuredClone(trees);}}
 }
 function evaluate(selected:any[]){const predictions=selected.map(r=>initial+rate*bestTrees.reduce((s,t)=>s+predict(t,r.x),0));const wins=selected.map((r,i)=>r.won?Math.abs(Math.min(r.balance,Math.max(0,predictions[i]))-r.top):null).filter(x=>x!==null) as number[];
  return{rows:selected.length,winningBidMAE:wins.reduce((a,b)=>a+b,0)/wins.length,censoredNLL:selected.reduce((s,r,i)=>s+loss(r,predictions[i],sigma)[0],0)/selected.length};}
 const fit={sigma,initial,rate,trees:bestTrees,train:evaluate(train),validation:evaluate(test)};fits.push(fit);
 console.log(JSON.stringify({sigma,trees:bestTrees.length,train:fit.train,validation:fit.validation}));
}
fits.sort((a,b)=>a.validation.censoredNLL-b.validation.censoredNLL);const best=fits[0];
writeFileSync('src/strategies/lexforgeTrees.ts',`// Nonlinear bid reconstruction from public source matches; original code unavailable.\nexport const LEXFORGE_TREES = ${JSON.stringify(best)};\n`);
writeFileSync('bench/results/viability/lexforge-tree-fit.json',JSON.stringify({elapsedSeconds:(performance.now()-began)/1000,fits},null,2)+'\n');
