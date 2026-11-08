// The interface every strategy implements. The live bot (index.ts) and the
// offline simulator (bench/) both build a MatchView and call these.

import type { Counts, Lexicon } from "./lexicon.js";

export interface OpponentView {
  botId?: bigint;
  /** Guaranteed letters only; hidden starting tiles remain unknown. */
  knownRack?: Counts;
  unknownTiles?: number;
  balance: number;
  score: number;
}

export interface AuctionRecord {
  slot: number;
  paid: number;   // what the winner paid (0 if nobody bid)
  mine: boolean;  // this bot won it
}

export interface MatchView {
  /** Letter on auction now (bid calls only; "" for play calls). */
  letter: string;
  /** Auctions still to come after the current one. 0 = this is the last. */
  auctionsLeft: number;
  balance: number;
  score: number;
  rack: Counts;
  opponents: OpponentView[];
  /** Tiles not yet seen by this bot: the bag plus opponents' starting racks. */
  unseen: Counts;
  unseenTotal: number;
  /** Estimated bag composition; its sum equals auctionsLeft. */
  remainingBagEstimate?: Float64Array;
  firstPrice: boolean;
  /** Closed auctions of this match, oldest first. */
  history: readonly AuctionRecord[];
  lexicon: Lexicon;
}

export interface Policy {
  readonly name: string;
  /** Whole-number bid in [0, balance]; 0 skips. */
  bid(view: MatchView): number;
  /** A word to play now, or null. Called again after each play. */
  play(view: MatchView): string | null;
}
