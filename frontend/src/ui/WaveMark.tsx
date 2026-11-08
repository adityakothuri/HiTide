/** Simple two-wave HiTide glyph for small, single-colour spots (driver home band). The full logo is LogoMark. */
export function WaveMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={Math.round(size * 1.6)} height={size} viewBox="0 0 40 24" aria-hidden="true">
      <path d="M3 9.5c4.2-4.6 8.4-4.6 12.6 0s8.4 4.6 12.6 0 6.3-3.4 8.8-1.3M3 17.5c4.2-4.6 8.4-4.6 12.6 0s8.4 4.6 12.6 0 6.3-3.4 8.8-1.3"
        stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" fill="none" />
    </svg>
  )
}
