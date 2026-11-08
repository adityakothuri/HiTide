import * as Tooltip from '@radix-ui/react-tooltip'
import type { ReactNode } from 'react'
import s from './Tip.module.css'

export function Tip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return (
    <Tooltip.Root delayDuration={200}>
      <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Content className={s.tip} sideOffset={6}>
          {content}
        </Tooltip.Content>
      </Tooltip.Portal>
    </Tooltip.Root>
  )
}

export const TipProvider = Tooltip.Provider
