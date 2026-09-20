import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

const base =
  'inline-flex items-center justify-center rounded-[10px] font-semibold transition-colors ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

const variants: Record<Variant, string> = {
  primary: 'bg-sage text-cream hover:bg-sage-dark',
  secondary: 'border border-line bg-cream text-ink hover:bg-cream-dark',
  ghost: 'text-ink/70 hover:bg-cream-dark hover:text-ink',
}

const sizes: Record<Size, string> = {
  sm: 'px-2.5 py-1.5 text-[13px]',
  md: 'px-4 py-2.5 text-sm',
  lg: 'px-6 py-3.5 text-[15px]',
}

type Props = { variant?: Variant; size?: Size } & ButtonHTMLAttributes<HTMLButtonElement>

export function Button({ variant = 'primary', size = 'md', className = '', ...props }: Props) {
  return <button className={`${base} ${variants[variant]} ${sizes[size]} ${className}`} {...props} />
}
