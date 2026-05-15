import { cn } from '@/lib/utils'
import { forwardRef, type HTMLAttributes } from 'react'

const ScrollArea = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(({ className, children, ...props }, ref) => (
  <div ref={ref} className={cn('relative overflow-auto', className)} {...props}>
    {children}
  </div>
))
ScrollArea.displayName = 'ScrollArea'

export { ScrollArea }
