import { Hand, Phone, PhoneOff, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useStore } from '../state/StoreContext'
import { useToast } from '../ui/Toast'
import type { OutreachEvent, Reply } from '../data/types'
import { speak, stopSpeaking } from './speech'
import s from './IncomingCall.module.css'

const RING_TIMEOUT_MS = 25_000

/**
 * The HiTide voice call, as the phone shows it. In the live product the call arrives over the
 * phone network (ElevenLabs); here it's mirrored in-app so the audience can see it. Answering plays
 * the script and lets the driver answer by tapping.
 */
export function IncomingCall({ call, caseId, onDone }: { call: OutreachEvent; caseId: string; onDone: () => void }) {
  const store = useStore()
  const toast = useToast()
  const [connected, setConnected] = useState(false)
  const [seconds, setSeconds] = useState(0)
  const [sending, setSending] = useState(false)
  const answerRef = useRef<HTMLButtonElement>(null)
  const safeRef = useRef<HTMLButtonElement>(null)

  // Ring only while unanswered; unanswered calls fall back to the check-in screen.
  useEffect(() => {
    if (connected) return
    answerRef.current?.focus()
    const t = window.setTimeout(onDone, RING_TIMEOUT_MS)
    return () => window.clearTimeout(t)
  }, [connected, onDone])

  useEffect(() => {
    if (connected) safeRef.current?.focus()
  }, [connected])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onDone()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onDone])

  useEffect(() => {
    if (!connected) return
    speak(call.body)
    const id = window.setInterval(() => setSeconds((x) => x + 1), 1000)
    return () => {
      window.clearInterval(id)
      stopSpeaking()
    }
  }, [connected, call.body])

  const answer = async (reply: Reply) => {
    if (sending) return
    setSending(true)
    stopSpeaking()
    try {
      await store.provider.reply(caseId, reply)
      store.setUi((u) => ({ ...u, replies: { ...u.replies, [caseId]: reply } }))
      onDone()
    } catch {
      toast("We couldn't send your answer", 'Check your connection and try again, or call 911 if you are in danger.')
      setSending(false)
    }
  }

  const mmss = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

  return (
    <div className={`${s.call} on-dark`} role="alertdialog" aria-modal="true" aria-labelledby="call-title" aria-describedby="call-status">
      <div className={s.caller}>
        <span className={s.avatar} aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M12 2.5 4.5 5.4v5.9c0 4.6 3.1 8.6 7.5 10.2 4.4-1.6 7.5-5.6 7.5-10.2V5.4Z" />
          </svg>
        </span>
        <h2 id="call-title" className={s.name}>HiTide</h2>
        <p id="call-status" className={`${s.status} num`}>
          {connected ? `Connected, ${mmss}` : 'Incoming call'}
        </p>
      </div>

      {connected ? (
        <div className={s.connected}>
          <p className={s.transcript}>&ldquo;{call.body}&rdquo;</p>
          <p className={s.hint}>Answer out loud, or tap:</p>
          <div className={s.replies}>
            <button ref={safeRef} type="button" className={`${s.reply} ${s.safe}`} disabled={sending} onClick={() => answer('safe')}>
              <ShieldCheck aria-hidden="true" />I'm safe
            </button>
            <button type="button" className={`${s.reply} ${s.help}`} disabled={sending} onClick={() => answer('need_help')}>
              <Hand aria-hidden="true" />I need help
            </button>
          </div>
          <button type="button" className={s.end} onClick={onDone} aria-label="End call">
            <PhoneOff aria-hidden="true" />
          </button>
        </div>
      ) : (
        <div className={s.ringActions}>
          <div className={s.action}>
            <button type="button" className={`${s.round} ${s.decline}`} onClick={onDone} aria-label="Decline call">
              <PhoneOff aria-hidden="true" />
            </button>
            <span aria-hidden="true">Decline</span>
          </div>
          <div className={s.action}>
            <button ref={answerRef} type="button" className={`${s.round} ${s.accept}`} onClick={() => setConnected(true)} aria-label="Answer call">
              <Phone aria-hidden="true" />
            </button>
            <span aria-hidden="true">Answer</span>
          </div>
        </div>
      )}
    </div>
  )
}
