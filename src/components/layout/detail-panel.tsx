import { cn } from '@/lib/utils'
import { X } from 'lucide-react'

interface DetailPanelProps {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
  width?: number
}

export function DetailPanel({ open, title, onClose, children, width = 360 }: DetailPanelProps) {
  if (!open) return null

  return (
    <div
      className="border-l bg-background flex flex-col shrink-0 overflow-hidden"
      style={{ width }}
    >
      <div className="h-14 flex items-center justify-between px-4 border-b">
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
