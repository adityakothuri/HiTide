import { Camera, Car, CircleCheck, FileText, History, Truck } from 'lucide-react'
import { useToast } from '../../ui/Toast'
import { Btn, LargeTitle, Row, Section } from '../ios'
import type { DriverView } from '../useDriverView'
import s from './Screens.module.css'

/** Claim summary card plus next steps. */
function ClaimPass({ view }: { view: DriverView }) {
  const toast = useToast()
  const p = view.persona
  const claim = p?.claim
  return (
    <>
      <div className={s.pass}>
        <p className={s.passLabel}>Auto claim</p>
        <p className={s.passNumber}>{claim?.number ?? 'Pending'}</p>
        <p className={s.passVehicle}>{view.case?.vehicle ?? p?.vehicle ?? 'Your vehicle'}</p>
        <p className={s.passStatus}><CircleCheck aria-hidden="true" />Started, no action needed</p>
      </div>

      <Section header="Next steps" id="next-steps" footer="Your agent has the details. There is nothing you need to do tonight.">
        <Row icon={Truck} title={`Tow to ${claim?.tow ?? 'a repair shop'}`} subtitle={`Scheduled for ${claim?.towWhen ?? 'tomorrow'}`} />
        <Row icon={Car} title="Rental car" subtitle={claim?.rental ?? 'Reserved near you'} />
        {view.case?.vision && <Row icon={Camera} title="Drone photos attached" subtitle="You don't need to photograph the damage" />}
      </Section>

      <Btn variant="plain" icon={FileText} onClick={() => toast('Claim details are not part of this prototype')}>View claim</Btn>
    </>
  )
}

/** 5.6: after the driver is safe. */
export function Claim({ view }: { view: DriverView }) {
  return (
    <>
      <LargeTitle size="title">You're safe. We started your claim.</LargeTitle>
      <ClaimPass view={view} />
    </>
  )
}

export function ClaimsTab({ view }: { view: DriverView }) {
  const open = view.screen === 'after'
  return (
    <>
      <LargeTitle>Claims</LargeTitle>
      {open ? (
        <ClaimPass view={view} />
      ) : (
        <Section footer="If your car is damaged in a flood, we can start a claim for you from the Flood Watch alert.">
          <Row icon={FileText} title="No open claims" />
        </Section>
      )}
      <Section>
        <Row icon={History} title="Claim history" subtitle="No claims in the last 3 years" />
      </Section>
    </>
  )
}
