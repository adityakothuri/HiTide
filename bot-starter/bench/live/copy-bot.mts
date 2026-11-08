import { DbConnection } from '../../src/module_bindings/index.js';
import { writeFileSync } from 'node:fs';
import { randomInt } from 'node:crypto';

export function copyName(taken: Iterable<string>, draw = () => randomInt(26 ** 3)): string {
  const names = new Set(taken);
  const encode = (n: number) => 'Pegasus-v'+String.fromCharCode(65+Math.floor(n/676),65+Math.floor(n/26)%26,65+n%26);
  let start = 0;
  for (let i=0;i<128;i++) {
    start = draw();
    const name = encode(start);
    if (!names.has(name)) return name;
  }
  for (let i=1;i<26**3;i++) {
    const name = encode((start+i)%(26**3));
    if (!names.has(name)) return name;
  }
  throw Error('No free copy name found');
}

/** Provision one fresh team and its bot through the game's public reducers.
 * The fresh identity owns the team and claims its own newly minted credential.
 * Persist its token privately before mutations so registration remains recoverable.
 */
export function registerCopy(name: string, tokenFile: string): Promise<string> {
  return new Promise((resolve,reject) => {
    let connection: DbConnection | null = null, settled = false;
    const finish = (error?: Error, id?: string) => {
      if (settled) return; settled=true;clearTimeout(timeout);connection?.disconnect();
      error ? reject(error) : resolve(id!);
    };
    const timeout = setTimeout(()=>finish(Error('Bot registration timed out. The saved identity can recover any created team.')),30000);
    connection = DbConnection.builder()
      .withUri(process.env.STDB_HOST ?? 'https://maincloud.spacetimedb.com')
      .withDatabaseName(process.env.STDB_DB ?? 'scrabblebot')
      .onConnect((conn,_identity,token) => {
        connection=conn;
        void (async()=>{
          try {
            writeFileSync(tokenFile,token,{mode:0o600,flag:'wx'});
            await new Promise<void>((ok,fail)=>conn.subscriptionBuilder().onApplied(()=>ok()).onError(()=>fail(Error('Registration subscription failed'))).subscribe(['SELECT * FROM bot','SELECT * FROM my_nonces']));
            if (settled) return;
            await conn.reducers.createTeam({teamName:name,botName:name});
            if (settled) return;
            await conn.reducers.mintCredentialNonce({});
            let nonce: any, bot: any;
            for(let i=0;i<100&&!settled;i++) {
              nonce=[...conn.db.myNonces.iter()][0];bot=[...conn.db.bot.iter()].find(b=>b.name===name);
              if(nonce&&bot)break;
              await new Promise(r=>setTimeout(r,50));
            }
            if(settled)return;
            if(!nonce||!bot)throw Error('Created team but its credential did not arrive. Saved identity retained.');
            await conn.reducers.claimCredential({code:nonce.code});
            finish(undefined,String(bot.id));
          } catch(e) { finish(e instanceof Error?e:Error(String(e))); }
        })();
      })
      .onConnectError((_ctx,e)=>finish(Error(`Registration connection failed: ${e.message}`)))
      .build();
  });
}
