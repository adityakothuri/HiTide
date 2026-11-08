// Checks for the live strategy. Run with `npm test`.

import assert from "node:assert/strict";
import { test } from "node:test";
import { BAG_COUNTS, Lexicon, countsFromString, wordReward } from "./lexicon.js";
import type { MatchView } from "./policy.js";
import { STRATEGY } from "./strategy.js";

const LEXICON = Lexicon.fromFile(new URL("../../spacetimedb/wordlist.txt", import.meta.url));

function view(over: Partial<MatchView> & { rackLetters?: string }): MatchView {
  const rack = countsFromString(over.rackLetters ?? "");
  const unseen = new Uint8Array(BAG_COUNTS);
  return {
    letter: "E",
    auctionsLeft: 40,
    balance: 100,
    score: 0,
    rack,
    opponents: Array.from({ length: 5 }, () => ({ balance: 100, score: 0 })),
    unseen,
    unseenTotal: unseen.reduce((a, b) => a + b, 0),
    firstPrice: false,
    history: [],
    lexicon: LEXICON,
    ...over,
  };
}

test("wordReward matches the server's length multipliers", () => {
  assert.equal(wordReward("CAT"), 5);      // 5 x 1
  assert.equal(wordReward("QUIZ"), 33);    // 22 x 1.5
  assert.equal(wordReward("PLANETS"), 27); // 9 x 3
});

test("bids are whole numbers within the balance", () => {
  for (const letter of "AEQZXKST") {
    for (const balance of [0, 1, 7, 100, 400]) {
      for (const auctionsLeft of [0, 1, 30, 67]) {
        const b = STRATEGY.bid(view({ letter, balance, auctionsLeft, rackLetters: "AERTSQ" }));
        assert.ok(Number.isInteger(b) && b >= 0 && b <= balance, `${letter} ${balance} ${auctionsLeft} -> ${b}`);
      }
    }
  }
});

test("words played are in the dictionary and use only rack letters", () => {
  const rack = "RETAINSXQ";
  const word = STRATEGY.play(view({ rackLetters: rack, auctionsLeft: 0 }));
  assert.ok(word && LEXICON.has(word));
  const have = countsFromString(rack);
  for (const c of word) assert.ok(have[c.charCodeAt(0) - 65]!-- > 0);
});

test("the final auction cashes in tiles and spends the balance", () => {
  // The match ends when the last auction closes, so tiles become worthless.
  assert.ok(STRATEGY.play(view({ rackLetters: "CAT", auctionsLeft: 0 })));
  assert.equal(STRATEGY.bid(view({ balance: 57, auctionsLeft: 0 })), 57);
});

test("an empty rack plays nothing", () => {
  assert.equal(STRATEGY.play(view({ rackLetters: "" })), null);
});

// The bot can't see a match move on while it decides, so decisions must
// stay far below the 1-second auction.
test("decisions stay well within an auction on big racks", () => {
  const racks = ["BCDFGHJKLMNPQRSTVWXZ", "AEIOUAEIOUAEIOURSTLN", "EEEEAAAIIIOORRSSTTNL"];
  for (const rackLetters of racks) {
    for (const letter of "EQS") {
      const start = performance.now();
      STRATEGY.bid(view({ rackLetters, letter }));
      STRATEGY.play(view({ rackLetters }));
      assert.ok(performance.now() - start < 250, `${rackLetters}/${letter} took too long`);
    }
  }
});

// Edge cases, for every strategy the live bot can run.
import { CHOICES } from "./strategy.js";

const EDGE_RACKS = ["", "Q", "QQQQ", "EEEEEEEEEE", "QZXJK", "AEIOUAEIOUAEIOUAEIOU", "BCDFGHJKLMNPQRSTVWXZAEIOU", "RETAINS", "QUIZZES"];

test("every strategy makes legal, fast decisions on edge cases", () => {
  for (const [name, make] of Object.entries(CHOICES)) {
    const s = make();
    // Warm up (first calls compile the code), so timings measure play speed.
    for (const rackLetters of EDGE_RACKS) s.play(view({ rackLetters }));
    for (const rackLetters of EDGE_RACKS) {
      for (const balance of [0, 1, 2, 37, 500]) {
        for (const auctionsLeft of [0, 1, 67]) {
          for (const firstPrice of [false, true]) {
            for (const empty of [false, true]) {
              const unseen = empty ? new Uint8Array(26) : new Uint8Array(BAG_COUNTS);
              const v = view({
                rackLetters, balance, auctionsLeft, firstPrice, letter: "Q",
                unseen, unseenTotal: unseen.reduce((a, b) => a + b, 0),
                history: Array.from({ length: empty ? 67 : 0 }, (_, i) => ({ slot: i % 26, paid: i % 30, mine: i % 5 === 0 })),
              });
              const t0 = performance.now();
              const bid = s.bid(v);
              assert.ok(Number.isInteger(bid) && bid >= 0 && bid <= balance, `${name}: bid ${bid} with balance ${balance}`);
              const word = s.play({ ...v, letter: "" });
              if (word !== null) {
                assert.ok(LEXICON.has(word), `${name}: '${word}' not a word`);
                const have = countsFromString(rackLetters);
                for (const c of word) assert.ok(have[c.charCodeAt(0) - 65]!-- > 0, `${name}: '${word}' not on rack ${rackLetters}`);
              }
              assert.ok(performance.now() - t0 < 100, `${name}: slow on ${rackLetters}`);
            }
          }
        }
      }
    }
  }
});

test("every strategy cashes in on the final auction", () => {
  for (const [name, make] of Object.entries(CHOICES)) {
    if (name === "starter" || name === "report") continue; // baselines have no endgame
    const s = make();
    assert.ok(s.play(view({ rackLetters: "RETAINS", auctionsLeft: 0 })), `${name} kept RETAINS at the end`);
  }
});
