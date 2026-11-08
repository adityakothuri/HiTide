// Subscribe to just what the bot needs, instead of every row of every
// table (the live database holds millions of finished auctions).
//
// Step 1: small tables, plus match_state to learn the newest match id.
// Step 2: the per-match tables, limited to recent matches. Match ids only
// grow, so every match the bot will play from now on is included.

import type { DbConnection } from "./module_bindings/index.js";

const SMALL = [
  "SELECT * FROM bot",
  "SELECT * FROM bot_credential",
  "SELECT * FROM lobby",
  "SELECT * FROM lobby_member",
  "SELECT * FROM match_state",
  "SELECT * FROM my_rack",
];

/** How far below the newest match id to start, to cover matches in play. */
const RECENT_MATCHES = 200;

export function subscribeForBot(conn: DbConnection, onReady: () => void, onError: (msg: string) => void) {
  conn
    .subscriptionBuilder()
    .onError((ctx) => onError(`subscription failed: ${String((ctx as { event?: unknown }).event ?? "unknown")}`))
    .onApplied(() => {
      let newest = 0n;
      for (const m of conn.db.matchState.iter()) if (m.id > newest) newest = m.id;
      const floor = newest > BigInt(RECENT_MATCHES) ? newest - BigInt(RECENT_MATCHES) : 0n;
      conn
        .subscriptionBuilder()
        .onError((ctx) => onError(`subscription failed: ${String((ctx as { event?: unknown }).event ?? "unknown")}`))
        .onApplied(onReady)
        .subscribe([
          `SELECT * FROM match_participant WHERE match_id > ${floor}`,
          `SELECT * FROM auction WHERE match_id > ${floor}`,
          `SELECT * FROM auction_result WHERE match_id > ${floor}`,
          `SELECT * FROM word_play WHERE match_id > ${floor}`,
        ]);
    })
    .subscribe(SMALL);
}
