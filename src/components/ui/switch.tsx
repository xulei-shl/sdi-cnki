import { cn } from '@/lib/utils'
import { forwardRef, type InputHTMLAttributes } from 'react'

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {}

const Switch = forwardRef<HTMLInputElement, SwitchProps>(({ className, checked, ...props }, ref) => {
  return (
    <input
      type="checkbox"
      role="switch"
      data-state={checked ? 'checked' : 'unchecked'}
      className={cn(
        'peer inline-flex h-[24px] w-[44px] shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 accent-primary data-[state=checked]:bg-primary data-[state=unchecked]:bg-input',
        className,
      )}
      ref={ref}
      checked={checked}
      {...props}
    />
  )
})
Switch.displayName = 'Switch'

export { Switch }
