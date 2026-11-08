// Strategies the experiment runner can seat, by name. Each factory takes
// optional numeric parameter overrides (from --params).

import { conversion, MARKET7V_PARAMS } from "../src/strategies/conversion.js";
import type { Policy } from "../src/policy.js";
import { REPORT_PARAMS, reportHybrid, starter } from "../src/strategies/baselines.js";
import { withEndgame } from "../src/strategies/endgame.js";
import { LIVE_BOTS, mimic } from "../src/strategies/mimic.js";
import { planner } from "../src/strategies/planner.js";
import { market } from "../src/strategies/market.js";
import { lexforge } from "../src/strategies/lexforge.js";
import { lexforgeOpt } from "../src/strategies/lexforgeOpt.js";
import { imitationPolicy, type ImitationModel } from "../src/fleetPolicy.js";
import { existsSync, readdirSync, readFileSync } from "node:fs";

// Frozen fleet clones (fleet/models/Pegasus-v*.json), seated as "F-va" … "F-vj".
const FLEET_DIR = new URL("../fleet/models/", import.meta.url);
export const FLEET_NAMES: string[] = existsSync(FLEET_DIR)
  ? readdirSync(FLEET_DIR).filter((f) => /^Pegasus-v[a-z]+\.json$/.test(f)).map((f) => `F-${f.slice(8, -5)}`).sort()
  : [];
const fleet: Record<string, Factory> = Object.fromEntries(
  FLEET_NAMES.map((n) => {
    const model = JSON.parse(readFileSync(new URL(`Pegasus-${n.slice(2)}.json`, FLEET_DIR), "utf8")) as ImitationModel;
    return [n, () => ({ ...imitationPolicy(model), name: n })];
  }),
);

type Factory = (overrides: Record<string, number>) => Policy;

const REPORT_HI = { ...REPORT_PARAMS, baseMultiplier: 3, maxBid: 40, vowelPremium: 4 };

// Best hand-picked planner from E3; a fixed self-play opponent for tuning.
export const PLANNER_REF = { pointsToBid: 3, faceFloor: 3, flatFloor: 3, maxBidShare: 0.8 };

// Live-bot copies; MIMIC_SHRINK corrects for winners' bids being biased high.
export const MIMIC_SHRINK = Number(process.env.MIMIC_SHRINK ?? 0.85);
const mimics: Record<string, Factory> = Object.fromEntries(
  Object.entries(LIVE_BOTS).flatMap(([n, q]) => [
    [`M-${n}`, (o: Record<string, number>) => mimic({ ...q, shrink: MIMIC_SHRINK, ...o }, `M-${n}`)],
    // Same bids, strong play: closer to how the real bots convert tiles.
    [`S-${n}`, (o: Record<string, number>) => mimic({ ...q, shrink: MIMIC_SHRINK, smartPlay: 1, ...o }, `S-${n}`)],
    // Same bids and play, but budget-aware (bids scale with money per auction left).
    [`B-${n}`, (o: Record<string, number>) => mimic({ ...q, shrink: MIMIC_SHRINK, smartPlay: 1, budgetTau: Number(process.env.BUDGET_TAU ?? 4), ...o }, `B-${n}`)],
  ]),
);

// Planner P1 (validated best of round 1) and bid-level variants of it.
export const P1 = {
  maxDeficit: 3, winRate: 0.729, pointsToBid: 1.981, faceFloor: 2.622, flatFloor: 4.89,
  spendTarget: 6.325, spendMin: 0.823, spendMax: 1.237, maxBidShare: 0.762, holdMargin: 1.111, minTargetLength: 6,
};
const scaled = (k: number) => ({ ...P1, pointsToBid: P1.pointsToBid * k, faceFloor: P1.faceFloor * k, flatFloor: P1.flatFloor * k });
// Best Strategy A from round 2 (E6).
export const HA2 = {
  baseMultiplier: 4.116, vowelPremium: 5.561, commonPremium: 2.651, balanceCorrection: 7.396, duplicatePenalty: 3.848,
  maxBid: 33, primaryMinLength: 8, pressureRackSize: 9, emergencyMinLength: 3,
};

export const REGISTRY: Record<string, Factory> = {
  ...mimics,
  ...fleet,
  LexForgeObserved: (o) => lexforge(o),
  LexOpt: (o) => lexforgeOpt(o, "LexOpt"),
  LexOptLate: (o) => lexforgeOpt({ lowCashPlay: 10, endgameStart: 3, paceBalance: 0, desperateBalance: 7, ...o }, "LexOptLate"),
  LexOptLateB: (o) => lexforgeOpt({ lowCashPlay: 10, endgameStart: 3, paceBalance: 0, desperateBalance: 7, bidScale: 2.0, ...o }, "LexOptLateB"),
  // Fallback variants: under N coins with nothing qualifying, play any word of length >= L.
  LexD10: (o) => lexforge({ desperateBalance: 10, desperateMinLength: 2, ...o }, "LexD10"),
  LexD10L3: (o) => lexforge({ desperateBalance: 10, desperateMinLength: 3, ...o }, "LexD10L3"),
  LexD10L4: (o) => lexforge({ desperateBalance: 10, desperateMinLength: 4, ...o }, "LexD10L4"),
  LexD5: (o) => lexforge({ desperateBalance: 5, desperateMinLength: 2, ...o }, "LexD5"),
  LexD7C12: (o) => lexforge({ desperateBalance: 7, desperateMinLength: 2, cashBalance: 12, ...o }, "LexD7C12"),
  LexD7C10: (o) => lexforge({ desperateBalance: 7, desperateMinLength: 2, cashBalance: 10, ...o }, "LexD7C10"),
  LexF08: (o) => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2, floorScale: 0.8, floorReserve: 1.5, ...o }, "LexF08"),
  LexF10: (o) => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2, floorScale: 1.0, floorReserve: 1.5, ...o }, "LexF10"),
  LexF12: (o) => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2, floorScale: 1.2, floorReserve: 1.5, ...o }, "LexF12"),
  LexF10r1: (o) => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2, floorScale: 1.0, floorReserve: 1.0, ...o }, "LexF10r1"),
  LexF10r2: (o) => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2, floorScale: 1.0, floorReserve: 2.0, ...o }, "LexF10r2"),
  LexF06: (o) => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2, floorScale: 0.6, floorReserve: 1.5, ...o }, "LexF06"),
  larper: (o) => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2, ...o }, "Larper"),
  G135: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.35, bidShift: -2, ...o }, "G135"),
  G120: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.2, bidShift: -2, ...o }, "G120"),
  G150: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.5, bidShift: -2, ...o }, "G150"),
  G165: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.65, bidShift: -2, ...o }, "G165"),
  G150s0: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.5, bidShift: 0, ...o }, "G150s0"),
  G150f6: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.5, bidShift: -2, floorScale: 0.6, ...o }, "G150f6"),
  G150L3: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.5, bidShift: -2, liquidateAt: 1, ...o }, "G150L3"),
  G150P50: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.5, bidShift: -2, primaryMinScore: 50, ...o }, "G150P50"),
  G150P40: (o) => lexforge({ noise: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, bidScale: 1.5, bidShift: -2, primaryMinScore: 40, ...o }, "G150P40"),
  LexD3: (o) => lexforge({ desperateBalance: 3, desperateMinLength: 2, ...o }, "LexD3"),
  LexD7: (o) => lexforge({ desperateBalance: 7, desperateMinLength: 2, ...o }, "LexD7"),
  LexD5L3: (o) => lexforge({ desperateBalance: 5, desperateMinLength: 3, ...o }, "LexD5L3"),
  LexD5Liq2: (o) => lexforge({ desperateBalance: 5, desperateMinLength: 2, liquidateAt: 2, ...o }, "LexD5Liq2"),
  LexD5Liq3: (o) => lexforge({ desperateBalance: 5, desperateMinLength: 2, liquidateAt: 3, ...o }, "LexD5Liq3"),
  LexD5C12: (o) => lexforge({ desperateBalance: 5, desperateMinLength: 2, cashBalance: 12, ...o }, "LexD5C12"),
  LexD5C20: (o) => lexforge({ desperateBalance: 5, desperateMinLength: 2, cashBalance: 20, ...o }, "LexD5C20"),
  // Coin-starvation fixes: cash in earlier (C), pace bids when low (P), or both.
  LexC30: (o) => lexforge({ cashBalance: 30, recoveryMinLength: 4, desperateBalance: 10, desperateMinLength: 2, ...o }, "LexC30"),
  LexC40: (o) => lexforge({ cashBalance: 40, recoveryMinLength: 4, desperateBalance: 10, desperateMinLength: 2, ...o }, "LexC40"),
  LexC25L5: (o) => lexforge({ cashBalance: 25, desperateBalance: 10, desperateMinLength: 3, ...o }, "LexC25L5"),
  LexP30: (o) => lexforge({ paceBalance: 30, paceShare: 0.3, desperateBalance: 10, desperateMinLength: 2, ...o }, "LexP30"),
  LexP40: (o) => lexforge({ paceBalance: 40, paceShare: 0.25, desperateBalance: 10, desperateMinLength: 2, ...o }, "LexP40"),
  LexCP30: (o) => lexforge({ cashBalance: 30, recoveryMinLength: 4, paceBalance: 30, paceShare: 0.3, desperateBalance: 10, desperateMinLength: 2, ...o }, "LexCP30"),
  LexCP25: (o) => lexforge({ cashBalance: 25, paceBalance: 30, paceShare: 0.35, desperateBalance: 10, desperateMinLength: 3, ...o }, "LexCP25"),
  Market7V: () => market(MARKET7V_PARAMS, "Market7V"),
  Market7Vb: () => market({ ...MARKET7V_PARAMS, brokeBalance: 35, brokeMinLength: 4 }, "Market7Vb"),
  Market7VC: (o) => conversion(o),
  Market7VF: (o) => conversion({ cashInRegimes: 0, cashBalance: 12, cashMinLength: 5, ...o }, "Market7VF"),
  // Strategy D: market-anchored bids + planner play.
  // Flat overrides; keys "plan_<name>" go to the planner settings.
  Market: (o) => {
    const plan: Record<string, number> = {};
    const top: Record<string, number> = {};
    for (const [k, v] of Object.entries(o)) {
      if (k.startsWith("plan_")) plan[k.slice(5)] = v;
      else top[k] = v;
    }
    return market({ ...top, plan });
  },
  "Market1.2": (o) => market({ anchor: 1.2, ...o }, "Market1.2"),
  MarketP: (o) => market({ paceK: 8, brokeBalance: 12, brokeMinLength: 5, ...o }, "MarketP"),
  MarketP12: (o) => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5, ...o }, "MarketP12"),
  // E11: GodOfThudner-style: 7-letter cap, pay up for 2-5 pt letters.
  Market7: (o) => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5, plan: { maxWordLength: 7 }, ...o }, "Market7"),
  Market7G: (o) => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, plan: { maxWordLength: 7 }, ...o }, "Market7G"),
  Market7V: (o) => market({ paceK: 12, paceFaceBoost: 0.5, brokeBalance: 12, brokeMinLength: 5, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, plan: { maxWordLength: 7 }, ...o }, "Market7V"),
  Market7Vb: (o) => market({ paceK: 12, paceFaceBoost: 0.5, brokeBalance: 35, brokeMinLength: 4, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, plan: { maxWordLength: 7 }, ...o }, "Market7Vb"),
  Market7Vc: (o) => market({ paceK: 12, paceFaceBoost: 0.5, brokeBalance: 25, brokeMinLength: 4, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, plan: { maxWordLength: 7 }, ...o }, "Market7Vc"),
  MarketG: (o) => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, ...o }, "MarketG"),
  MarketPS: (o) => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5, plan: { playSearch: 25 }, ...o }, "MarketPS"),
  MarketP5: (o) => market({ paceK: 5, brokeBalance: 12, brokeMinLength: 4, ...o }, "MarketP5"),
  "Market0.9": (o) => market({ anchor: 0.9, ...o }, "Market0.9"),
  L1: () => planner({ maxDeficit: 1, winRate: 0.733, pointsToBid: 1.222, faceFloor: 2.414, flatFloor: 4.374, spendTarget: 5.606, spendMin: 1.338, spendMax: 3.241, maxBidShare: 0.987, holdMargin: 1.059, minTargetLength: 5 }, "L1"),
  P1: (o) => planner({ ...P1, ...o }, "P1"),
  "P1x1.5": (o) => planner({ ...scaled(1.5), ...o }, "P1x1.5"),
  P1x2: (o) => planner({ ...scaled(2), ...o }, "P1x2"),
  "P1x2.5": (o) => planner({ ...scaled(2.5), ...o }, "P1x2.5"),
  // Calibration opponents: P1 at bid level PK (env), to match live prices.
  PK: (o) => planner({ ...scaled(Number(process.env.PK ?? 1.5)), ...o }, "PK"),
  HA2: (o) => withEndgame(reportHybrid({ ...REPORT_PARAMS, ...HA2, ...o }, "HA2"), "HA2"),
  Starter: () => starter,
  Report: (o) => reportHybrid({ ...REPORT_PARAMS, ...o }),
  // The report's heuristic at the E2 bid level.
  ReportHi: (o) => reportHybrid({ ...REPORT_HI, ...o }, "ReportHi"),
  // Strategy A: ReportHi plus the endgame cash-in.
  HeuristicA: (o) => withEndgame(reportHybrid({ ...REPORT_HI, ...o }, "ReportHi"), "HeuristicA"),
  // Strategy B.
  Planner: (o) => planner(o),
  PlannerRef: () => planner(PLANNER_REF, "PlannerRef"),
};
