import { useState, useRef, useEffect, Children, isValidElement, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { ChevronDown, Check } from 'lucide-react'

export interface SelectProps {
  value?: string | number
  onChange?: (e: { target: { value: string } }) => void
  onBlur?: () => void
  className?: string
  disabled?: boolean
  children?: ReactNode
}

const Select = ({ value, onChange, onBlur, className, disabled, children }: SelectProps) => {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const options = Children.toArray(children)
    .filter((child): child is React.ReactElement<{ value?: unknown; disabled?: boolean; children?: ReactNode }> =>
      isValidElement(child) && (child.type === 'option' || (typeof child.type === 'function' && child.type.name === 'option')),
    )
    .map(child => ({
      value: String(child.props.value ?? ''),
      label: child.props.children,
      disabled: child.props.disabled,
    }))

  const selectedOption = options.find(o => o.value === String(value))
  const selectedLabel = selectedOption?.label ?? null

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        onBlur?.()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open, onBlur])

  return (
    <div ref={ref} className={cn('relative w-full', className)}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(!open)}
        className={cn(
          'flex h-9 w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-all duration-200',
          'hover:bg-accent/50 hover:border-accent-foreground/20',
          'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-50',
          open && 'ring-1 ring-ring border-accent-foreground/20'
        )}
      >
        <span className={cn('truncate', !selectedLabel && 'text-muted-foreground')}>
          {selectedLabel ?? '请选择'}
        </span>
        <ChevronDown className={cn('h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-300', open && 'rotate-180')} />
      </button>

      {open && (
        <>
          {/* Overlay to close on outside click */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />

          <div className={cn(
            "absolute left-0 top-full mt-1 z-50 min-w-full rounded-md border bg-popover p-1 shadow-md",
            "animate-in fade-in zoom-in-95 duration-200 origin-top"
          )}>
            <div className="max-h-[300px] overflow-y-auto overflow-x-hidden custom-scrollbar">
              {options.length === 0 ? (
                <div className="px-2 py-1.5 text-sm text-muted-foreground text-center">无选项</div>
              ) : (
                options.map(opt => {
                  const isSelected = String(value) === opt.value
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      disabled={opt.disabled}
                      className={cn(
                        'flex w-full items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-sm text-left transition-colors',
                        'hover:bg-accent hover:text-accent-foreground',
                        'disabled:opacity-50 disabled:pointer-events-none',
                        isSelected && 'bg-accent/40 font-medium text-primary'
                      )}
                      onClick={() => {
                        onChange?.({ target: { value: opt.value } })
                        setOpen(false)
                        onBlur?.()
                      }}
                    >
                      <span className="truncate flex-1">{opt.label}</span>
                      {isSelected && <Check className="h-3.5 w-3.5 shrink-0 text-primary animate-in fade-in zoom-in-50 duration-300" />}
                    </button>
                  )
                })
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export { Select }
