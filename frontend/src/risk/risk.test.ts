import { describe, expect, it } from 'vitest'
import { band, BANDS } from './bands'
import { decodeFactors, decodeFrame, parseIndex, sample, type RiskIndex } from './grid'
import { paintGrid } from './paint'
import { readout } from './readout'
import { riskTicks } from './ticks'
import { riskRgba, turbo } from './turbo'

const INDEX_JSON = {
  version: 1,
  name: 'Flood risk index',
  study_area: 'Hunt to Kerrville',
  bounds: [-100, 30, -99, 31],
  width: 2,
  height: 2,
  cell_m: 60,
  factors: ['Low height above stream', 'Near a waterway', 'Rain, past hour', 'Rain, past 24 h'],
  frames: [{ id: 'a', time: '2025-07-04T06:00:00Z', kind: 'observed', url: 'grids/a.bin', factors_url: 'grids/a.factors.bin', min: 0, max: 80 }],
}

function f32(values: number[]): ArrayBuffer {
  const buf = new ArrayBuffer(values.length * 4)
  const dv = new DataView(buf)
  values.forEach((v, i) => dv.setFloat32(i * 4, v, true))
  return buf
}

describe('turbo colormap', () => {
  it('runs dark blue at 0 to dark red at 1', () => {
    const [r0, g0, b0] = turbo(0)
    const [rLow, gLow, bLow] = turbo(0.1)
    const [r1, g1, b1] = turbo(1)
    expect(r0 + g0 + b0).toBeLessThan(150)
    expect(bLow).toBeGreaterThan(rLow)
    expect(bLow).toBeGreaterThan(gLow)
    expect(r1).toBeGreaterThan(b1)
    expect(r1).toBeGreaterThan(g1)
  })

  it('is green-dominant in the middle', () => {
    const [r, g, b] = turbo(0.5)
    expect(g).toBeGreaterThan(r)
    expect(g).toBeGreaterThan(b)
  })

  it('clamps out-of-range input', () => {
    expect(turbo(-1)).toEqual(turbo(0))
    expect(turbo(2)).toEqual(turbo(1))
  })

  it('maps a 0..100 index to color and NaN to transparent', () => {
    expect(riskRgba(50)[3]).toBe(255)
    expect(riskRgba(Number.NaN)[3]).toBe(0)
    expect(riskRgba(100).slice(0, 3)).toEqual(turbo(1))
  })

  it('starts the ramp at blue, not near-black', () => {
    const [r, g, b] = riskRgba(0)
    expect(b).toBeGreaterThan(r)
    expect(b).toBeGreaterThan(g)
  })

  it('fades low values out so the basemap shows through', () => {
    expect(riskRgba(0)[3]).toBe(0)
    expect(riskRgba(5)[3]).toBe(0)
    expect(riskRgba(15)[3]).toBeGreaterThan(0)
    expect(riskRgba(15)[3]).toBeLessThan(255)
    expect(riskRgba(25)[3]).toBe(255)
  })
})

describe('bands', () => {
  it('splits at 25, 50 and 75', () => {
    expect(band(0)).toBe('Low')
    expect(band(24.9)).toBe('Low')
    expect(band(25)).toBe('Moderate')
    expect(band(50)).toBe('High')
    expect(band(75)).toBe('Severe')
    expect(band(100)).toBe('Severe')
    expect(BANDS).toHaveLength(4)
  })
})

describe('legend ticks', () => {
  it('puts ticks at 0, 25, 50, 75 and 100 with band names between them', () => {
    const t = riskTicks()
    expect(t.ticks.map((x) => x.label)).toEqual(['0', '25', '50', '75', '100'])
    expect(t.ticks.map((x) => x.pos)).toEqual([0, 0.25, 0.5, 0.75, 1])
    expect(t.bands.map((b) => b.label)).toEqual(['Low', 'Moderate', 'High', 'Severe'])
    expect(t.bands[0].pos).toBeCloseTo(0.125)
  })
})

describe('grid index and frames', () => {
  it('parses a valid index', () => {
    const idx = parseIndex(INDEX_JSON)
    expect(idx.width).toBe(2)
    expect(idx.frames[0].kind).toBe('observed')
    expect(idx.frames[0].t).toBe(Date.parse('2025-07-04T06:00:00Z'))
  })

  it('reads optional per-frame rain stats', () => {
    const withRain = { ...INDEX_JSON, frames: [{ ...INDEX_JSON.frames[0], rain1h_max: 2.5, rain1h_mean: 0.4 }] }
    expect(parseIndex(withRain).frames[0].rain1hMax).toBe(2.5)
    expect(parseIndex(withRain).frames[0].rain1hMean).toBe(0.4)
    expect(parseIndex(INDEX_JSON).frames[0].rain1hMax).toBeNull()
  })

  it('rejects malformed indexes', () => {
    expect(() => parseIndex({ ...INDEX_JSON, width: -1 })).toThrow()
    expect(() => parseIndex({ ...INDEX_JSON, bounds: [1, 2] })).toThrow()
    expect(() => parseIndex(null)).toThrow()
    expect(() => parseIndex({ ...INDEX_JSON, frames: [{ ...INDEX_JSON.frames[0], kind: 'guess' }] })).toThrow()
  })

  it('decodes little-endian Float32 and checks the length', () => {
    const v = decodeFrame(f32([1, 2, Number.NaN, 4]), 2, 2)
    expect(v[1]).toBe(2)
    expect(Number.isNaN(v[2])).toBe(true)
    expect(() => decodeFrame(f32([1, 2, 3]), 2, 2)).toThrow()
  })

  it('decodes the factor bytes', () => {
    const f = decodeFactors(new Uint8Array([0x01, 0x32, 255, 0x20]).buffer, 2, 2)
    expect(f[1]).toBe(0x32)
    expect(() => decodeFactors(new Uint8Array([1]).buffer, 2, 2)).toThrow()
  })
})

describe('bilinear sampling', () => {
  // Row 0 is north. Cell centers: (-99.75, 30.75)=10, (-99.25, 30.75)=20, (-99.75, 30.25)=30, (-99.25, 30.25)=40.
  const idx: RiskIndex = parseIndex(INDEX_JSON)
  const values = new Float32Array([10, 20, 30, 40])

  it('returns the cell value at a cell center', () => {
    expect(sample(idx, values, -99.75, 30.75)).toBeCloseTo(10)
    expect(sample(idx, values, -99.25, 30.25)).toBeCloseTo(40)
  })

  it('interpolates between centers', () => {
    expect(sample(idx, values, -99.5, 30.5)).toBeCloseTo(25)
    expect(sample(idx, values, -99.5, 30.75)).toBeCloseTo(15)
  })

  it('returns null outside the grid', () => {
    expect(sample(idx, values, -101, 30.5)).toBeNull()
    expect(sample(idx, values, -99.5, 31.5)).toBeNull()
  })

  it('ignores NaN neighbours and returns null on an all-NaN cell', () => {
    const withGap = new Float32Array([10, Number.NaN, 30, 40])
    expect(sample(idx, withGap, -99.25, 30.75)).toBeNull()
    const v = sample(idx, withGap, -99.5, 30.5)
    expect(v).not.toBeNull()
    expect(v as number).toBeCloseTo((10 + 30 + 40) / 3)
  })
})

describe('hover readout', () => {
  const idx = parseIndex(INDEX_JSON)
  const values = new Float32Array([10, 60, 30, Number.NaN])
  const factors = new Uint8Array([0x01, 0x23, 0x10, 255])

  it('gives value, band and the top two factors of the nearest cell', () => {
    const r = readout(idx, values, factors, -99.25, 30.75)
    expect(r).not.toBeNull()
    expect(r?.value).toBe(60)
    expect(r?.band).toBe('High')
    expect(r?.factors).toEqual(['Rain, past hour', 'Rain, past 24 h'])
  })

  it('returns null outside the study area or on a NaN cell', () => {
    expect(readout(idx, values, factors, -99.25, 30.25)).toBeNull()
    expect(readout(idx, values, factors, -98, 30.25)).toBeNull()
  })
})

describe('paintGrid', () => {
  it('upsamples by the scale and leaves NaN cells transparent', () => {
    const px = paintGrid(new Float32Array([0, 100, Number.NaN, 50]), 2, 2, 2)
    expect(px.length).toBe(4 * 4 * 4)
    // Top-right output pixel is the 100 cell: opaque.
    expect(px[(0 * 4 + 3) * 4 + 3]).toBe(255)
    // Top-left output pixel is the 0 cell: faded out.
    expect(px[3]).toBe(0)
    // Bottom-left output pixel sits in the NaN cell.
    const bl = (3 * 4 + 0) * 4
    expect(px[bl + 3]).toBe(0)
  })
})
