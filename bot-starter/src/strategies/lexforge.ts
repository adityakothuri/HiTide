// Behavioral reconstruction of LexForge-Base-v1 (bot 224) from public records.
// Original source and losing bids are unavailable: this is not a 1:1 code copy.
import { maskOf, totalOf, type Lexicon } from '../lexicon.js';
import type { MatchView, Policy } from '../policy.js';
import { lexforgeFeatures } from './lexforgeFeatures.js';
import { LEXFORGE_TREES } from './lexforgeTrees.js';
import { LEXFORGE_MODEL } from './lexforgeModel.js';
interface BidTree {value:number;feature?:number;cut?:number;left?:BidTree;right?:BidTree}
export const LEXFORGE_PARAMS = { noise:1, useTrees:0, primaryMinLength:7, primaryMinScore:45, primaryTileCost:3, cashBalance:15, recoveryMinLength:5, liquidateAt:1 };
function stateNoise(v:MatchView):number {
 const key=`${v.letter}|${v.auctionsLeft}|${v.balance}|${Array.from(v.rack).join(',')}`;
 let h=2166136261;
 for(let i=0;i<key.length;i++)h=Math.imul(h^key.charCodeAt(i),16777619);
 let sum=0;
 for(let i=0;i<4;i++){h=Math.imul(h^(h>>>15),2246822519);h=Math.imul(h^(h>>>13),3266489917);sum+=((h^(h>>>16))>>>0)/4294967296;}
 return(sum-2)*Math.sqrt(3);
}
const primaryCaches = new WeakMap<Lexicon,Map<string,number>>();
function primaryWord(v:MatchView,p:typeof LEXFORGE_PARAMS):number {
 let cache=primaryCaches.get(v.lexicon);if(!cache)primaryCaches.set(v.lexicon,cache=new Map());
 const key=`${p.primaryMinLength}:${p.primaryMinScore}:${p.primaryTileCost}:${Array.from(v.rack).join(',')}`;
 const hit=cache.get(key);if(hit!==undefined)return hit;
 const lex=v.lexicon,mask=maskOf(v.rack);let best=-1,value=-Infinity;
 for(let i=lex.startAt(totalOf(v.rack));i<lex.words.length;i++){
  if(lex.length[i]!<p.primaryMinLength)break;
  if(lex.reward[i]!<p.primaryMinScore||(lex.mask[i]!&~mask)!==0||!lex.spells(i,v.rack))continue;
  const utility=lex.reward[i]!-p.primaryTileCost*lex.length[i]!;
  if(utility>value||(utility===value&&best>=0&&lex.length[i]!<lex.length[best]!)){best=i;value=utility;}
 }
 if(cache.size>12000)cache.clear();cache.set(key,best);return best;
}
export function lexforge(overrides:Partial<typeof LEXFORGE_PARAMS>={},name='LexForgeObserved'):Policy {
 const p={...LEXFORGE_PARAMS,...overrides};
 return {
  name,
  bid(v){
   const balance=Math.floor(v.balance);if(balance<=0)return 0;
   if(v.auctionsLeft===0)return v.firstPrice?Math.min(balance,Math.max(0,...v.opponents.map(o=>o.balance))+1):balance;
   const features=lexforgeFeatures(v);let mean=LEXFORGE_MODEL.weights[0]!;
   for(let i=0;i<features.length;i++)mean+=LEXFORGE_MODEL.weights[i+1]!*(features[i]!-LEXFORGE_MODEL.means[i]!)/LEXFORGE_MODEL.scales[i]!;
   let sigma=LEXFORGE_MODEL.sigma;
   if(p.useTrees){
    mean=LEXFORGE_TREES.initial;
    for(const root of LEXFORGE_TREES.trees){
     let node:BidTree=root;
     while(node.feature!==undefined)node=features[node.feature]!<=node.cut!?node.left!:node.right!;
     mean+=LEXFORGE_TREES.rate*node.value;
    }
    sigma=LEXFORGE_TREES.sigma;
   }
   let amount=Math.round(mean+p.noise*sigma*stateNoise(v));
   if(v.firstPrice)amount=Math.min(Math.floor(amount*.7),Math.max(0,...v.opponents.map(o=>o.balance))+1);
   return Math.max(0,Math.min(balance,amount));
  },
  play(v){
   if(v.auctionsLeft<=p.liquidateAt){const i=v.lexicon.best(v.rack,2);return i<0?null:v.lexicon.words[i]!;}
   const primary=primaryWord(v,p);
   let chosen=primary>=0&&v.lexicon.reward[primary]!>=p.primaryMinScore?primary:-1;
   if(v.balance<p.cashBalance){const rescue=v.lexicon.best(v.rack,p.recoveryMinLength);if(rescue>=0&&(chosen<0||v.lexicon.reward[rescue]!>v.lexicon.reward[chosen]!))chosen=rescue;}
   return chosen<0?null:v.lexicon.words[chosen]!;
  },
 };
}
