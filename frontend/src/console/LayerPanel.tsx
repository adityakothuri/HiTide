import type { RainProduct } from '../wx/types'
import type { WxLayers, WxState } from '../wx/useWx'
import s from './LayerPanel.module.css'

type Toggle = Exclude<keyof WxLayers, 'rain'>

const TOGGLES: { key: Toggle; label: string }[] = [
  { key: 'depth', label: 'Flood depth' },
  { key: 'gauges', label: 'Gauges' },
  { key: 'roads', label: 'Road closures' },
]

const RAIN: { value: RainProduct; label: string }[] = [
  { value: 'p1h', label: '1h' },
  { value: 'p24h', label: '24h' },
]

/** Layer toggles. Rainfall is one switch with a 1h / 24h choice. */
export function LayerPanel({ wx }: { wx: WxState }) {
  const { layers, setLayers } = wx
  const rainOn = layers.rain !== null
  return (
    <section className={s.panel} aria-labelledby="layers-h">
      <h2 id="layers-h" className={s.heading}>Layers</h2>
      <ul className={s.list}>
        <li className={s.row}>
          <label className={s.label}>
            <input
              type="checkbox"
              checked={rainOn}
              onChange={(e) => setLayers((l) => ({ ...l, rain: e.target.checked ? 'p1h' : null }))}
            />
            Rainfall
          </label>
          <div className={s.seg} role="radiogroup" aria-label="Rainfall period">
            {RAIN.map((r) => (
              <button
                key={r.value}
                type="button"
                role="radio"
                aria-checked={layers.rain === r.value}
                className={s.segBtn}
                onClick={() => setLayers((l) => ({ ...l, rain: r.value }))}
              >
                {r.label}
              </button>
            ))}
          </div>
        </li>
        {TOGGLES.map((t) => (
          <li key={t.key} className={s.row}>
            <label className={s.label}>
              <input type="checkbox" checked={layers[t.key]} onChange={(e) => setLayers((l) => ({ ...l, [t.key]: e.target.checked }))} />
              {t.label}
            </label>
          </li>
        ))}
      </ul>
    </section>
  )
}
