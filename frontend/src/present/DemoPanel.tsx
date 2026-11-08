import * as Dialog from '@radix-ui/react-dialog'
import { Play, RotateCcw, SkipForward, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button } from '../ui/Button'
import { humanizeNarration, personaFor } from '../data/personas'
import { useApp, useStore, useUi } from '../state/StoreContext'
import { useToast } from '../ui/Toast'
import s from './DemoPanel.module.css'

const TOTAL_STEPS = 7
const PHONE_DRIVERS = ['demo-a', 'demo-b', 'demo-d']

/** Hidden presenter controls. Shift+D toggles it. Not part of the product UI. */
export function DemoPanel() {
  const store = useStore()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const step = useApp((st) => st.demoStep)
  const status = useUi((u) => u.status)
  const phone = useUi((u) => u.phoneDriverId)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (e.metaKey || e.ctrlKey || e.altKey || e.repeat) return
      if (target?.closest('input, textarea, select, [contenteditable]')) return
      if (e.shiftKey && (e.key === 'D' || e.key === 'd')) {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const run = (label: string, fn: () => Promise<void>) => () => {
    fn().catch(() => toast(`${label} failed`, 'Check that the backend is running, or open this page with ?mode=mock.'))
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen} modal={false}>
      <Dialog.Portal>
        <Dialog.Content
          className={s.panel}
          data-theme="dispatch"
          aria-describedby="demo-desc"
          onInteractOutside={(e) => e.preventDefault()}
          onOpenAutoFocus={(e) => e.preventDefault()}
        >
          <div className={s.head}>
            <Dialog.Title className={s.title}>Demo controls</Dialog.Title>
            <Dialog.Close className={s.close} aria-label="Close demo controls">
              <X aria-hidden="true" />
            </Dialog.Close>
          </div>
          <p id="demo-desc" className={s.desc}>
            {status === 'live' ? 'Driving the live backend.' : 'Playing the recorded offline demo.'} Shift+D hides this panel.
          </p>
          <div className={s.step} role="status">
            {step ? (
              <>
                <span className={`${s.stepNum} num`}>Step {step.step} of {TOTAL_STEPS}</span>
                <span className={s.stepTitle}>{step.title}</span>
              </>
            ) : (
              <span className={s.stepTitle}>Not started</span>
            )}
          </div>
          <label className={s.field}>
            <span className={s.fieldLabel}>Phone shows</span>
            <select
              className={s.select}
              value={phone ?? ''}
              onChange={(e) => {
                const v = e.target.value || null
                store.setUi((u) => ({ ...u, phoneDriverId: v }))
              }}
            >
              <option value="">Follow the story</option>
              {PHONE_DRIVERS.map((id) => (
                <option key={id} value={id}>{personaFor(id)?.name}</option>
              ))}
            </select>
          </label>
          <div className={s.actions}>
            <Button icon={Play} onClick={run('Starting the demo', () => store.provider.startDemo())}>Run scenario</Button>
            <Button variant="secondary" icon={SkipForward} disabled={store.provider.kind === 'live'} onClick={run('Next step', () => store.provider.nextStep())}>
              Next step
            </Button>
            <Button variant="secondary" icon={RotateCcw} onClick={run('Reset', () => store.provider.reset())}>Reset</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/** Narration caption for /present. */
export function StepCaption() {
  const step = useApp((st) => st.demoStep)
  if (!step) return null
  return (
    <div className={s.caption} role="status">
      <span className={`${s.captionNum} num`}>{step.step}</span>
      <div>
        <p className={s.captionTitle}>{step.title}</p>
        <p className={s.captionDetail}>{humanizeNarration(step.detail)}</p>
      </div>
    </div>
  )
}
