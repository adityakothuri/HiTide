import { useEffect, useState } from 'react'
import { Console } from '../console/Console'
import { DriverApp } from '../driver/DriverApp'
import { StepCaption } from './DemoPanel'
import s from './Present.module.css'

const PHONE_H = 844
const CAPTION_H = 180

function usePhoneScale(): number {
  const calc = () => Math.min(1, (window.innerHeight - CAPTION_H - 32) / PHONE_H)
  const [scale, setScale] = useState(calc)
  useEffect(() => {
    const onResize = () => setScale(calc())
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return scale
}

/** Side by side: the driver's phone and the ops console, one store. */
export function Present() {
  const scale = usePhoneScale()
  return (
    <div className={s.present}>
      <aside className={s.phoneCol} aria-label="Driver app" style={{ width: Math.round(390 * scale) + 48 }}>
        <div className={s.phoneBox} style={{ width: 390 * scale, height: PHONE_H * scale }}>
          <div style={{ transform: `scale(${scale})`, transformOrigin: 'top left' }}>
            <DriverApp framed />
          </div>
        </div>
        <StepCaption />
      </aside>
      <div className={s.consoleCol}>
        <Console compact />
      </div>
    </div>
  )
}
