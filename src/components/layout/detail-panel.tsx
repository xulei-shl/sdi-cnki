import { cn } from '@/lib/utils'
import { X } from 'lucide-react'

interface DetailPanelProps {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
  width?: number
}

export function DetailPanel({ open, title, onClose, children, width = 560 }: DetailPanelProps) {
  return (
    <>
      <div
        className={cn(
          "absolute inset-0 bg-background/40 backdrop-blur-sm z-40 transition-all duration-300",
          open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        )}
        onClick={onClose}
      />
      <div
        className={cn(
          "absolute right-0 top-0 bottom-0 border-l shadow-2xl bg-background flex flex-col shrink-0 overflow-hidden transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] z-50",
          open ? "translate-x-0" : "translate-x-full"
        )}
        style={{ width }}
      >
        <div className="h-14 flex items-center justify-between px-4 border-b shrink-0">
          <h2 className="text-sm font-medium truncate">{title}</h2>
          <button
            onClick={onClose}
            className="p-1 rounded-md hover:bg-accent transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {children}
        </div>
      </div>
    </>
  )
}

export function DetailSection({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('space-y-1', className)}>
      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</h3>
      {children}
    </div>
  )
}

export function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-sm text-muted-foreground shrink-0 mr-2">{label}</span>
      <span className="text-sm text-right break-all">{children}</span>
    </div>
  )
}
