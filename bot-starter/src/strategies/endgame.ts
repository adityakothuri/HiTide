// Endgame wrapper: on the final auction a bot's own tiles are about to
// become worthless (the match ends when that auction closes, before a real
// bot can react), so play every word it can and spend its whole balance.

import type { Policy } from "../policy.js";

export function withEndgame(inner: Policy, name = `${inner.name}+End`): Policy {
  return {
    name,
    bid(v) {
      if (v.auctionsLeft === 0) return Math.max(0, Math.floor(v.balance));
      return inner.bid(v);
    },
    play(v) {
      if (v.auctionsLeft === 0) {
        const i = v.lexicon.best(v.rack, 2);
        return i < 0 ? null : v.lexicon.words[i]!;
      }
      return inner.play(v);
    },
  };
}
