import { Hand, PhoneIncoming, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useStore } from '../../state/StoreContext'
import { useToast } from '../../ui/Toast'
import type { Reply, Town } from '../../data/types'
import { formatClock } from '../../lib/format'
import { nearestStreet, streetFromText } from '../../lib/geo'
import { LargeTitle, Row, Section } from '../ios'
import { Call911 } from './Call911'
import type { DriverView } from '../useDriverView'
import s from './Screens.module.css'

export function CheckIn({ view, town }: { view: DriverView; town: Town | null }) {
  const store = useStore()
  const toast = useToast()
  const [sending, setSending] = useState<Reply | null>(null)
  const c = view.case
  if (!c) return null
  const street = streetFromText(view.callBody ?? undefined) ?? nearestStreet(town, c.location.lat, c.location.lon)
  const contact = view.persona?.contact.name ?? 'your emergency contact'

  const send = async (reply: Reply) => {
    setSending(reply)
    try {
      await store.provider.reply(c.id, reply)
      store.setUi((u) => ({ ...u, replies: { ...u.replies, [c.id]: reply } }))
    } catch {
      toast("We couldn't send your answer", 'Check your connection and try again, or call 911 if you are in danger.')
    } finally {
      setSending(null)
    }
  }

  return (
    <>
      <LargeTitle size="title" sub={`${street ? `${street}, ` : ''}${formatClock(c.opened_at)}`}>
        Your car stopped on a flooded road
      </LargeTitle>

      {view.callBody && (
        <Section>
          <Row icon={PhoneIncoming} title="We're calling your phone" subtitle="Answer the call, or tap below" />
        </Section>
      )}

      <section className={s.stackTight} aria-labelledby="safe-q">
        <h3 id="safe-q" className={s.question}>Are you safe?</h3>
        <div className={s.answers}>
          <button type="button" className={`${s.answer} ${s.answerSafe}`} disabled={sending !== null} onClick={() => send('safe')}>
            <ShieldCheck aria-hidden="true" />
            <span>
              {sending === 'safe' ? 'Sending' : "I'm safe"}
              <span className={s.answerSub}>We'll tell your family and start your claim</span>
            </span>
          </button>
          <button type="button" className={`${s.answer} ${s.answerHelp}`} disabled={sending !== null} onClick={() => send('need_help')}>
            <Hand aria-hidden="true" />
            <span>
              {sending === 'need_help' ? 'Sending' : 'I need help'}
              <span className={s.answerSub}>We'll send rescuers to your car</span>
            </span>
          </button>
        </div>
      </section>

      <section className={s.stackTight} aria-label="If you're in danger right now">
        <Call911 />
        <p className={s.footnote}>If we don't hear back, we'll keep trying you and {contact}, and send help to your location.</p>
      </section>
    </>
  )
}
