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
      <path d="M32 4L56 18V46L32 60L8 46V18L32 4Z" fill="#0f172a" />
      <path d="M22 17V47" stroke="white" strokeWidth="5.5" strokeLinecap="round" />
      <path d="M22 32L44 17" stroke="white" strokeWidth="5.5" strokeLinecap="round" />
      <path d="M22 32L44 47" stroke="white" strokeWidth="5.5" strokeLinecap="round" />
      <circle cx="22" cy="32" r="5" fill="#0369ea" />
    </svg>
  )
}
