import { cn } from '@/lib/utils'
import { Slot } from '@radix-ui/react-slot'
import { forwardRef, type ButtonHTMLAttributes } from 'react'

const TooltipProvider = ({ children, ...props }: { children: React.ReactNode; delayDuration?: number }) => (
  <div className="contents" {...props}>
    {children}
  </div>
)

const Tooltip = ({ children, content, className, wrapperClassName, disabled }: { children: React.ReactNode; content: React.ReactNode; className?: string; wrapperClassName?: string; disabled?: boolean }) => (
  <div className={cn('relative group inline-block', wrapperClassName)}>
    {children}
    {!disabled && (
      <div
        className={cn(
          'absolute z-50 px-3 py-2 text-sm rounded-lg bg-[#efe4d8] text-foreground border border-[#e0d3c4] shadow-md whitespace-nowrap invisible group-hover:visible opacity-0 group-hover:opacity-100 transition-all duration-200 -translate-x-1/2 left-1/2 bottom-full mb-1',
          className,
        )}
      >
        {content}
      </div>
    )}
  </div>
)
Tooltip.displayName = 'Tooltip'

const TooltipTrigger = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { asChild?: boolean }>(
  ({ className, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp ref={ref} className={cn('', className)} {...props} />
  },
)
TooltipTrigger.displayName = 'TooltipTrigger'

const TooltipContent = ({ className, ...props }: { className?: string; children: React.ReactNode }) => (
  <div className={cn('', className)} {...props} />
)
TooltipContent.displayName = 'TooltipContent'

export { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider }
