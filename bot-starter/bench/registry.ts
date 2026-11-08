// Strategies the experiment runner can seat, by name. Each factory takes
// optional numeric parameter overrides (from --params).

import { conversion, MARKET7V_PARAMS } from "../src/strategies/conversion.js";
import type { Policy } from "../src/policy.js";
import { REPORT_PARAMS, reportHybrid, starter } from "../src/strategies/baselines.js";
import { withEndgame } from "../src/strategies/endgame.js";
import { LIVE_BOTS, mimic } from "../src/strategies/mimic.js";
import { planner } from "../src/strategies/planner.js";
import { market } from "../src/strategies/market.js";

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
