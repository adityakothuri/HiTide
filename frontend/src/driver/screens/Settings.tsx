import * as Switch from '@radix-ui/react-switch'
import { BellRing, LocateFixed, Plus, ShieldCheck, Volume2 } from 'lucide-react'
import { useId, useState } from 'react'
import { useToast } from '../../ui/Toast'
import { setSpokenAlerts, speak, spokenAlertsOn } from '../speech'
import { Glyph, LargeTitle, Row, Section } from '../ios'
import iosStyles from '../ios.module.css'
import type { DriverView } from '../useDriverView'
import s from './Screens.module.css'

function SwitchRow({ icon, label, checked, onChange }: { icon: typeof ShieldCheck; label: string; checked: boolean; onChange: (v: boolean) => void }) {
  const id = useId()
  return (
    <div className={`${iosStyles.row} ${iosStyles.withIcon}`}>
      <Glyph icon={icon} />
      <label htmlFor={id} className={iosStyles.rowText}>
        <span className={iosStyles.rowTitle}>{label}</span>
      </label>
      <Switch.Root id={id} className={s.switch} checked={checked} onCheckedChange={onChange}>
        <Switch.Thumb className={s.thumb} />
      </Switch.Root>
    </div>
  )
}

export function Settings({ view }: { view: DriverView }) {
  const toast = useToast()
  const [watch, setWatch] = useState(true)
  const [voice, setVoice] = useState(spokenAlertsOn())
  const p = view.persona

  return (
    <>
      <LargeTitle>Settings</LargeTitle>

      <Section header="Flood Watch" id="fw" footer="We check your usual routes against National Weather Service and USGS flood data. We use your location only while a flood warning is active near you.">
        <SwitchRow icon={ShieldCheck} label="Flood Watch" checked={watch} onChange={setWatch} />
        <Row icon={LocateFixed} title="Location" trailing="During warnings" />
      </Section>

      <Section header="Alerts while driving" id="alerts" footer="Hear turn-around alerts without looking at your phone. Test once before you drive so your phone allows sound.">
        <SwitchRow
          icon={BellRing}
          label="Spoken alerts"
          checked={voice}
          onChange={(v) => {
            setVoice(v)
            setSpokenAlerts(v)
          }}
        />
        <button
          type="button"
          className={`${iosStyles.row} ${iosStyles.withIcon} ${iosStyles.tappable}`}
          disabled={!voice}
          onClick={() => speak('This is a test of Flood Watch spoken alerts.')}
        >
          <Glyph icon={Volume2} />
          <span className={`${iosStyles.rowTitle} ${voice ? s.action : s.actionDisabled}`}>Test spoken alert</span>
        </button>
      </Section>

      <Section header="Emergency contacts" id="ec" footer="We text and call your emergency contacts only if your car stops in floodwater and we can't reach you.">
        {p && <Row title={`${p.contact.name}, ${p.contact.relation}`} subtitle={p.contact.phone} chevron onClick={() => toast('Editing contacts is not part of this prototype')} label={`Edit ${p.contact.name}`} />}
        <button type="button" className={`${iosStyles.row} ${iosStyles.tappable}`} onClick={() => toast('Adding contacts is not part of this prototype')}>
          <Plus className={s.addIcon} aria-hidden="true" />
          <span className={`${iosStyles.rowTitle} ${s.action}`}>Add contact</span>
        </button>
      </Section>
    </>
  )
}
