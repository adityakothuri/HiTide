// Independent SpacetimeDB sessions; only immutable dictionaries/models are shared.
import{DbConnection}from'./module_bindings/index.js';
import{readFileSync,writeFileSync,appendFileSync,mkdirSync,existsSync}from'node:fs';
import{createHash}from'node:crypto';
import{Lexicon,slotOf}from'./lexicon.js';
import{buildView,type LiveSnapshot}from'./live.js';
import{imitationPolicy,type ImitationModel}from'./fleetPolicy.js';
import type{Policy}from'./policy.js';
import type{Identity}from'spacetimedb';
const HOST=process.env.STDB_HOST??'https://maincloud.spacetimedb.com',DB=process.env.STDB_DB??'scrabblebot';
const manifest=JSON.parse(readFileSync('fleet/manifest.json','utf8')) as{entries:Entry[]};
interface Entry{name:string;sourceName:string;botId:string;credentialPath:string;modelPath:string;modelHash:string;status:string}
interface Slot{ready:boolean;subscription:{unsubscribe():void}|null;wordBusy:boolean;wordKey:string;lastBids:Map<string,number>;bidBusy:Set<string>}
const lexicon=Lexicon.fromFile(new URL('../../spacetimedb/wordlist.txt',import.meta.url));
mkdirSync('fleet/results',{recursive:true});
const sessions=new Map<string,FleetSession>();let shuttingDown=false;
class FleetSession{
 conn:DbConnection|null=null;identity:Identity|null=null;slots=new Map<bigint,Slot>();ended=new Set<string>();pending=new Set<bigint>();scheduled=false;ready=false;paused=false;joining=false;lastJoin=0;
 policy:Policy;botId:bigint;state:Record<string,unknown>;reconnectTimer:ReturnType<typeof setTimeout>|null=null;generation=0;
 constructor(readonly entry:Entry){
  if(entry.status!=='ready')throw Error(`${entry.name} is not provisioned`);
  const text=readFileSync(entry.modelPath,'utf8');if(createHash('sha256').update(text).digest('hex')!==entry.modelHash)throw Error('Frozen model hash changed');
  const model=JSON.parse(text) as ImitationModel;if(model.name!==entry.name)throw Error('Model identity mismatch');
  this.policy=imitationPolicy(model);this.botId=BigInt(entry.botId);this.state={name:entry.name,botId:entry.botId,source:entry.sourceName,status:'starting',matches:0,bidErrors:0,lateSkipped:0,wordErrors:0,decisionMaxMs:0};
  const file=`fleet/results/${entry.name}.jsonl`;if(existsSync(file))for(const line of readFileSync(file,'utf8').trim().split('\n'))if(line){try{this.ended.add(String(JSON.parse(line).matchId));}catch{}}
 }
 queue(id:bigint){if(!this.ready||!this.slots.has(id))return;this.pending.add(id);if(this.scheduled)return;this.scheduled=true;queueMicrotask(()=>{this.scheduled=false;const ids=[...this.pending];this.pending.clear();for(const matchId of ids)this.act(matchId);});}
 connect(){
  if(this.paused||shuttingDown)return;const generation=++this.generation;this.ready=false;this.slots.clear();this.pending.clear();
  this.conn=DbConnection.builder().withUri(HOST).withDatabaseName(DB).withToken(readFileSync(this.entry.credentialPath,'utf8').trim())
   .onConnect((conn,identity)=>{
    if(generation!==this.generation||this.paused||shuttingDown){conn.disconnect();return;}
    this.conn=conn;this.identity=identity;this.state.status='subscribing';
    conn.db.matchParticipant.onInsert((_ctx,p)=>{if(this.ready&&p.botId===this.botId)this.watch(p.matchId);});
    conn.db.matchParticipant.onUpdate((_ctx,_old,p)=>this.queue(p.matchId));
    conn.db.auction.onInsert((_ctx,a)=>this.queue(a.matchId));conn.db.auction.onUpdate((_ctx,_old,a)=>this.queue(a.matchId));
    conn.db.myRack.onInsert((_ctx,h)=>this.queue(h.matchId));conn.db.myRack.onUpdate((_ctx,_old,h)=>this.queue(h.matchId));conn.db.myRack.onDelete((_ctx,h)=>this.queue(h.matchId));
    conn.db.wordPlay.onInsert((_ctx,w)=>{if(w.botId===this.botId){const slot=this.slots.get(w.matchId);if(slot)slot.wordBusy=false;}this.queue(w.matchId);});
    conn.db.auctionResult.onInsert((_ctx,a)=>{this.slots.get(a.matchId)?.lastBids.delete(String(a.auctionId));this.queue(a.matchId);});
    conn.db.matchState.onUpdate((_ctx,_old,m)=>this.queue(m.id));
    conn.subscriptionBuilder().onError(()=>{this.state.status='subscription-error';conn.disconnect();})
     .onApplied(()=>{
      const credential=conn.db.botCredential.identity.find(identity);if(credential?.botId!==this.botId){this.state.status='wrong-credential';this.paused=true;conn.disconnect();return;}
      this.ready=true;this.state.status='waiting';
      const recent=[...conn.db.matchParticipant.iter()].filter(p=>p.botId===this.botId).sort((a,b)=>a.matchId>b.matchId?-1:1).slice(0,2);
      for(const p of recent)this.watch(p.matchId);this.join();
      console.log(`[${this.entry.name}] connected as bot ${this.botId}; imitating ${this.entry.sourceName}`);
     }).subscribe(['SELECT * FROM bot_credential','SELECT * FROM my_rack',`SELECT * FROM match_participant WHERE bot_id = ${this.botId}`]);
   }).onConnectError(()=>{if(generation===this.generation)this.retry();}).onDisconnect(()=>{if(generation!==this.generation)return;this.ready=false;this.state.status=this.paused?'paused':'disconnected';this.retry();}).build();
 }
 retry(){if(this.paused||shuttingDown||this.reconnectTimer)return;this.reconnectTimer=setTimeout(()=>{this.reconnectTimer=null;this.connect();},2000);}
 watch(id:bigint){
  if(!this.conn||this.slots.has(id)||this.ended.has(String(id)))return;
  const slot:Slot={ready:false,subscription:null,wordBusy:false,wordKey:'',lastBids:new Map(),bidBusy:new Set()};this.slots.set(id,slot);
  slot.subscription=this.conn.subscriptionBuilder().onError(()=>{this.slots.delete(id);this.state.status='match-subscription-error';})
   .onApplied(()=>{slot.ready=true;this.queue(id);}).subscribe([
    `SELECT * FROM match_state WHERE id = ${id}`,`SELECT * FROM match_participant WHERE match_id = ${id}`,
    `SELECT * FROM auction WHERE match_id = ${id}`,`SELECT * FROM auction_result WHERE match_id = ${id}`,`SELECT * FROM word_play WHERE match_id = ${id}`]);
 }
 snapshot(id:bigint,letter:string):LiveSnapshot|null{
  const conn=this.conn,m=conn?.db.matchState.id.find(id);if(!conn||!m||m.status.tag!=='Running')return null;
  const rack=new Map<string,number>();for(const h of conn.db.myRack.iter())if(h.matchId===id)rack.set(h.letter,(rack.get(h.letter)??0)+h.count);
  return{myBotId:this.botId,matchId:id,letter,startingRackSize:m.startingRackSize,auctionsLeft:m.bagTotal,firstPrice:m.auctionType.tag==='FirstPrice',rack,
   participants:[...conn.db.matchParticipant.iter()].filter(p=>p.matchId===id).map(p=>({botId:p.botId,balance:Number(p.balance),score:Number(p.score)})),
   openLetters:[...conn.db.auction.iter()].filter(a=>a.matchId===id&&a.status.tag==='Open').map(a=>a.letter),
   results:[...conn.db.auctionResult.iter()].filter(r=>r.matchId===id),plays:[...conn.db.wordPlay.iter()].filter(w=>w.matchId===id)};
 }
 act(id:bigint){
  const conn=this.conn,slot=this.slots.get(id);if(!conn||!slot?.ready||this.paused)return;
  const m=conn.db.matchState.id.find(id);if(!m)return;if(m.status.tag==='Ended'){this.finish(id);return;}if(m.status.tag!=='Running')return;
  const snap=this.snapshot(id,'');if(!snap)return;const view=buildView(snap,lexicon);if(!view)return;
  this.state.status='playing';this.state.matchId=String(id);this.state.score=view.score;this.state.balance=view.balance;this.state.auctionsLeft=view.auctionsLeft;this.state.updatedAt=new Date().toISOString();
  const wordKey=`${Array.from(view.rack).join(',')}:${view.balance}:${view.auctionsLeft}`;
  if(!slot.wordBusy&&slot.wordKey!==wordKey){
   slot.wordKey=wordKey;const start=performance.now(),word=this.policy.play(view);this.state.decisionMaxMs=Math.max(Number(this.state.decisionMaxMs),performance.now()-start);
   if(word){
    const counts=new Uint8Array(view.rack);let valid=lexicon.has(word);for(const c of word){const s=slotOf(c);if(!counts[s])valid=false;else counts[s]!--;}
    if(!valid)throw Error(`${this.entry.name}: unplayable policy word`);
    slot.wordBusy=true;console.log(`[${this.entry.name}] match ${id}: ${word}`);
    conn.reducers.submitWord({matchId:id,word}).catch(()=>{slot.wordBusy=false;this.state.wordErrors=Number(this.state.wordErrors)+1;});
   }
  }
  for(const a of conn.db.auction.iter()){
   if(a.matchId!==id||a.status.tag!=='Open')continue;
   const key=String(a.id);if(slot.bidBusy.has(key))continue;
   if(Number(a.closesAt.microsSinceUnixEpoch)/1000-Date.now()<100){this.state.lateSkipped=Number(this.state.lateSkipped)+1;continue;}
   const start=performance.now(),amount=Math.max(0,Math.min(view.balance,Math.floor(this.policy.bid({...view,letter:a.letter}))));
   this.state.decisionMaxMs=Math.max(Number(this.state.decisionMaxMs),performance.now()-start);
   if(slot.lastBids.get(key)===amount||(!amount&&!slot.lastBids.has(key)))continue;
   slot.lastBids.set(key,amount);slot.bidBusy.add(key);
   conn.reducers.submitBid({auctionId:a.id,amount:BigInt(amount)}).catch(()=>{this.state.bidErrors=Number(this.state.bidErrors)+1;}).finally(()=>{slot.bidBusy.delete(key);this.queue(id);});
  }
 }
 finish(id:bigint){
  if(!this.conn)return;const conn=this.conn,slot=this.slots.get(id);
  if(!this.ended.has(String(id))){
   const table=[...conn.db.matchParticipant.iter()].filter(p=>p.matchId===id),me=table.find(p=>p.botId===this.botId);
   if(me){const top=Math.max(...table.map(p=>Number(p.score))),score=Number(me.score),words=[...conn.db.wordPlay.iter()].filter(w=>w.matchId===id&&w.botId===this.botId),wins=[...conn.db.auctionResult.iter()].filter(a=>a.matchId===id&&a.winnerBotId===this.botId);
    const result={matchId:String(id),botId:String(this.botId),name:this.entry.name,source:this.entry.sourceName,endedAt:new Date().toISOString(),score,balance:Number(me.balance),place:1+table.filter(p=>p.score>me.score).length,winShare:score===top?1/table.filter(p=>Number(p.score)===top).length:0,tilesWon:wins.length,paid:wins.reduce((s,a)=>s+Number(a.paid),0),words:words.map(w=>w.word),table:table.map(p=>({botId:String(p.botId),score:Number(p.score)}))};
    appendFileSync(`fleet/results/${this.entry.name}.jsonl`,JSON.stringify(result)+'\n');this.state.lastResult=result;this.state.matches=Number(this.state.matches)+1;console.log(`[${this.entry.name}] match ${id} ended: score ${score}, place ${result.place}`);
   }
   this.ended.add(String(id));
  }
  this.slots.delete(id);slot?.subscription?.unsubscribe();this.state.status='waiting';this.state.matchId=null;this.join();
 }
 join(){if(!this.ready||!this.conn||this.paused||this.joining||Date.now()-this.lastJoin<2000||[...this.slots].some(([id])=>this.conn?.db.matchState.id.find(id)?.status.tag==='Running'))return;
  if([...this.slots.values()].some(s=>!s.ready))return;
  this.joining=true;this.lastJoin=Date.now();this.conn.reducers.joinLobby({}).catch(()=>{}).finally(()=>{this.joining=false;});
 }
 pause(paused:boolean){if(this.paused===paused)return;this.paused=paused;if(paused){this.conn?.disconnect();this.state.status='paused';}else this.connect();}
}
const ids=new Set<string>();for(const entry of manifest.entries){if(ids.has(entry.botId))throw Error('Fleet bots must have different server IDs');ids.add(entry.botId);const session=new FleetSession(entry);sessions.set(entry.name,session);session.connect();}
setInterval(()=>{
 let paused:string[]=[];try{paused=JSON.parse(readFileSync('fleet/control.json','utf8')).pausedBots??[];}catch{}
 for(const [name,s]of sessions){s.pause(paused.includes(name));s.join();}
 writeFileSync('fleet/runtime.json',JSON.stringify({pid:process.pid,updatedAt:new Date().toISOString(),bots:[...sessions.values()].map(s=>s.state),memory:process.memoryUsage()},null,2)+'\n');
},3000);
function stop(){shuttingDown=true;for(const s of sessions.values()){s.conn?.disconnect();if(s.reconnectTimer)clearTimeout(s.reconnectTimer);}setTimeout(()=>process.exit(0),200);}
process.on('SIGTERM',stop);process.on('SIGINT',stop);
