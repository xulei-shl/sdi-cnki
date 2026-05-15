import { cn } from '@/lib/utils'
import { forwardRef, type HTMLAttributes } from 'react'

const Progress = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & { value?: number }>(
  ({ className, value, ...props }, ref) => (
    <div ref={ref} className={cn('relative h-2 w-full overflow-hidden rounded-full bg-primary/20', className)} {...props}>
      <div
        className="h-full w-full flex-1 bg-primary transition-all"
        style={{ transform: `translateX(-${100 - (value ?? 0)}%)` }}
      />
    </div>
  ),
)
Progress.displayName = 'Progress'

export { Progress }
