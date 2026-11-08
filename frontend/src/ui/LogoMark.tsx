/** The HiTide logo: a shield with a breaking wave (design/brand/hitide-logo.png). Decorative next to the name. */
export function LogoMark({ size = 26, className }: { size?: number; className?: string }) {
  return <img src="/hitide-logo.png" alt="" aria-hidden="true" width={size} height={size} className={className} style={{ flex: 'none', objectFit: 'contain' }} />
}
