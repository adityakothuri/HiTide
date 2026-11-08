// Normal public team/credential reducers, once per independently owned bot.
// Secrets stay under .fleet-secrets (0700 directory, 0600 files), never in logs.
import {readFileSync,writeFileSync,existsSync,mkdirSync,renameSync}from'node:fs';
import {DbConnection}from'../../src/module_bindings/index.js';
import type{Identity}from'spacetimedb';
const HOST=process.env.STDB_HOST??'https://maincloud.spacetimedb.com',DB=process.env.STDB_DB??'scrabblebot';
const path='fleet/manifest.json',manifest=JSON.parse(readFileSync(path,'utf8'));
if(!process.argv.includes('--execute'))throw Error('Use --execute to register the prepared, named bots');
mkdirSync('.fleet-secrets',{recursive:true,mode:0o700});
const pause=(ms:number)=>new Promise(r=>setTimeout(r,ms));
function save(){writeFileSync(path+'.tmp',JSON.stringify(manifest,null,2)+'\n');renameSync(path+'.tmp',path);}
async function connect(tokenPath:string):Promise<{conn:DbConnection;identity:Identity}>{
 return new Promise((resolve,reject)=>{
  let connected:DbConnection|undefined;const timer=setTimeout(()=>{connected?.disconnect();reject(Error('Credential connection timed out'));},20000);
  connected=DbConnection.builder().withUri(HOST).withDatabaseName(DB).withToken(existsSync(tokenPath)?readFileSync(tokenPath,'utf8').trim():undefined)
   .onConnect((conn,identity,token)=>{clearTimeout(timer);writeFileSync(tokenPath,token,{mode:0o600});resolve({conn,identity});})
   .onConnectError(()=>{clearTimeout(timer);reject(Error('Credential connection failed'));}).build();
 });
}
async function subscribe(conn:DbConnection,queries:string[]){await new Promise<void>((resolve,reject)=>conn.subscriptionBuilder().onApplied(()=>resolve()).onError(()=>reject(Error('Credential subscription failed'))).subscribe(queries));}
async function until<T>(find:()=>T|undefined):Promise<T>{for(let i=0;i<80;i++){const value=find();if(value!==undefined)return value;await pause(100);}throw Error('Expected credential state did not arrive');}
const existingIds=new Set<string>();
for(const entry of manifest.entries){
 if(!/^Pegasus-v[a-z]+$/.test(entry.name))throw Error('Invalid bot name');
 const ownerPath=`.fleet-secrets/owner-${entry.name}.token`,botPath=`.fleet-secrets/bot-${entry.name}.token`;
 const owner=await connect(ownerPath);let bot:Awaited<ReturnType<typeof connect>>|undefined;
 try{
  await subscribe(owner.conn,['SELECT * FROM my_team','SELECT * FROM my_nonces']);
  let team=[...owner.conn.db.myTeam.iter()][0];
  if(!team){await owner.conn.reducers.createTeam({teamName:entry.name,botName:entry.name});team=await until(()=>[...owner.conn.db.myTeam.iter()][0]);}
  if(team.botName!==entry.name)throw Error('Owner identity belongs to a different bot; refusing reuse');
  entry.botId=String(team.botId);entry.teamId=String(team.teamId);entry.status='registered';save();
  bot=await connect(botPath);await subscribe(bot.conn,['SELECT * FROM bot_credential']);
  let credential=bot.conn.db.botCredential.identity.find(bot.identity);
  if(!credential){
   await owner.conn.reducers.mintCredentialNonce({});
   const nonce=await until(()=>[...owner.conn.db.myNonces.iter()].find(n=>n.botId===team!.botId));
   await bot.conn.reducers.claimCredential({code:nonce.code});
   credential=await until(()=>bot!.conn.db.botCredential.identity.find(bot!.identity));
  }
  if(credential.botId!==team.botId)throw Error('Credential points at a different bot');
  if(existingIds.has(entry.botId))throw Error('Duplicate server bot identity');existingIds.add(entry.botId);
  entry.status='ready';entry.credentialPath=botPath;save();
  console.log(`${entry.name}: registered bot ${entry.botId}; source ${entry.sourceName}; independent credential verified`);
 }finally{bot?.conn.disconnect();owner.conn.disconnect();}
}
console.log(`Ready: ${manifest.entries.length} independently registered bots. No lobby entries made during provisioning.`);
