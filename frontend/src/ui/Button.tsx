import type { ButtonHTMLAttributes, ReactNode, Ref } from 'react'
import type { LucideIcon } from 'lucide-react'
import s from './Button.module.css'

export type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'emergency' | 'onDark' | 'safe' | 'critical'
export type ButtonSize = 'md' | 'lg' | 'xl'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  icon?: LucideIcon
  block?: boolean
  children: ReactNode
  ref?: Ref<HTMLButtonElement>
}

export function Button({ variant = 'primary', size = 'md', icon: Icon, block = false, className, children, type = 'button', ref, ...rest }: Props) {
  const dark = variant === 'emergency' || variant === 'primary' ? 'on-dark' : ''
  const cls = [s.button, s[variant], s[size], block ? s.block : '', dark, className ?? ''].join(' ')
  return (
    <button ref={ref} type={type} className={cls} {...rest}>
      {Icon && <Icon className={s.icon} aria-hidden="true" strokeWidth={2} />}
      <span>{children}</span>
    </button>
  )
}
