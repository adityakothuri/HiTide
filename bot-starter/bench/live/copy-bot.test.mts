import { test } from 'node:test';
import assert from 'node:assert/strict';
import { copyName } from './copy-bot.mjs';
import { mkdtempSync, writeFileSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

test('random three-letter names avoid collisions, including repeated draws',()=>{
  assert.equal(copyName([],()=>0),'Pegasus-vAAA');
  assert.equal(copyName(['Pegasus-vAAA'],()=>0),'Pegasus-vAAB');
  assert.equal(copyName([],()=>26**3-1),'Pegasus-vZZZ');
  const taken=new Set<string>();
  for(let i=0;i<100;i++){const name=copyName(taken);assert.match(name,/^Pegasus-v[A-Z]{3}$/);assert.ok(!taken.has(name));taken.add(name);}
});

test('copied runners load and acknowledge isolated profiles without overwriting Pegasus',()=>{
  const folder=mkdtempSync(join(tmpdir(),'scout-copy-check-'));
  const originalPath=new URL('../results/scouting/runtime.json',import.meta.url);
  let original: string|null=null;try{original=readFileSync(originalPath,'utf8');}catch{}
  for(const name of ['Lbender','LexForge']){
    const config=join(folder,name+'.json'),runtime=join(folder,name+'-runtime.json');
    writeFileSync(config,JSON.stringify({enabled:true,mode:'imitate',revision:name,generatedAt:new Date().toISOString(),profiles:[{name,botId:224}]}));
    const child=spawnSync(process.execPath,['--import','tsx','--input-type=module','-e',`import {loadScouting,writeScoutHeartbeat} from './src/scouting.ts';if(loadScouting()?.revision!==${JSON.stringify(name)})throw Error('Wrong configuration');writeScoutHeartbeat({botName:${JSON.stringify('Pegasus-v'+name)}});`],{cwd:new URL('../../',import.meta.url),env:{...process.env,SCOUT_CONFIG_PATH:config,SCOUT_RUNTIME_PATH:runtime},encoding:'utf8'});
    assert.equal(child.status,0,child.stderr);
    const state=JSON.parse(readFileSync(runtime,'utf8'));
    assert.equal(state.revision,name);assert.equal(state.profileName,name);assert.equal(state.botName,'Pegasus-v'+name);
  }
  // Pegasus may be producing heartbeats concurrently; its identity/config must stay independent.
  if(original){const before=JSON.parse(original),after=JSON.parse(readFileSync(originalPath,'utf8'));assert.equal(after.botName,before.botName);assert.equal(after.pid,before.pid);}
});
