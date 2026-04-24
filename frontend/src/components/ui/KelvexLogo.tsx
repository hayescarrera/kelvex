interface KelvexLogoProps {
  size?: number
  className?: string
}

export default function KelvexLogo({ size = 28, className }: KelvexLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      className={className}
      aria-label="Kelvex"
    >
      {/* Hexagon outline */}
      <path
        d="M32 4 L56 18 L56 46 L32 60 L8 46 L8 18 Z"
        fill="none"
        stroke="#0c7fbb"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      {/* Upper-right arrow (dark teal) */}
      <line x1="18" y1="46" x2="44" y2="16" stroke="#0c7fbb" strokeWidth="3.5" strokeLinecap="round" />
      <polyline points="36,14 44,16 42,24" fill="none" stroke="#0c7fbb" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {/* Lower-right arrow (cyan/light teal) */}
      <line x1="18" y1="18" x2="44" y2="48" stroke="#22b8cf" strokeWidth="3.5" strokeLinecap="round" />
      <polyline points="36,50 44,48 42,40" fill="none" stroke="#22b8cf" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
