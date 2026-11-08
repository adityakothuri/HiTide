import { useEffect, useState } from 'react'
import { LogoMark } from '../ui/LogoMark'
import s from './Intro.module.css'

const KEY = 'ht-intro'
/** Longest animation plus margin: unmount even if animationend never fires (background tab). */
const FALLBACK_MS = 2600

function shouldPlay(): boolean {
  if (typeof window === 'undefined') return false
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false
  if (new URLSearchParams(window.location.search).get('intro') === '1') return true
  try {
    if (window.sessionStorage.getItem(KEY)) return false
    window.sessionStorage.setItem(KEY, '1')
  } catch {
    /* Storage blocked: play it; it's short. */
  }
  return true
}

/**
 * Opening animation, "tide out": the logo pops in on deep navy with two ripples, a wave line draws
 * under it, then the cover drains upward with a wavy edge to reveal the app. Once per session; skipped
 * for reduced motion; never blocks input once it starts leaving.
 */
export function Intro() {
  const [on, setOn] = useState(shouldPlay)
  useEffect(() => {
    if (!on) return
    const t = window.setTimeout(() => setOn(false), FALLBACK_MS)
    return () => window.clearTimeout(t)
  }, [on])
  if (!on) return null
  return (
    <div
      className={s.cover}
      aria-hidden="true"
      onAnimationEnd={(e) => {
        if (e.target === e.currentTarget && e.animationName.includes('drain')) setOn(false)
      }}
    >
      <div className={s.stage}>
        <span className={`${s.ring} ${s.r1}`} />
        <span className={`${s.ring} ${s.r2}`} />
        <span className={s.tile}><LogoMark size={92} /></span>
        <svg className={s.line} viewBox="0 0 160 16" width="160" height="16">
          <path d="M2 8 C 22 0, 38 0, 58 8 S 98 16, 118 8 S 150 0, 158 8" />
        </svg>
      </div>
      <svg className={s.edge} viewBox="0 0 1440 80" preserveAspectRatio="none">
        <path d="M0 0 H2880 V36 C 2760 76, 2640 76, 2520 36 S 2280 -4, 2160 36 S 1920 76, 1800 36 S 1560 -4, 1440 36 S 1200 76, 1080 36 S 840 -4, 720 36 S 480 76, 360 36 S 120 -4, 0 36 Z" />
      </svg>
    </div>
  )
}
