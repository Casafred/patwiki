interface BrandLogoProps {
  size?: number
  className?: string
  decorative?: boolean
}

export default function BrandLogo({ size = 32, className = '', decorative = false }: BrandLogoProps) {
  return <img
    src="/patwiki-logo.svg"
    width={size}
    height={size}
    className={`patwiki-brand-logo ${className}`.trim()}
    alt={decorative ? '' : 'PatWiki'}
    draggable={false}
  />
}
