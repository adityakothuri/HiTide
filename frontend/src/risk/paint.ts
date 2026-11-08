import { RISK_LUT } from './turbo'

/**
 * Paints a risk frame to RGBA pixels, upsampled `scale` times with bilinear interpolation between
 * cell centers so it reads as a continuous field. NaN cells (outside the study area) stay transparent.
 */
export function paintGrid(values: Float32Array, width: number, height: number, scale: number): Uint8ClampedArray<ArrayBuffer> {
  const W = width * scale
  const H = height * scale
  const out = new Uint8ClampedArray(new ArrayBuffer(W * H * 4))
  const at = (c: number, r: number) => values[Math.min(height - 1, Math.max(0, r)) * width + Math.min(width - 1, Math.max(0, c))]
  for (let py = 0; py < H; py++) {
    const y = (py + 0.5) / scale - 0.5
    const r0 = Math.floor(y)
    const fy = y - r0
    const own = Math.min(height - 1, Math.max(0, Math.floor((py + 0.5) / scale)))
    for (let px = 0; px < W; px++) {
      const ownC = Math.min(width - 1, Math.floor((px + 0.5) / scale))
      if (!Number.isFinite(values[own * width + ownC])) continue
      const x = (px + 0.5) / scale - 0.5
      const c0 = Math.floor(x)
      const fx = x - c0
      let sum = 0
      let wsum = 0
      const add = (v: number, w: number) => {
        if (w > 0 && Number.isFinite(v)) {
          sum += v * w
          wsum += w
        }
      }
      add(at(c0, r0), (1 - fx) * (1 - fy))
      add(at(c0 + 1, r0), fx * (1 - fy))
      add(at(c0, r0 + 1), (1 - fx) * fy)
      add(at(c0 + 1, r0 + 1), fx * fy)
      if (wsum === 0) continue
      const v = sum / wsum
      const [cr, cg, cb, ca] = RISK_LUT[Math.round(Math.min(100, Math.max(0, v)))]
      const o = (py * W + px) * 4
      out[o] = cr
      out[o + 1] = cg
      out[o + 2] = cb
      out[o + 3] = ca
    }
  }
  return out
}
