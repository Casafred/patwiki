interface BrandWordmarkProps {
  width?: number
  className?: string
  decorative?: boolean
}

export default function BrandWordmark({ width = 190, className = '', decorative = false }: BrandWordmarkProps) {
  return <img
    src="/patwiki-logo-wordmark.svg"
    width={width}
    height={Math.round(width * 0.25)}
    className={`patwiki-brand-wordmark ${className}`.trim()}
    alt={decorative ? '' : 'patwiki · patent knowledge workspace'}
    draggable={false}
  />
}
