// Features use only our own rack and already-public bag/auction observations.
import { type MatchView } from '../policy.js';
import { totalOf, SLOT_VALUE } from '../lexicon.js';
import { PLANNER_PARAMS, potentials } from './planner.js';
export const LEXFORGE_FEATURE_NAMES = [
  ...Array.from({length:26},(_,s)=>`letter_${String.fromCharCode(65+s)}`),
  'balance','log_balance','cash_per_round','rack_size','copies','vowel_gap','face_value',
  'immediate_gain','six_plus_gain','target_gain','rack_face_value','q_without_support',
  'primary_before','primary_after','new_primary_cash','new_recovery_cash',
];
const PLAN={...PLANNER_PARAMS,maxDeficit:1,minTargetLength:7,maxWordLength:12,winRate:.7};
export function lexforgeFeatures(v:Pick<MatchView,'letter'|'rack'|'balance'|'auctionsLeft'|'unseen'|'unseenTotal'|'lexicon'>):number[]{
 const s=v.letter.charCodeAt(0)-65, n=totalOf(v.rack), plus=new Uint8Array(v.rack);plus[s]!++;
 const score=(rack:Uint8Array,min:number)=>{const i=v.lexicon.best(rack,min);return i<0?0:v.lexicon.reward[i]!;};
 let vowels=0,face=0;for(let j=0;j<26;j++){if('AEIOU'.includes(String.fromCharCode(65+j)))vowels+=v.rack[j]!;face+=v.rack[j]!*SLOT_VALUE[j]!;}
 const odds=new Float64Array(26),share=v.unseenTotal?Math.min(1,v.auctionsLeft/v.unseenTotal):0;
 for(let j=0;j<26;j++)odds[j]=.7*(1-(1-share)**v.unseen[j]!);
 const primaryBefore=score(v.rack,7),primaryAfter=score(plus,7);
 const recoveryBefore=v.balance<15?score(v.rack,5):0,recoveryAfter=v.balance<15?score(plus,5):0;
 const [before,after]=potentials(v.lexicon,v.rack,s,odds,PLAN);
 return [...Array.from({length:26},(_,j)=>j===s?1:0),v.balance,Math.log1p(v.balance),v.balance/(v.auctionsLeft+1),n,v.rack[s]!,
  ('AEIOU'.includes(v.letter)?1:-1)*(.4-(n?vowels/n:.4)),SLOT_VALUE[s]!,
  score(plus,2)-score(v.rack,2),score(plus,6)-score(v.rack,6),Math.max(0,after-before),face,
  v.letter==='Q'&&!v.rack[20]&&!v.rack[8]?1:0,primaryBefore,primaryAfter,
  primaryBefore<45&&primaryAfter>=45?primaryAfter:0,
  v.balance<15&&recoveryBefore===0?recoveryAfter:0];
}
