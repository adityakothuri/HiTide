import { LiveDronePanel } from './LiveDronePanel'
import s from './Operations.module.css'

export function Drone() {
  return <div className={s.app}>
    <a className={s.skip} href="#drone-main">Skip to drone controls</a>
    <header className={s.header}>
      <a href="/" className={s.brand}>
        <span className={s.brandMark}><img src="/hitide-logo.png" alt="" width={44} height={44} /></span>
        <span>HiTide<span className={s.brandSub}>HACKUTD 2026</span></span>
      </a>
      <nav aria-label="Main">
        <a href="/texas">Texas monitor</a>
        <a href="/console">Kerrville test case</a>
        <a href="/drone" aria-current="page">Drone</a>
      </nav>
    </header>
    <main id="drone-main" className={s.main}>
      <LiveDronePanel />
    </main>
  </div>
}
