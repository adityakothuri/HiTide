import type { MatchView,Policy } from './policy.js';
import { maskOf,totalOf } from './lexicon.js';
import { lexforgeFeatures } from './strategies/lexforgeFeatures.js';
export interface ImitationStyle {primaryLength:number;primaryMinReward:number;recoveryBalance:number;recoveryMinLength:number;liquidateAt:number;primaryTileCost:number}
export interface ImitationModel {
 schemaVersion:1;name:string;source:{botId:number;name:string;rank:number;snapshotAt:string;matchIds:number[];latestMatchEndedAt:string|null};
 style:ImitationStyle;bid:{kind:'censored-normal';means:number[];scales:number[];weights:number[];sigma:number};
 validation:{matches:number;winningBidMAE:number|null;wordRewardAgreement:number|null};evidence:{trainingMatches:number;usableMatches:number;skippedMatches:number;sourceMeanScore:number|null;sourceMeanPlace:number|null};
}
export function chooseImitationWord(v:MatchView,p:ImitationStyle):string|null{
 const lex=v.lexicon;
 if(v.auctionsLeft<=p.liquidateAt){const i=lex.best(v.rack,2);return i<0?null:lex.words[i]!;}
 const mask=maskOf(v.rack);let best=-1,value=-Infinity;
 for(let i=lex.startAt(totalOf(v.rack));i<lex.words.length;i++){
  const len=lex.length[i]!;if(len<p.primaryLength)break;
  if(lex.reward[i]!<p.primaryMinReward||(lex.mask[i]!&~mask)!==0||!lex.spells(i,v.rack))continue;
  const utility=lex.reward[i]!-p.primaryTileCost*len;
  if(utility>value||(utility===value&&best>=0&&len<lex.length[best]!)){best=i;value=utility;}
 }
 if(v.balance<p.recoveryBalance){const i=lex.best(v.rack,p.recoveryMinLength);if(i>=0&&(best<0||lex.reward[i]!>lex.reward[best]!))best=i;}
 return best<0?null:lex.words[best]!;
}
function noise(v:MatchView):number{
 const key=`${v.letter}|${v.auctionsLeft}|${v.balance}|${Array.from(v.rack).join(',')}`;let h=2166136261;
 for(let i=0;i<key.length;i++)h=Math.imul(h^key.charCodeAt(i),16777619);
 let sum=0;for(let i=0;i<4;i++){h=Math.imul(h^(h>>>15),2246822519);h=Math.imul(h^(h>>>13),3266489917);sum+=((h^(h>>>16))>>>0)/4294967296;}
 return(sum-2)*Math.sqrt(3);
}
export function validateImitationModel(m:ImitationModel):void{
 if(m.schemaVersion!==1||!/^Pegasus-v[a-z]+$/.test(m.name))throw Error('Invalid fleet model identity');
 const n=m.bid.means.length;
 if(m.bid.weights.length!==n+1||m.bid.scales.length!==n||m.bid.scales.some(x=>!Number.isFinite(x)||x<=0)||m.bid.weights.some(x=>!Number.isFinite(x))||!Number.isFinite(m.bid.sigma))throw Error('Invalid fleet model coefficients');
 if(m.style.primaryLength<2||m.style.recoveryMinLength<2||m.style.liquidateAt<0)throw Error('Invalid word style');
}
export function imitationPolicy(model:ImitationModel):Policy{
 validateImitationModel(model);
 return{name:model.name,bid(v){
  const balance=Math.floor(v.balance);if(balance<=0)return 0;
  if(v.auctionsLeft===0)return v.firstPrice?Math.min(balance,Math.max(0,...v.opponents.map(p=>p.balance))+1):balance;
  const x=lexforgeFeatures(v,model.style);if(x.length!==model.bid.means.length)throw Error('Fleet model feature mismatch');
  let amount=model.bid.weights[0]!;
  for(let i=0;i<x.length;i++)amount+=model.bid.weights[i+1]!*(x[i]!-model.bid.means[i]!)/model.bid.scales[i]!;
  amount+=model.bid.sigma*noise(v);
  if(v.firstPrice)amount=Math.min(amount*.7,Math.max(0,...v.opponents.map(p=>p.balance))+1);
  return Math.max(0,Math.min(balance,Math.round(amount)));
 },play:v=>chooseImitationWord(v,model.style)};
}
