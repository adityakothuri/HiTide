import type { FloodCategory, RainProduct } from '../wx/types'
import type { BaseField, WxState } from '../wx/useWx'
import s from './LayerPanel.module.css'

const BASES: { value: BaseField; label: string; hint: string }[] = [
  { value: 'risk', label: 'Flood risk', hint: 'Relative index, 0 to 100' },
  { value: 'rain', label: 'Rainfall', hint: 'NOAA MRMS radar estimate' },
  { value: 'depth', label: 'Flood depth', hint: 'Modelled from river stage' },
]

const RAIN: { value: RainProduct; label: string }[] = [
  { value: 'p1h', label: '1 h' },
  { value: 'p24h', label: '24 h' },
]

const CATS: FloodCategory[] = ['action', 'minor', 'moderate', 'major']

/** Layers: one base field at a time (radio), overlays as checkboxes, then the base field's opacity. */
export function LayerPanel({ wx }: { wx: WxState }) {
  const { layers, setLayers } = wx
  return (
    <section className={s.panel} aria-labelledby="layers-h">
      <h2 id="layers-h" className={s.heading}>Layers</h2>
      <fieldset className={s.group}>
        <legend className={s.sub}>Base field</legend>
        {BASES.map((b) => (
          <div key={b.value} className={s.row}>
            <label className={s.label}>
              <input type="radio" name="base" value={b.value} checked={layers.base === b.value} onChange={() => setLayers((l) => ({ ...l, base: b.value }))} />
              <span className={s.text}>
                {b.label}
                <span className={s.hint}>{b.hint}</span>
              </span>
            </label>
            {b.value === 'rain' && (
              <div className={s.seg} role="group" aria-label="Rainfall period">
                {RAIN.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    aria-pressed={layers.base === 'rain' && layers.rainProduct === r.value}
                    className={s.segBtn}
                    onClick={() => setLayers((l) => ({ ...l, base: 'rain', rainProduct: r.value }))}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </fieldset>
      <fieldset className={s.group}>
        <legend className={s.sub}>Overlays</legend>
        <div className={s.row}>
          <label className={s.label}>
            <input type="checkbox" checked={layers.gauges} onChange={(e) => setLayers((l) => ({ ...l, gauges: e.target.checked }))} />
            <span className={s.text}>River gauges<span className={s.hint}>NWS flood category</span></span>
          </label>
          <span className={s.keys} aria-hidden="true">{CATS.map((c) => <span key={c} className={`${s.dot} ${s[c]}`} />)}</span>
        </div>
        <div className={s.row}>
          <label className={s.label}>
            <input type="checkbox" checked={layers.roads} onChange={(e) => setLayers((l) => ({ ...l, roads: e.target.checked }))} />
            <span className={s.text}>Roads<span className={s.hint}>Closed, likely flooded</span></span>
          </label>
          <span className={s.keys} aria-hidden="true"><span className={`${s.line} ${s.closed}`} /><span className={`${s.line} ${s.likely}`} /></span>
        </div>
      </fieldset>
      <label className={s.opacity}>
        <span className={s.sub}>Opacity</span>
        <input
          type="range"
          min={0.2}
          max={1}
          step={0.05}
          value={layers.opacity}
          onChange={(e) => setLayers((l) => ({ ...l, opacity: Number(e.target.value) }))}
          aria-valuetext={`${Math.round(layers.opacity * 100)} percent`}
        />
        <span className={`${s.pct} num`}>{Math.round(layers.opacity * 100)}%</span>
      </label>
    </section>
  )
}
