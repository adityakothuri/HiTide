import { Layers } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { WxState } from '../wx/useWx'
import { Colorbar } from './Colorbar'
import { LayerPanel } from './LayerPanel'
import s from './LayersMenu.module.css'

/** Weather layers behind one button, so the default map shows only people, areas, points and drones. */
export function LayersMenu({ wx }: { wx: WxState }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])
  return (
    <div ref={ref} className={s.wrap}>
      <button type="button" className={s.btn} aria-expanded={open} aria-controls="layers-pop" onClick={() => setOpen((x) => !x)}>
        <Layers size={14} aria-hidden="true" />
        Layers
      </button>
      {open && (
        <div id="layers-pop" className={s.pop}>
          <LayerPanel wx={wx} />
          <Colorbar wx={wx} compact />
        </div>
      )}
    </div>
  )
}
