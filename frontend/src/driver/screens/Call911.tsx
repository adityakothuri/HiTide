import { Phone } from 'lucide-react'
import { useToast } from '../../ui/Toast'
import { Btn } from '../ios'

/** In the prototype this never dials. A real build would use a tel: link. */
export function Call911() {
  const toast = useToast()
  return (
    <Btn
      variant="dark"
      icon={Phone}
      onClick={() => toast('Calling 911 is turned off in this prototype', 'In a real emergency, dial 911 from your phone.')}
    >
      Call 911
    </Btn>
  )
}
