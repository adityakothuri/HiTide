import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { useState } from 'react'
import type { VisionResult } from '../data/types'
import { droneImage } from '../lib/media'
import { useStore } from '../state/StoreContext'
import s from './Detail.module.css'

const LEVEL: Record<VisionResult['water_level'], string> = {
  none: 'No water at the car',
  wheels: 'Up to the wheels',
  doors: 'Up to the doors',
  windows: 'Up to the windows',
  roof: 'Over the roof',
}

const PLACEMENT: Record<VisionResult['people'][number]['placement'], string> = {
  on_roof: 'on the roof',
  in_water: 'in the water',
  on_shore: 'on shore',
  inside_unknown: 'possibly inside',
}

function peopleText(v: VisionResult): string {
  if (v.people.length === 0) return 'No people seen'
  const groups = new Map<string, number>()
  for (const p of v.people) groups.set(p.placement, (groups.get(p.placement) ?? 0) + 1)
  return [...groups].map(([k, n]) => `${n} ${n === 1 ? 'person' : 'people'} ${PLACEMENT[k as keyof typeof PLACEMENT]}`).join(', ')
}

interface Shot { src: string; alt: string; label: string; tag: string | null }

export function VisionPanel({ vision: v }: { vision: VisionResult }) {
  const store = useStore()
  const kind = store.provider.kind
  const boat = v.recommendation === 'boat_required'
  const [open, setOpen] = useState<Shot | null>(null)
  const shots: Shot[] = [
    {
      src: droneImage(v.image_url, kind),
      alt: `Drone ${v.night_mode ? 'thermal' : 'camera'} view of the car`,
      label: v.night_mode ? 'Thermal' : 'Camera',
      tag: v.thermal_simulated ? 'Simulated thermal' : null,
    },
    { src: droneImage(v.annotated_url, kind), alt: 'Drone image with the car and people outlined', label: 'Detections', tag: 'Sample image' },
  ]

  return (
    <section className={s.section} aria-labelledby="vision-h">
      <h3 id="vision-h" className={s.sectionTitle}>What the drone sees</h3>
      <p className={s.verdict}>{boat ? 'Boat required' : 'Truck route available'}</p>
      <p className={s.visionFacts}>{LEVEL[v.water_level]}. {peopleText(v)}.</p>
      <div className={s.thumbs}>
        {shots.map((shot) => (
          <button key={shot.label} type="button" className={s.thumb} onClick={() => setOpen(shot)} aria-label={`Enlarge ${shot.label.toLowerCase()} image`}>
            <img src={shot.src} alt={shot.alt} />
            <span className={s.thumbLabel}>{shot.label}</span>
          </button>
        ))}
      </div>

      <Dialog.Root open={open !== null} onOpenChange={(o) => !o && setOpen(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className={s.lightboxOverlay} />
          <Dialog.Content className={s.lightbox} data-theme="dispatch" aria-describedby={undefined}>
            {open && (
              <>
                <div className={s.lightboxHead}>
                  <Dialog.Title className={s.lightboxTitle}>{open.label}</Dialog.Title>
                  {open.tag && <span className={s.lightboxTag}>{open.tag}</span>}
                  <Dialog.Close className={s.lightboxClose} aria-label="Close image">
                    <X aria-hidden="true" />
                  </Dialog.Close>
                </div>
                <img className={s.lightboxImg} src={open.src} alt={open.alt} />
              </>
            )}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </section>
  )
}
