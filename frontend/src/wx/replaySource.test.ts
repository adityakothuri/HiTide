import { describe, expect, it } from 'vitest'
import { categoryOf, sampleSeries } from './category'
import { replaySource, type ReplayData } from './replaySource'

const CATS = { action: 7, minor: 9, moderate: 12, major: 20 }

const DATA: ReplayData = {
  mrms: {
    bbox: [-100, 29, -99, 30],
    minzoom: 8,
    maxzoom: 11,
    stamps_utc: ['2025070406', '2025070407', '2025070408'],
    products: {
      p1h: { label: '1 hour', legend: { stops: [], ticks: [], units: 'in' } },
      p24h: { label: '24 hours', legend: { stops: [], ticks: [], units: 'in' } },
    },
  },
  depth: {
    gauge: { site: '08166200', base_stage_ft: 0 },
    rise_step_m: 0.5,
    coordinates: [[0, 1], [1, 1], [1, 0], [0, 0]],
    bands: [],
    frames: [0, 0.5, 1, 1.5].map((r) => ({ rise_m: r, file: `rise_${r}.png` })),
    roads: { a: [0.2, 0.4], b: [1.0, 1.5] },
  },
  gauges: {
    warnings: [{ at: '2025-07-04T01:14:00-05:00', event: 'Flash Flood Warning', area: 'Kerr County' }],
    gauges: [
      {
        site: '08166200', name: 'Kerrville', lon: 0, lat: 0, categories_ft: CATS,
        // 0 ft at 06Z rising to 4 ft (1.22 m) at 07Z
        series: [['2025-07-04T06:00:00Z', 0], ['2025-07-04T07:00:00Z', 4]],
      },
      { site: 'x', name: 'Uncategorized', lon: 0, lat: 0, categories_ft: null, series: [] },
    ],
  },
}

const at = (iso: string) => replaySource(DATA).at(Date.parse(iso))

describe('categoryOf', () => {
  it('puts a stage at a threshold into that category', () => {
    expect(categoryOf(6.9, CATS)).toBe('below')
    expect(categoryOf(7, CATS)).toBe('action')
    expect(categoryOf(9, CATS)).toBe('minor')
    expect(categoryOf(12, CATS)).toBe('moderate')
    expect(categoryOf(37.5, CATS)).toBe('major')
  })

  it('is none without categories or a reading', () => {
    expect(categoryOf(10, null)).toBe('none')
    expect(categoryOf(null, CATS)).toBe('none')
  })
})

describe('sampleSeries', () => {
  const s = [[0, 0], [10, 10], [100, 20]] as const
  it('interpolates inside the series', () => expect(sampleSeries(s, 5, 50)).toBe(5))
  it('is null outside the series or across a long gap', () => {
    expect(sampleSeries(s, -1, 50)).toBeNull()
    expect(sampleSeries(s, 50, 50)).toBeNull()
  })
})

describe('replaySource', () => {
  it('shows the newest completed rain hour', () => {
    expect(at('2025-07-04T07:59:00Z').rainTiles('p1h')).toBe('/wx/mrms/p1h/2025070407/{z}/{x}/{y}.png')
    expect(at('2025-07-04T08:00:00Z').rainValidAt).toBe(Date.parse('2025-07-04T08:00:00Z'))
  })

  it('has no depth frame or closed roads before the river rises', () => {
    const s = at('2025-07-04T06:00:00Z')
    expect(s.depth).toBeNull()
    expect(s.roads.closed.size + s.roads.likely.size).toBe(0)
  })

  it('picks the depth frame and road status for the Kerrville rise', () => {
    // 07Z: 4 ft = 1.219 m -> frame 1.0 m; road a closed, b likely
    const s = at('2025-07-04T07:00:00Z')
    expect(s.depth?.riseM).toBe(1)
    expect([...s.roads.closed]).toEqual(['a'])
    expect([...s.roads.likely]).toEqual(['b'])
  })

  it('shows the NWS warning in effect at t', () => {
    expect(at('2025-07-04T06:10:00Z').warning).toBeNull()
    expect(at('2025-07-04T06:20:00Z').warning?.event).toBe('Flash Flood Warning')
  })

  it('reports gauge category and trend', () => {
    const k = at('2025-07-04T07:00:00Z').gauges[0]
    expect(k.stageFt).toBe(4)
    expect(k.trendFtPerHr).toBe(4)
    expect(k.category).toBe('below')
    expect(at('2025-07-04T07:00:00Z').gauges[1].category).toBe('none')
  })
})
