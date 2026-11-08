import { useEffect } from 'react'
import type { WxState } from '../wx/useWx'

function typing(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  // The time range input handles its own arrows; other inputs, selects and text areas keep their keys.
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

/** Map page keys: arrows step time, Space plays or pauses, Esc closes the detail panel, / focuses search. */
export function useConsoleKeys(wx: WxState, onEscape: () => void, timeKeys = true): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'Escape') {
        onEscape()
        return
      }
      if (typing(e.target)) return
      // Buttons, links, tabs and radios keep Space and arrows for their own activation and navigation.
      if (e.target instanceof Element && e.target.closest('button, a, [role="tab"], [role="radio"], [role="tablist"], [role="radiogroup"], summary')) return
      if (!timeKeys && e.key !== '/') return
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault()
        wx.step(e.key === 'ArrowRight' ? 1 : -1)
      } else if (e.key === ' ') {
        e.preventDefault()
        wx.setPlaying(!wx.playing)
      } else if (e.key === '/') {
        const search = document.querySelector<HTMLInputElement>('[data-console-search]')
        if (search) {
          e.preventDefault()
          search.focus()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [wx, onEscape, timeKeys])
}
