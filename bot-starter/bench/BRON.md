# Bron public-match profile

Bot **Bron (114)**. Latest **100 completed matches**, IDs 43142–45590, 2026-11-07T23:52:25.617Z to 2026-11-08T01:55:58.876Z. No bot-version reset rows were found. The profile describes observed behavior, not recovered source code.

## Performance

- Mean score **89.92**, descriptive 95% normal interval [85.59, 94.25]; median 87.00, range 50–159.
- Latest 10 mean **100.80**; previous 90 mean **88.71**. Small recent samples and different opponents limit inference.
- Mean place **2.66**; 25 outright wins, 2 tied firsts; tie-split win share 26.0%.
- Mean auction tiles won **13.62**, spend **163.47**, ending coins **26.45**.
- Pooled points per played tile **5.02**, including the free starting rack.

## Word timing and selection

306 observed word plays. Length histogram: {"2":32,"3":24,"4":18,"5":23,"6":30,"7":146,"8":31,"9":2}. 293/306 match the best available immediate reward in reconstructed racks. 97/100 starting racks have all five letters forced by public prefix constraints; other rack states use feasible samples.

Bron frequently plays seven-letter words well below 45 points, including healthy-cash plays such as GREENIE (24, 82 coins), DAILIES (24, 86), and ARTIEST (21, 42). LexForge-Base-v1's 45-point primary gate therefore does **not** describe Bron. Bron also plays 8/9-letter words; there is no universal seven-letter maximum in this sample.

Only 10 plays shorter than seven letters occurred with more than five future tiles: 8 had at most 10 coins, while DOUMA (16 points, 37 coins, 26 left) and ZOOTY (34, 41 coins, 22 left) are counterexamples to a simple low-cash-only rule. A dynamic future-word valuation or other state-dependent rule is plausible, but public evidence does not identify it uniquely.

All 74 two-to-four-letter plays occurred with zero tiles behind the open auction. This differs from LexForge-Base-v1, whose small dumps usually occurred one auction earlier. Median elapsed time from the previous tile Bron won to a word play is 195.59 ms (90th percentile 5126.00 ms); these times mix opportunity, batching and latency.

## Acquisition and budget pacing

Last-auction wins are separated because an external client cannot play that tile and all-in bids distort normal price statistics.

| Phase (auction indices) | Wins | Tiles/match | Mean winning bid | Mean paid |
|---|---:|---:|---:|---:|
| early | 398 | 3.98 | 14.47 | 12.54 |
| middle | 430 | 4.30 | 13.87 | 11.57 |
| late | 534 | 5.34 | 16.68 | 11.95 |
| final | 0 | 0.00 | — | — |

| Tile group (excluding final auction) | Wins | Tiles/match | Mean winning bid | Mean paid |
|---|---:|---:|---:|---:|
| vowels | 592 | 5.92 | 12.84 | 10.02 |
| 1-point consonants | 343 | 3.43 | 13.20 | 10.21 |
| 2–5 point letters | 371 | 3.71 | 18.57 | 15.12 |
| 8–10 point letters | 56 | 0.56 | 28.82 | 23.34 |

## Per-letter winning bids

These describe tiles Bron **won**, not its unconditional bidding policy. Missing archives stay missing; paid is not substituted for a bid. Last auctions are excluded.

| Letter | Wins | Bid P25 | Median bid | Bid P75 | Mean paid |
|---|---:|---:|---:|---:|---:|
| A | 126 | 10.00 | 12.00 | 15.00 | 10.33 |
| B | 32 | 16.00 | 17.00 | 21.00 | 15.38 |
| C | 28 | 17.00 | 18.00 | 20.00 | 15.36 |
| D | 53 | 13.00 | 14.00 | 18.00 | 12.64 |
| E | 169 | 11.00 | 12.00 | 15.00 | 10.46 |
| F | 34 | 18.00 | 20.00 | 24.00 | 16.03 |
| G | 45 | 12.00 | 15.00 | 16.00 | 12.11 |
| H | 22 | 18.00 | 20.00 | 22.00 | 17.64 |
| I | 136 | 10.00 | 12.00 | 15.00 | 9.67 |
| J | 12 | 23.00 | 28.00 | 30.00 | 25.00 |
| K | 16 | 19.00 | 26.00 | 28.00 | 19.19 |
| L | 57 | 10.00 | 12.00 | 15.00 | 10.39 |
| M | 33 | 17.00 | 19.00 | 22.00 | 15.61 |
| N | 80 | 10.00 | 12.00 | 15.00 | 10.05 |
| O | 113 | 10.00 | 11.00 | 13.00 | 9.75 |
| P | 31 | 15.00 | 18.00 | 20.00 | 15.55 |
| Q | 18 | 15.00 | 24.00 | 35.00 | 19.94 |
| R | 80 | 10.00 | 12.00 | 13.00 | 9.76 |
| S | 51 | 12.00 | 14.00 | 16.00 | 11.94 |
| T | 75 | 10.00 | 11.00 | 13.00 | 9.53 |
| U | 48 | 10.00 | 12.00 | 14.00 | 9.23 |
| V | 24 | 14.00 | 19.00 | 22.00 | 14.50 |
| W | 27 | 17.00 | 20.00 | 22.00 | 16.11 |
| X | 12 | 30.00 | 32.00 | 33.00 | 25.67 |
| Y | 26 | 18.00 | 21.00 | 23.00 | 17.42 |
| Z | 14 | 25.00 | 31.00 | 33.00 | 24.29 |

## Actual shared matchups

“Above” means a strictly higher score, with ties separate. Comparisons are paired within the same table; bots appear different numbers of times.

| Opponent | Met | Bron mean | Opponent mean | Bron above | Tied |
|---|---:|---:|---:|---:|---:|
| StickBot (180) | 23 | 92.17 | 82.65 | 16/23 | 0 |
| Jaeger (167) | 22 | 85.00 | 77.55 | 14/22 | 0 |
| LUCENT (18) | 20 | 90.20 | 91.75 | 11/20 | 1 |
| RackMaw (193) | 18 | 77.33 | 88.67 | 4/18 | 1 |
| Nigel "Bidderson" Richards (205) | 16 | 93.00 | 69.13 | 12/16 | 1 |
| monkey (185) | 16 | 89.63 | 40.69 | 15/16 | 0 |
| QuertyBot (183) | 16 | 86.19 | 64.19 | 14/16 | 0 |
| bot1717 (204) | 16 | 90.81 | 47.19 | 15/16 | 0 |
| Rowin'Boats (202) | 15 | 85.00 | 85.80 | 6/15 | 0 |
| exzell (179) | 14 | 96.00 | 87.50 | 7/14 | 1 |
| LexiconWarrior (181) | 14 | 92.79 | 96.43 | 7/14 | 0 |
| Sigma (219) | 13 | 99.00 | 19.77 | 13/13 | 0 |
| Abhi-AuctionLab (169) | 13 | 87.46 | 81.00 | 8/13 | 0 |
| NigelBot (194) | 13 | 88.31 | 67.08 | 10/13 | 1 |
| Primey (191) | 12 | 88.33 | 88.58 | 4/12 | 0 |
| Malicious (168) | 11 | 92.82 | 85.45 | 7/11 | 0 |
| TileHoarder (187) | 11 | 78.73 | 69.18 | 7/11 | 0 |
| Lexicoin (199) | 11 | 100.18 | 76.27 | 9/11 | 0 |
| Tow57-Auctioneer (164) | 10 | 84.50 | 76.80 | 5/10 | 0 |
| Lbender (201) | 10 | 81.30 | 120.50 | 2/10 | 0 |
| SevenUp (215) | 10 | 82.00 | 87.90 | 3/10 | 0 |
| Nhat (206) | 10 | 90.90 | 41.30 | 9/10 | 0 |
| Odysseus's Voyage (172) | 9 | 97.78 | 76.33 | 7/9 | 1 |
| GodOfThudner (171) | 9 | 94.11 | 100.44 | 2/9 | 0 |
| aipom (192) | 9 | 84.33 | 101.56 | 2/9 | 0 |
| Cruds (217) | 9 | 80.67 | 37.11 | 8/9 | 0 |
| wordgoat (175) | 9 | 82.78 | 92.89 | 3/9 | 0 |
| Lexiconda (225) | 9 | 86.67 | 72.33 | 5/9 | 0 |
| SoapConsumers (166) | 8 | 88.38 | 60.75 | 7/8 | 0 |
| Lucy (186) | 8 | 69.75 | 85.75 | 2/8 | 0 |
| Afterword (145) | 8 | 105.88 | 0.00 | 8/8 | 0 |
| GoatBot (213) | 8 | 95.00 | 80.13 | 7/8 | 0 |
| rackpilot-live (220) | 7 | 109.57 | 28.57 | 7/7 | 0 |
| peanuts (188) | 7 | 91.00 | 58.29 | 6/7 | 0 |
| CoolBotYay (221) | 7 | 90.14 | 84.57 | 4/7 | 0 |
| cosine (165) | 6 | 90.50 | 68.33 | 4/6 | 0 |
| Astronaut (212) | 6 | 85.67 | 72.50 | 4/6 | 0 |
| CasualThinker (203) | 6 | 104.00 | 41.00 | 6/6 | 0 |
| Bot (161) | 6 | 95.50 | 61.50 | 5/6 | 0 |
| gas (178) | 5 | 86.40 | 81.00 | 3/5 | 0 |
| Babbler (177) | 5 | 94.00 | 0.00 | 5/5 | 0 |
| Mavvy (226) | 4 | 94.00 | 72.75 | 3/4 | 0 |
| scrabblemaxxing (182) | 4 | 98.50 | 89.25 | 2/4 | 0 |
| Jake (230) | 4 | 95.00 | 69.50 | 3/4 | 1 |
| Mr. Turkey (198) | 4 | 84.75 | 41.75 | 4/4 | 0 |
| Binter (163) | 3 | 117.00 | 25.00 | 3/3 | 0 |
| evol (211) | 3 | 108.67 | 38.67 | 3/3 | 0 |
| megatron pro max plus ultra 3000 (173) | 3 | 103.33 | 19.33 | 3/3 | 0 |
| Karppa (190) | 3 | 79.00 | 75.33 | 2/3 | 0 |
| LexForge-Base-v1 (224) | 2 | 73.50 | 99.00 | 0/2 | 0 |
| Pegasus (208) | 2 | 81.50 | 26.00 | 2/2 | 0 |

## Comparison with the LexForge study

Bron's sampled overall mean is 89.92 vs LexForge-Base-v1's earlier 34-match 107.68. Bron's pooled conversion is 5.02 vs 5.76. These are **different match sets and periods**, so this is not a controlled ranking. Bron's latest-10 mean of 100.80 is closer to the 100-point goal than its full-window mean. The shared-table section is the appropriate direct evidence where overlap exists.

Actionable research candidates: compare Bron's earlier/cheaper seven-letter cash-ins against the LexForge 45-point gate, and compare final-only small-word liquidation against the one-auction buffer. Neither change is adopted automatically. The playing bot is unchanged.

## Evidence and reproduction

```sh
REPLAY_INPUT_OUT=bench/results/viability/bron-input.json node --import tsx bench/live/fetch-replay.mts 100 114
STUDY_BOT=114 STUDY_IN=bench/results/viability/bron-input.json STUDY_OUT=bench/results/viability/bron-observations.json node --import tsx bench/live/study-lexforge.mts
node --import tsx bench/live/profile-bron.mts
```

Pinned input, reconstructed observations and structured profile are under `bench/results/viability/bron-*.json`. Refetching changes the sample. No source-code or exact losing-bid recovery is claimed.
