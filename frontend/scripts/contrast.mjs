// WCAG contrast check for the documented token pairings. Reads colors from src/styles/tokens.css.
// Usage: npm run contrast. Exits 1 if any text pairing falls below its target.
import { readFileSync } from 'node:fs'

const css = readFileSync(new URL('../src/styles/tokens.css', import.meta.url), 'utf8')
const tokens = Object.fromEntries([...css.matchAll(/--([\w-]+):\s*(#[0-9a-f]{3,6})/gi)].map(([, k, v]) => [k, expand(v)]))

function expand(hex) {
  return hex.length === 4 ? '#' + [...hex.slice(1)].map((c) => c + c).join('') : hex
}
function lum(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}
function ratio(a, b) {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

// [foreground, background, target]. 4.5 = AA text, 3 = icons and non-text marks.
const PAIRS = [
  ['ink', 'surface', 4.5], ['ink', 'surface-page', 4.5], ['neutral-5', 'surface', 4.5], ['neutral-5', 'surface-page', 4.5],
  ['neutral-6', 'surface', 4.5], ['neutral-6', 'neutral-1', 4.5], ['on-dark', 'brand-red', 4.5], ['on-dark', 'brand-red-hover', 4.5],
  ['brand-red', 'surface', 4.5], ['brand-red', 'surface-page', 4.5],
  ['safe', 'surface', 4.5], ['safe', 'safe-bg', 4.5], ['caution', 'surface', 4.5], ['caution', 'caution-bg', 4.5],
  ['critical', 'surface', 4.5], ['critical', 'critical-bg', 4.5], ['on-dark', 'critical-deep', 4.5],
  ['info', 'surface', 4.5], ['info', 'info-bg', 4.5], ['on-dark', 'ink', 4.5], ['on-dark', 'neutral-6', 4.5],
  ['ink', 'water-1', 4.5], ['ink', 'water-2', 4.5], ['on-dark', 'water-4', 4.5], ['on-dark', 'water-5', 4.5], ['water-5', 'surface', 4.5],
  ['neutral-4', 'surface', 3], ['neutral-4', 'surface-page', 3], ['info', 'surface', 3], ['info', 'surface-page', 3], ['on-dark', 'critical-deep', 3], ['neutral-5', 'surface', 3], ['caution-mark', 'surface', 3],
]

let failed = 0
for (const [fg, bg, target] of PAIRS) {
  if (!tokens[fg] || !tokens[bg]) { console.log(`missing token: ${fg} or ${bg}`); failed += 1; continue }
  const r = ratio(tokens[fg], tokens[bg])
  const ok = r >= target
  if (!ok) failed += 1
  console.log(`${ok ? 'pass' : 'FAIL'}  ${r.toFixed(2).padStart(5)}  ${fg} on ${bg} (target ${target})`)
}
process.exit(failed ? 1 : 0)
