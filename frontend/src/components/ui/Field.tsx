import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react'
import { cn } from '../../lib/cn'

/* The designs are placeholder-and-icon driven, so labels are visually hidden rather than dropped -
   every control still has an accessible name. */
const CONTROL =
  'rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-muted ' +
  'transition-colors focus:border-accent focus:ring-2 focus:ring-accent/20 focus:outline-none ' +
  'disabled:cursor-not-allowed disabled:bg-canvas disabled:text-ink-muted'

interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
}

export function TextInput({ label, className, ...rest }: TextInputProps) {
  return (
    <label className="block">
      <span className="sr-only">{label}</span>
      <input className={cn(CONTROL, 'w-full', className)} {...rest} />
    </label>
  )
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string
  hint?: string
}

export function Textarea({ label, hint, className, ...rest }: TextareaProps) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-ink-soft">{label}</span>
      <textarea className={cn(CONTROL, 'mt-1 w-full font-mono text-xs', className)} {...rest} />
      {hint && <span className="mt-1 block text-[11px] leading-relaxed text-ink-muted">{hint}</span>}
    </label>
  )
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  children: ReactNode
}

export function Select({ label, className, children, ...rest }: SelectProps) {
  return (
    <label className="block">
      <span className="sr-only">{label}</span>
      <select className={cn(CONTROL, 'cursor-pointer pr-8', className)} {...rest}>
        {children}
      </select>
    </label>
  )
}
