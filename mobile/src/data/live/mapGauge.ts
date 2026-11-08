import type { GaugeReading } from '@/domain/types';
import type { RemoteGauge } from './schema';

/** USGS 08166200, Guadalupe River at Kerrville: the gauge nearest the app's trip. */
export const KERRVILLE_GAUGE_SITE = '08166200';

const MAX_SAMPLES = 12;
const TREND_FT_PER_HR = 0.1;
const DEFAULT_STEP_MIN = 15; // USGS instantaneous values are 15-minute
const MS_PER_MINUTE = 60_000;

const prettyName = (name: string): string => name.replace(/\bRv\b/g, 'River').replace(/\babv\b/g, 'above');

/**
 * Builds the gauge card from the backend's latest reading, appending to the previous series when the reading is new.
 * Returns null when the gauge is missing or has no stage (the card then keeps its labelled sample data).
 */
export function toGauge(
  gauges: readonly RemoteGauge[],
  prev: GaugeReading,
  replayLabel: string | null,
  site: string = KERRVILLE_GAUGE_SITE,
): GaugeReading | null {
  const g = gauges.find((x) => x.site === site);
  if (!g || g.stage_ft == null || g.observed_at == null || g.online === false) return null;
  const id = `usgs-${site}`;
  const observedAt = new Date(g.observed_at * 1000).toISOString();
  const continuing = prev.id === id && prev.observedAt < observedAt;
  const same = prev.id === id && prev.observedAt === observedAt;

  let series: readonly number[] = [g.stage_ft];
  let step = DEFAULT_STEP_MIN;
  if (same && prev.stageFt === g.stage_ft) return prev; // unchanged reading: keep the same object (no re-render)
  if (same) {
    series = prev.series;
    step = prev.seriesStepMinutes;
  } else if (continuing) {
    const n = prev.series.length;
    const startMs = Date.parse(prev.observedAt) - prev.seriesStepMinutes * (n - 1) * MS_PER_MINUTE;
    series = [...prev.series, g.stage_ft].slice(-MAX_SAMPLES);
    step = (Date.parse(observedAt) - startMs) / MS_PER_MINUTE / n;
  }

  const rate = g.rate_ft_per_hr ?? 0;
  return {
    id,
    name: prettyName(g.name),
    stageFt: g.stage_ft,
    actionStageFt: null,
    floodCategory: g.flood_category && g.flood_category !== 'none' ? g.flood_category : null,
    trend: rate > TREND_FT_PER_HR ? 'rising' : rate < -TREND_FT_PER_HR ? 'falling' : 'steady',
    series,
    seriesStepMinutes: step,
    observedAt,
    source: `USGS ${site}${replayLabel ? ` · ${replayLabel}` : ''}`,
  };
}
