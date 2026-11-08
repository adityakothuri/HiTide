import { useState } from 'react'
import s from './LiveDronePanel.module.css'

export async function configureLiveOverlay(settings: Record<string, unknown>) {
  const response = await fetch('/api/live-drone/analysis/config', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings),
  })
  if (!response.ok) throw new Error('Could not update the live overlay')
}

export function LiveOverlayControls({ onAlign }: { onAlign: (kind: 'car' | 'tray') => void }) {
  const [visibility, setVisibility] = useState({ enabled: true, water: true, car: true, tray: true, labels: true })
  const [depth, setDepth] = useState('')
  const [stddev, setStddev] = useState('0.02')
  const [message, setMessage] = useState('')
  async function update(settings: Record<string, unknown>) {
    try { await configureLiveOverlay(settings); setMessage('') }
    catch { setMessage('Live overlay settings unavailable. Check the drone bridge.') }
  }
  return <div className={s.overlayControls}>
    <h3>Live overlay controls</h3>
    <div className={s.overlayOptions}>{Object.entries(visibility).map(([key, value]) =>
      <label key={key}><input type="checkbox" checked={value} onChange={event => {
        const checked = event.target.checked
        setVisibility({ ...visibility, [key]: checked })
        void update({ [key]: checked })
      }} />{key === 'enabled' ? 'Show overlays' : key === 'car' ? 'Vehicle' : key[0].toUpperCase() + key.slice(1)}</label>)}</div>
    <div className={s.controls}>
      <button onClick={() => onAlign('car')}>Align vehicle</button>
      <button onClick={() => onAlign('tray')}>Align tray</button>
    </div>
    <label>Water depth (ft) <input type="number" min="0" max="100" step="0.01" value={depth}
      placeholder="Enter water depth" onChange={event => {
        const value = event.target.value
        setDepth(value)
        if (value === '' || event.target.validity.valid) void update({ demo_depth: value === '' ? null : Number(value) })
      }} /></label>
    <label>Standard deviation (ft) <input type="number" min="0" max="100" step="0.01" value={stddev}
      onChange={event => {
        const value = event.target.value
        setStddev(value)
        if (value !== '' && event.target.validity.valid) void update({ demo_stddev: Number(value) })
      }} /></label>
    <p>Set standard deviation to 0 for a steady value. Clear depth to hide it.</p>
    <p role="status">{message}</p>
  </div>
}
