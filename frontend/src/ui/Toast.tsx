import * as RToast from '@radix-ui/react-toast'
import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import s from './Toast.module.css'

interface ToastMsg { id: number; title: string; detail?: string }
const ToastCtx = createContext<(title: string, detail?: string) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastMsg[]>([])
  const push = useCallback((title: string, detail?: string) => {
    setItems((xs) => [...xs, { id: Date.now() + Math.random(), title, detail }])
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      <RToast.Provider duration={5000}>
        {children}
        {items.map((t) => (
          <RToast.Root key={t.id} className={s.toast} onOpenChange={(open) => !open && setItems((xs) => xs.filter((x) => x.id !== t.id))}>
            <RToast.Title className={s.title}>{t.title}</RToast.Title>
            {t.detail && <RToast.Description className={s.detail}>{t.detail}</RToast.Description>}
            <RToast.Close className={s.close}>Dismiss</RToast.Close>
          </RToast.Root>
        ))}
        <RToast.Viewport className={s.viewport} />
      </RToast.Provider>
    </ToastCtx.Provider>
  )
}

export function useToast() {
  return useContext(ToastCtx)
}
