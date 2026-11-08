// Observe future match assignments without credentials or match participation.
// node --import tsx bench/live/next-matches.mts <afterMatchId> [count=10] [botId=208]
import { mkdirSync,writeFileSync,renameSync } from 'node:fs';
import { sql } from './sql.mjs';
const after=Number(process.argv[2]),count=Number(process.argv[3]??10),hero=Number(process.argv[4]??208);
if(!Number.isSafeInteger(after)||after<0||!Number.isInteger(count)||count<1||count>50||!Number.isSafeInteger(hero))throw Error('Invalid tracker arguments');
const path='bench/results/next-10-matches.json',createdAt=new Date().toISOString();
const records=new Map<number,unknown>();
let names=new Map<number,string>();
mkdirSync('bench/results',{recursive:true});
function save(){writeFileSync(path+'.tmp',JSON.stringify({createdAt,updatedAt:new Date().toISOString(),botId:hero,afterMatchId:after,target:count,
 complete:records.size>=count,matches:[...records].sort((a,b)=>a[0]-b[0]).slice(0,count).map(([,r])=>r)},null,2)+'\n');renameSync(path+'.tmp',path);}
save();
const deadline=Date.now()+45*60*1000;
while(records.size<count&&Date.now()<deadline){
 try{
  const rows=await sql(`SELECT * FROM match_participant WHERE bot_id = ${hero} AND match_id > ${after}`);
  const ids=rows.map(p=>Number(p.match_id)).sort((a,b)=>a-b).slice(0,count);
  for(const id of ids){
   if(records.has(id))continue;
   const [states,table]=await Promise.all([sql(`SELECT * FROM match_state WHERE id = ${id}`),sql(`SELECT * FROM match_participant WHERE match_id = ${id}`)]);
   if(!names.size||table.some(p=>!names.has(Number(p.bot_id))))names=new Map((await sql('SELECT * FROM bot')).map(b=>[Number(b.id),String(b.name)]));
   const state=states[0];
   records.set(id,{matchId:id,observedAt:new Date().toISOString(),startedAt:state?new Date(Number((state.created_at as any[])[0])/1000).toISOString():null,
    opponents:table.filter(p=>Number(p.bot_id)!==hero).map(p=>({botId:Number(p.bot_id),name:names.get(Number(p.bot_id))??String(p.bot_id)}))});
   save();console.log(`${records.size}/${count}: match ${id}`);
  }
 }catch(e){console.error(new Date().toISOString(),String(e));}
 if(records.size<count)await new Promise(r=>setTimeout(r,10000));
}
save();console.log(records.size>=count?'Complete: all requested future matches recorded.':'Tracker reached 45-minute limit with a partial list.');
