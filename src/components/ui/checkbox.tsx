import { cn } from '@/lib/utils'
import { forwardRef, type InputHTMLAttributes } from 'react'

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {}

const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(({ className, ...props }, ref) => {
  return (
    <input
      type="checkbox"
      className={cn(
        'h-4 w-4 rounded border-input text-primary focus:ring-primary',
        className,
      )}
      ref={ref}
      {...props}
    />
  )
})
Checkbox.displayName = 'Checkbox'

export { Checkbox }
