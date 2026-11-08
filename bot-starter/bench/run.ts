// Experiment runner.
//
//   npx tsx bench/run.ts suite --heroes Starter,Report --games 500 --seed 1
//   npx tsx bench/run.ts melee --heroes A,B,C --fill mix --games 500
//   options: --fields mixed,agg,...  --first-price  --params '{"Name":{...}}'
//
// Every strategy is run on the same seeds. The simulator draws random
// numbers the same way whatever the bids are, so game i deals the same
// racks, tile order and sim jitter to every strategy (paired comparison).

import { Lexicon } from "../src/lexicon.js";
import type { Policy } from "../src/policy.js";
import { FLEET_NAMES, REGISTRY } from "./registry.js";
import {
  type Rng,
  type Seat,
  type SeatResult,
  type SimStyle,
  MARKET,
  intIn,
  mulberry32,
  runMatch,
  shuffle,
} from "./sim.js";

const args = process.argv.slice(2);
const mode = args[0] ?? "suite";
const opt = (name: string, dflt: string): string => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] !== undefined ? args[i + 1]! : dflt;
};
const GAMES = Number(opt("games", "500"));
const SEED = Number(opt("seed", "1"));
const FIRST_PRICE = args.includes("--first-price");
const PARAMS: Record<string, Record<string, number>> = JSON.parse(opt("params", "{}"));
const HEROES = opt("heroes", "Starter,Report").split(",");
const FIELDS = opt("fields", "mixed,agg,value,cheap,starters,reports,realmix").split(",");

const lexicon = Lexicon.fromFile(new URL("../../spacetimedb/wordlist.txt", import.meta.url));

// ---------- Timing wrapper ----------

interface Timing { calls: number; total: number; max: number }
const timings = new Map<string, Timing>();
function timed(p: Policy): Policy {
  const t = timings.get(p.name) ?? { calls: 0, total: 0, max: 0 };
  timings.set(p.name, t);
  const wrap = <A extends unknown[], R>(f: (...a: A) => R) => (...a: A): R => {
    const s = performance.now();
    const r = f(...a);
    const d = performance.now() - s;
    t.calls++;
    t.total += d;
    if (d > t.max) t.max = d;
    return r;
  };
  return { name: p.name, bid: wrap(p.bid.bind(p)), play: wrap(p.play.bind(p)) };
}

function makePolicy(name: string): Policy {
  const factory = REGISTRY[name];
  if (!factory) throw new Error(`unknown strategy ${name}; have ${Object.keys(REGISTRY).join(", ")}`);
  return timed(factory(PARAMS[name] ?? {}));
}

// ---------- Fields ----------

const SIM_POOL: SimStyle[] = ["Cheapskate", "ValueBidder", "Aggressive", "ValueBidder", "Aggressive", "Cheapskate"];
const sim = (style: SimStyle): Seat => ({ kind: "sim", style });
const pol = (name: string): Seat => ({ kind: "policy", policy: makePolicy(name) });

function opponents(field: string, rng: Rng): Seat[] {
  switch (field) {
    case "mixed": return shuffle(rng, SIM_POOL).slice(0, 5).map(sim);
    case "agg": return Array.from({ length: 5 }, () => sim("Aggressive"));
    case "value": return Array.from({ length: 5 }, () => sim("ValueBidder"));
    case "cheap": return Array.from({ length: 5 }, () => sim("Cheapskate"));
    case "starters": return Array.from({ length: 5 }, () => pol("Starter"));
    case "reports": return Array.from({ length: 5 }, () => pol("Report"));
    case "blive": return shuffle(rng, ["B-LUCENT", "B-Bron", "B-GodOfThudner", "B-Maverick", "B-StickBot", "B-Odysseus", "B-Tow57", "B-SoapConsumers"]).slice(0, 5).map(pol);
    case "slive": return shuffle(rng, ["S-LUCENT", "S-Bron", "S-GodOfThudner", "S-Maverick", "S-StickBot", "S-Odysseus", "S-Tow57", "S-SoapConsumers"]).slice(0, 5).map(pol);
    case "live": return shuffle(rng, ["M-LUCENT", "M-Bron", "M-GodOfThudner", "M-Maverick", "M-StickBot", "M-Odysseus"]).slice(0, 5).map(pol);
    case "fleet": return shuffle(rng, FLEET_NAMES).slice(0, 5).map(pol);
    case "realmix": return [pol("Starter"), pol("Starter"), pol("Report"), sim("Aggressive"), sim("ValueBidder")];
    default: {
      // "Name*k+Other*j+..." for custom fields
      const seats: Seat[] = [];
      for (const part of field.split("+")) {
        const [n, k] = part.split("*");
        for (let i = 0; i < Number(k ?? 1); i++) {
          seats.push(["Cheapskate", "ValueBidder", "Aggressive"].includes(n!) ? sim(n as SimStyle) : pol(n!));
        }
      }
      return seats;
    }
  }
}

// ---------- Stats ----------

function wilson(wins: number, n: number): [number, number] {
  const z = 1.96;
  const p = wins / n;
  const d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  return [Math.max(0, c - h), Math.min(1, c + h)];
}

function meanCi(xs: number[]): [number, number] {
  const n = xs.length;
  const m = xs.reduce((a, b) => a + b, 0) / n;
  const v = xs.reduce((a, b) => a + (b - m) ** 2, 0) / Math.max(1, n - 1);
  return [m, 1.96 * Math.sqrt(v / n)];
}

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

/** Win credit: 1 for a clear first, 1/k when k bots share the top score. */
function winCredit(r: SeatResult, all: SeatResult[]): number {
  if (r.place !== 0) return 0;
  return 1 / all.filter((q) => q.place === 0).length;
}

interface Rec { win: number[]; place: number[]; score: number[]; opp: number[]; left: number[]; won: number[]; words: number[] }
const newRec = (): Rec => ({ win: [], place: [], score: [], opp: [], left: [], won: [], words: [] });
function record(rec: Rec, r: SeatResult, all: SeatResult[]) {
  rec.win.push(winCredit(r, all));
  rec.place.push(r.place + 1);
  rec.score.push(r.score);
  rec.opp.push(Math.max(...all.filter((q) => q !== r).map((q) => q.score)));
  rec.left.push(r.tilesLeft);
  rec.won.push(r.tilesWon);
  rec.words.push(r.words);
}

const matchOpts = { lexicon, firstPrice: FIRST_PRICE, startingRack: 5, startingBalance: 100 };

// ---------- Modes ----------

function suite() {
  console.log(`suite: ${GAMES} games/field, seed ${SEED}, ${FIRST_PRICE ? "first-price" : "Vickrey"}\n`);
  console.log("| Field | Strategy | Win share (95% CI) | Mean place | Mean score | Best opp. | Δplace vs " + HEROES[0] + " | won/words/left |");
  console.log("|---|---|---|---:|---:|---:|---:|---|");
  for (const field of FIELDS) {
    const recs = HEROES.map(newRec);
    for (const [h, hero] of HEROES.entries()) {
      const rng = mulberry32(SEED);
      for (let g = 0; g < GAMES; g++) {
        const seat = intIn(rng, 0, 5);
        const seats = opponents(field, rng);
        seats.splice(seat, 0, pol(hero));
        const res = runMatch(seats, rng, matchOpts);
        record(recs[h]!, res[seat]!, res);
      }
    }
    for (const [h, hero] of HEROES.entries()) {
      const r = recs[h]!;
      const wins = r.win.reduce((a, b) => a + b, 0);
      const [lo, hi] = wilson(wins, GAMES);
      const [pm] = meanCi(r.place);
      const [sm] = meanCi(r.score);
      const [om] = meanCi(r.opp);
      let delta = "—";
      if (h > 0) {
        const [dm, dh] = meanCi(r.place.map((x, i) => x - recs[0]!.place[i]!));
        delta = `${dm >= 0 ? "+" : ""}${dm.toFixed(2)} ± ${dh.toFixed(2)}`;
      }
      const avg = (xs: number[]) => (xs.reduce((a, b) => a + b, 0) / xs.length).toFixed(1);
      console.log(`| ${field} | ${hero} | ${pct(wins / GAMES)} (${pct(lo)}–${pct(hi)}) | ${pm.toFixed(2)} | ${sm.toFixed(1)} | ${om.toFixed(1)} | ${delta} | ${avg(r.won)}/${avg(r.words)}/${avg(r.left)} |`);
    }
  }
  printTimings();
}

/** All heroes at one table (seats shuffled), padded with `--fill`. */
function melee() {
  const fill = opt("fill", "mix");
  console.log(`melee: ${HEROES.join(" vs ")} + ${fill}, ${GAMES} games, seed ${SEED}, ${FIRST_PRICE ? "first-price" : "Vickrey"}\n`);
  const recs = new Map(HEROES.map((h) => [h, newRec()]));
  const rng = mulberry32(SEED);
  for (let g = 0; g < GAMES; g++) {
    const seats: Seat[] = HEROES.map(pol);
    while (seats.length < 6) {
      seats.push(fill === "mix" ? sim(SIM_POOL[intIn(rng, 0, 5)]!) : opponents(fill, rng)[0]!);
    }
    const order = shuffle(rng, seats);
    const res = runMatch(order, rng, matchOpts);
    const seen = new Set<string>();
    for (const r of res) {
      if (!recs.has(r.name) || seen.has(r.name)) continue;
      seen.add(r.name);
      record(recs.get(r.name)!, r, res);
    }
  }
  console.log("| Strategy | Win share (95% CI) | Mean place | Mean score | Tiles won | Words | Tiles left at end |");
  console.log("|---|---|---:|---:|---:|---:|---:|");
  for (const [name, r] of recs) {
    const wins = r.win.reduce((a, b) => a + b, 0);
    const [lo, hi] = wilson(wins, GAMES);
    const [pm, ph] = meanCi(r.place);
    const [sm] = meanCi(r.score);
    const [lm] = meanCi(r.left);
    const avg = (xs: number[]) => (xs.reduce((a, b) => a + b, 0) / xs.length).toFixed(1);
    console.log(`| ${name} | ${pct(wins / GAMES)} (${pct(lo)}–${pct(hi)}) | ${pm.toFixed(2)} ± ${ph.toFixed(2)} | ${sm.toFixed(1)} | ${avg(r.won)} | ${avg(r.words)} | ${lm.toFixed(1)} |`);
  }
  printTimings();
}

function printMarket() {
  if (MARKET.sold === 0) return;
  console.log(`\nmarket: ${MARKET.sold} tiles sold, ${MARKET.unsold} unsold; mean winning bid ${(MARKET.top / MARKET.sold).toFixed(1)}, mean price paid ${(MARKET.paid / MARKET.sold).toFixed(1)} (live: 15.0 / 10.6)`);
  // Live mean price paid by letter (bench/live/market.mts, 400 matches).
  const LIVE = [10.7, 14.7, 16.1, 13.1, 11.0, 16.9, 12.0, 18.7, 10.0, 24.4, 21.4, 10.5, 15.6, 10.3, 10.1, 15.3, 19.3, 10.8, 11.9, 9.9, 9.8, 15.4, 16.5, 25.7, 18.9, 30.5];
  const row = MARKET.bySlot.map((b, s) => `${String.fromCharCode(65 + s)} ${b.sold ? (b.paid / b.sold).toFixed(0) : "-"}/${LIVE[s]!.toFixed(0)}`);
  console.log(`price paid by letter, sim/live: ${row.join("  ")}`);
}

function printTimings() {
  printMarket();
  console.log("\n| Strategy | decision calls | mean ms | max ms |");
  console.log("|---|---:|---:|---:|");
  for (const [name, t] of timings) {
    if (t.calls === 0) continue;
    console.log(`| ${name} | ${t.calls} | ${(t.total / t.calls).toFixed(3)} | ${t.max.toFixed(1)} |`);
  }
}

if (mode === "suite") suite();
else if (mode === "melee") melee();
else throw new Error(`unknown mode ${mode}`);
