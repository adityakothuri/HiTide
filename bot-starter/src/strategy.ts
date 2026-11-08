// The strategy the live bot plays. Chosen by the experiments in
// bench/EXPERIMENTS.md; swap it with STRATEGY=<name> for comparisons.

import { lexforge } from "./strategies/lexforge.js";
import { rush } from "./strategies/rush.js";
import { conversion } from "./strategies/conversion.js";
import { portfolio, TUNED_PARAMS } from "./strategies/portfolio.js";
export { PARAMS, TUNED_PARAMS, decideBid, chooseWord } from "./strategies/portfolio.js";
import type { Policy } from "./policy.js";
import { REPORT_PARAMS, reportHybrid, starter } from "./strategies/baselines.js";
import { withEndgame } from "./strategies/endgame.js";
import { planner } from "./strategies/planner.js";
import { market } from "./strategies/market.js";

// Planner P1: best configuration of tuning round 1 (E4) and the best on
// fresh validation games (E5: mean place 1.068 over four tough fields).
// Provisional until round 2 and the final validation finish.
export const FINAL_PARAMS = {
  maxDeficit: 3, winRate: 0.729, pointsToBid: 1.981, faceFloor: 2.622, flatFloor: 4.89,
  spendTarget: 6.325, spendMin: 0.823, spendMax: 1.237, maxBidShare: 0.762, holdMargin: 1.111,
  minTargetLength: 6,
};

// HA2: Strategy A (report heuristic with live-level bids + endgame cash-in),
// best of tuning round 2 (E6); strongest against live-calibrated opponents.
export const HA2_PARAMS = {
  ...REPORT_PARAMS,
  baseMultiplier: 4.116, vowelPremium: 5.561, commonPremium: 2.651, balanceCorrection: 7.396,
  duplicatePenalty: 3.848, maxBid: 33, primaryMinLength: 8, pressureRackSize: 9, emergencyMinLength: 3,
};

// L1: planner tuned against live-calibrated opponents (budget-aware copies
// of the server's top bots, E9): mean place 2.106 vs HA2's 2.981 there.
export const L1_PARAMS = {
  maxDeficit: 1, winRate: 0.733, pointsToBid: 1.222, faceFloor: 2.414, flatFloor: 4.374,
  spendTarget: 5.606, spendMin: 1.338, spendMax: 3.241, maxBidShare: 0.987, holdMargin: 1.059,
  minTargetLength: 5,
};

/** Numeric LexForge overrides from FORGE_OVERRIDES (JSON); invalid input fails fast. */
function forgeOverrides(): Record<string, number> {
  const raw = process.env.FORGE_OVERRIDES;
  if (!raw) return {};
  const parsed: unknown = JSON.parse(raw);
  if (!parsed || typeof parsed !== "object" || Object.values(parsed).some(v => typeof v !== "number" || !Number.isFinite(v)))
    throw new Error("FORGE_OVERRIDES must be a JSON object of finite numbers");
  return parsed as Record<string, number>;
}

export const CHOICES: Record<string, () => Policy> = {
  // Larper: LexForge plus coin-starvation fixes. Below 10 coins it cashes in its
  // best 5+ letter word; below 7 coins it cashes any word so it can keep bidding.
  // Replay on 38 of bot 259's live matches: +2.6..+3.0 points/match vs lexforge.
  larper: () => lexforge({ cashBalance: 10, desperateBalance: 7, desperateMinLength: 2 }, "Larper"),
  // Forge: LexForge tuned in the live-market replay (100 Pegasus matches, 70/30
  // split): noiseless bids x1.35-2, no forced liquidation, cash in below 10 coins.
  // Replay: 87-88 points/match vs 76-78 for lexforge.
  forge: () => lexforge({ noise: 0, bidScale: 1.35, bidShift: -2, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2 }, "Forge"),
  // Experimental Forge: FORGE_OVERRIDES='{"bidScale":1.25}' layers replay-tested settings on top.
  forgex: () => lexforge({ noise: 0, bidScale: 1.35, bidShift: -2, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2, ...forgeOverrides() }, "ForgeX"),
  // Larper v2: Forge with bids at 1.5x the fitted LexForge model (no shift).
  // The live copy underbid high-value letters (Z/Q/X ~20 vs ~45 paid by real
  // LexForge). Replay over 4 match sets (bots 224/253/259/285): 89.1 points/match
  // vs 88.8 Forge and 83.5 Larper v1. Gain over Forge is within noise; run live as an A/B.
  larperv2: () => lexforge({ noise: 0, bidScale: 1.5, bidShift: 0, liquidateAt: 0, cashBalance: 10, desperateBalance: 10, desperateMinLength: 2 }, "LarperV2"),
  lexforge: () => lexforge(),
  lexforgeTrees: () => lexforge({ useTrees: 1 }, "LexForgeTrees"),
  lexforgeMean: () => lexforge({ noise: 0 }, "LexForgeMean"),
  lexforgeHalfNoise: () => lexforge({ noise: .5 }, "LexForgeHalfNoise"),
  rush: () => rush(),
  rush4: () => rush({}, "MarketRush4", 4),
  // Research candidate: Market7V + bounded cash-in and completion funding.
  market7vc: () => conversion(),
  market7vf: () => conversion({ cashInRegimes: 0, cashBalance: 12, cashMinLength: 5 }, "Market7VF"),
  portfolio: () => portfolio(),
  portfolioTuned: () => portfolio(TUNED_PARAMS, "PortfolioTuned"),
  // Strategy D: bids anchored to live winning-bid prices + planner (L1) play.
  market: () => market({}, "Market"),
  // Strategy D with budget pacing (K=12) and cash-in when broke.
  marketp: () => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5 }, "MarketP12"),
  // E11: like the strongest live bot: aim for 7-letter words (never longer
  // before the final auction) and pay up for 2-5 point letters.
  market7g: () => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, plan: { maxWordLength: 7 } }, "Market7G"),
  // + pacing cap scaled by letter value (live: 4-10 pt letters were capped
  // at bids of 8-14 against market prices of 20-39, so it won none).
  // + cash in a 4+ letter word whenever the balance drops below 35, so
  // income keeps funding bids (live: bids stuck at 9 for 30 auctions).
  market7vb: () => market({ paceK: 12, paceFaceBoost: 0.5, brokeBalance: 35, brokeMinLength: 4, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, plan: { maxWordLength: 7 } }, "Market7Vb"),
  market7v: () => market({ paceK: 12, paceFaceBoost: 0.5, brokeBalance: 12, brokeMinLength: 5, anchor1pt: 0.85, anchorMid: 1.2, anchorHigh: 1.1, plan: { maxWordLength: 7 } }, "Market7V"),
  // + word choice by reward + leftover potential, best final word set.
  marketps: () => market({ paceK: 12, brokeBalance: 12, brokeMinLength: 5, plan: { playSearch: 25 } }, "MarketPS"),
  l1: () => planner(L1_PARAMS, "L1"),
  ha2: () => withEndgame(reportHybrid(HA2_PARAMS, "HA2"), "HA2"),
  final: () => planner(FINAL_PARAMS, "Final"),
  starter: () => starter,
  report: () => reportHybrid(REPORT_PARAMS),
};

export const STRATEGY: Policy = (CHOICES[process.env.STRATEGY ?? "larper"] ?? CHOICES.larper!)();
