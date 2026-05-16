import { cn } from '@/lib/utils'
import { X } from 'lucide-react'

interface DetailPanelProps {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
  width?: number
}

export function DetailPanel({ open, title, onClose, children, width = 600 }: DetailPanelProps) {
  return (
    <>
      <div
        className={cn(
          "absolute inset-0 bg-background/60 backdrop-blur-sm z-40 transition-all duration-300",
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
        <div className="h-16 flex items-center justify-between px-6 border-b shrink-0 bg-muted/30">
          <h2 className="text-base font-semibold tracking-tight text-foreground truncate">{title}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-8 space-y-8">
          {children}
        </div>
      </div>
    </>
  )
}

export function DetailSection({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('space-y-3 relative', className)}>
      <h3 className="text-sm font-semibold text-foreground tracking-tight">{label}</h3>
      <div className="bg-muted/10 rounded-lg p-1 border space-y-0.5">
        {children}
      </div>
    </div>
  )
}

export function DetailRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between items-start py-2 px-3 rounded-md transition-colors hover:bg-muted/40 group">
      <span className="text-sm font-medium text-muted-foreground shrink-0 mr-4 w-[120px] group-hover:text-foreground/80 transition-colors leading-relaxed">{label}</span>
      <span className="text-sm text-right break-words flex-1 text-foreground font-medium leading-relaxed">{children}</span>
    </div>
  )
}
