// Random-search tuner. Evaluates sampled parameter sets for one strategy on
// a fixed set of tough fields (paired seeds) and appends JSON lines.
//
//   npx tsx bench/tune.ts --strategy Planner --n 10 --sample-seed 3 \
//     --games 100 --seed 1001 --out bench/results/tune-planner.jsonl
//   npx tsx bench/tune.ts --strategy Planner --configs '[{...},{...}]' ...
//
// Objective: mean finishing place averaged over the fields (lower is better).

import * as fs from "node:fs";
import { Lexicon } from "../src/lexicon.js";
import { REGISTRY } from "./registry.js";
import { type Seat, intIn, mulberry32, runMatch } from "./sim.js";

const args = process.argv.slice(2);
const opt = (name: string, dflt: string): string => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] !== undefined ? args[i + 1]! : dflt;
};
const STRATEGY = opt("strategy", "Planner");
const N = Number(opt("n", "10"));
const SAMPLE_SEED = Number(opt("sample-seed", "1"));
const GAMES = Number(opt("games", "100"));
const SEED = Number(opt("seed", "1001"));
const OUT = opt("out", `bench/results/tune-${STRATEGY}.jsonl`);
const FIELDS = opt("fields", "ReportHi*5,PlannerRef*5,HeuristicA*5,PlannerRef*2+ReportHi+Aggressive+ValueBidder").split(",");
const FIRST_PRICE = args.includes("--first-price");

type Space = Record<string, [number, number, "int" | "real" | "log"]>;
const SPACES: Record<string, Space> = {
  Planner: {
    maxDeficit: [1, 3, "int"],
    winRate: [0.3, 0.95, "real"],
    pointsToBid: [0.5, 6, "log"],
    faceFloor: [0.5, 6, "log"],
    flatFloor: [0, 6, "real"],
    spendTarget: [1, 12, "log"],
    spendMin: [0.3, 1.5, "real"],
    spendMax: [1, 5, "real"],
    maxBidShare: [0.3, 1, "real"],
    holdMargin: [0.7, 1.5, "real"],
    minTargetLength: [4, 7, "int"],
  },
  // Live-market search: wider, higher bid ranges (live prices ~10-14/tile).
  PlannerLive: {
    maxDeficit: [1, 3, "int"],
    winRate: [0.3, 0.95, "real"],
    pointsToBid: [0.5, 8, "log"],
    faceFloor: [1, 6, "log"],
    flatFloor: [0, 14, "real"],
    spendTarget: [1, 12, "log"],
    spendMin: [0.5, 2, "real"],
    spendMax: [1, 4, "real"],
    maxBidShare: [0.3, 1, "real"],
    holdMargin: [0.8, 1.4, "real"],
    minTargetLength: [5, 7, "int"],
  },
  HeuristicA: {
    baseMultiplier: [1.5, 6, "log"],
    vowelPremium: [0, 8, "real"],
    commonPremium: [0, 4, "real"],
    balanceCorrection: [0, 12, "real"],
    duplicatePenalty: [0, 4, "real"],
    maxBid: [10, 60, "int"],
    primaryMinLength: [4, 8, "int"],
    pressureRackSize: [6, 14, "int"],
    emergencyMinLength: [3, 6, "int"],
  },
};

function sample(space: Space, rng: () => number): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [k, [lo, hi, kind]] of Object.entries(space)) {
    const u = rng();
    if (kind === "int") out[k] = Math.floor(lo + u * (hi - lo + 1));
    else if (kind === "log") out[k] = +Math.exp(Math.log(lo) + u * (Math.log(hi) - Math.log(lo))).toFixed(3);
    else out[k] = +(lo + u * (hi - lo)).toFixed(3);
  }
  return out;
}

const lexicon = Lexicon.fromFile(new URL("../../spacetimedb/wordlist.txt", import.meta.url));
const matchOpts = { lexicon, firstPrice: FIRST_PRICE, startingRack: 5, startingBalance: 100 };

function seatsFor(field: string): Seat[] {
  const seats: Seat[] = [];
  for (const part of field.split("+")) {
    const [n, k] = part.split("*");
    for (let i = 0; i < Number(k ?? 1); i++) {
      if (["Cheapskate", "ValueBidder", "Aggressive"].includes(n!)) {
        seats.push({ kind: "sim", style: n as "Aggressive" });
      } else {
        seats.push({ kind: "policy", policy: REGISTRY[n!]!({}) });
      }
    }
  }
  return seats;
}

function evaluate(params: Record<string, number>) {
  const hero = REGISTRY[STRATEGY === "PlannerLive" ? "Planner" : STRATEGY]!(params);
  const perField: Record<string, { place: number; win: number; score: number }> = {};
  for (const field of FIELDS) {
    const rng = mulberry32(SEED);
    let place = 0;
    let win = 0;
    let score = 0;
    for (let g = 0; g < GAMES; g++) {
      const seat = intIn(rng, 0, 5);
      const seats = seatsFor(field);
      seats.splice(seat, 0, { kind: "policy", policy: hero });
      const res = runMatch(seats, rng, matchOpts);
      const me = res[seat]!;
      place += me.place + 1;
      score += me.score;
      if (me.place === 0) win += 1 / res.filter((r) => r.place === 0).length;
    }
    perField[field] = { place: place / GAMES, win: win / GAMES, score: score / GAMES };
  }
  const objective = Object.values(perField).reduce((a, f) => a + f.place, 0) / FIELDS.length;
  return { objective, perField };
}

/** Perturb `base` by up to +-noise (relative), clamped to the space. */
function around(base: Record<string, number>, space: Space, noise: number, rng: () => number) {
  const out: Record<string, number> = { ...base };
  for (const [k, [lo, hi, kind]] of Object.entries(space)) {
    const v = base[k];
    if (v === undefined) continue;
    let x = v * (1 + noise * (2 * rng() - 1));
    if (kind === "int") x = Math.round(v + (rng() < 0.3 ? (rng() < 0.5 ? -1 : 1) : 0));
    out[k] = +Math.min(hi, Math.max(lo, x)).toFixed(3);
  }
  return out;
}

const configs: Record<string, number>[] = args.includes("--configs")
  ? JSON.parse(opt("configs", "[]"))
  : args.includes("--around")
    ? (() => {
        // Local refinement: --around '[{base1},{base2}]' --noise 0.25 --n 8
        const bases: Record<string, number>[] = JSON.parse(opt("around", "[]"));
        const noise = Number(opt("noise", "0.25"));
        const rng = mulberry32(SAMPLE_SEED);
        return Array.from({ length: N }, (_, i) => around(bases[i % bases.length]!, SPACES[STRATEGY]!, noise, rng));
      })()
    : (() => {
      const rng = mulberry32(SAMPLE_SEED);
      return Array.from({ length: N }, () => sample(SPACES[STRATEGY]!, rng));
    })();

fs.mkdirSync(new URL("./results/", import.meta.url), { recursive: true });
for (const params of configs) {
  const t0 = performance.now();
  const r = evaluate(params);
  const line = { strategy: STRATEGY, seed: SEED, games: GAMES, firstPrice: FIRST_PRICE, params, ...r, secs: +((performance.now() - t0) / 1000).toFixed(1) };
  fs.appendFileSync(OUT, JSON.stringify(line) + "\n");
  console.log(`${r.objective.toFixed(3)} ${JSON.stringify(params)}`);
}
