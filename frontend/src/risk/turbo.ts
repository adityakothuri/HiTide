/**
 * Turbo colormap (Mikhailov, Google 2019): a perceptually improved rainbow, blue = low, red = high,
 * without jet's false bands. Polynomial approximation from the reference implementation.
 */
export type Rgb = [number, number, number]
export type Rgba = [number, number, number, number]

const R = [0.13572138, 4.6153926, -42.66032258, 132.13108234, -152.94239396, 59.28637943]
const G = [0.09140261, 2.19418839, 4.84296658, -14.18503333, 4.27729857, 2.82956604]
const B = [0.1066733, 12.64194608, -60.58204836, 110.36276771, -89.90310912, 27.34824973]

function poly(c: readonly number[], x: number): number {
  let y = 0
  for (let i = c.length - 1; i >= 0; i--) y = y * x + c[i]
  return y
}

const byte = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 255)

export function turbo(x: number): Rgb {
  const t = Math.min(1, Math.max(0, x))
  return [byte(poly(R, t)), byte(poly(G, t)), byte(poly(B, t))]
}

/**
 * The risk ramp skips Turbo's near-black start so index 0 is blue, as on GIS risk maps.
 * Low values fade out (fully transparent at or below FADE_FROM, opaque from FADE_TO) so the
 * basemap shows wherever risk is negligible.
 */
const RAMP_START = 0.1
export const FADE_FROM = 5
export const FADE_TO = 25

const rampColor = (index: number): Rgb => turbo(RAMP_START + (1 - RAMP_START) * (index / 100))

/** 101-entry lookup (one per index point) with alpha, so painting a frame is a table read per pixel. */
export const RISK_LUT: readonly Rgba[] = Array.from({ length: 101 }, (_, v) => {
  const [r, g, b] = rampColor(v)
  const a = Math.round(Math.min(1, Math.max(0, (v - FADE_FROM) / (FADE_TO - FADE_FROM))) * 255)
  return [r, g, b, a]
})

/** Flood risk index 0..100 to RGBA. NaN (outside the study area) is fully transparent. */
export function riskRgba(index: number): Rgba {
  if (!Number.isFinite(index)) return [0, 0, 0, 0]
  return [...RISK_LUT[Math.round(Math.min(100, Math.max(0, index)))]] as Rgba
}

/** CSS gradient stops for the colorbar, bottom (0) to top (100), matching the map ramp. */
export function turboCss(steps = 16): string {
  return Array.from({ length: steps + 1 }, (_, i) => {
    const [r, g, b] = rampColor((i / steps) * 100)
    return `rgb(${r} ${g} ${b}) ${((i / steps) * 100).toFixed(1)}%`
  }).join(', ')
}
