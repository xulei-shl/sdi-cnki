import { cn } from '@/lib/utils'
import { forwardRef, type HTMLAttributes } from 'react'

const Tabs = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & { value?: string; onValueChange?: (v: string) => void }>(
  ({ className, ...props }, ref) => <div ref={ref} className={cn('', className)} {...props} />,
)
Tabs.displayName = 'Tabs'

const TabsList = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      'inline-flex h-9 items-center justify-center rounded-lg bg-muted p-1 text-muted-foreground',
      className,
    )}
    {...props}
  />
))
TabsList.displayName = 'TabsList'

const TabsTrigger = forwardRef<HTMLButtonElement, HTMLAttributes<HTMLButtonElement> & { value: string }>(
  ({ className, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow',
        className,
      )}
      {...props}
    />
  ),
)
TabsTrigger.displayName = 'TabsTrigger'

const TabsContent = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement> & { value: string }>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        'mt-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        className,
      )}
      {...props}
    />
  ),
)
TabsContent.displayName = 'TabsContent'

export { Tabs, TabsList, TabsTrigger, TabsContent }
