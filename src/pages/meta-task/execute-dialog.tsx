import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'

interface ExecuteDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onRunDirect: () => void
  onRunDraft: () => void
  loading: boolean
}

export function ExecuteDialog({ open, onOpenChange, onRunDirect, onRunDraft, loading }: ExecuteDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>确认执行</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          将基于此模板创建新的任务实例并执行。
        </p>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button variant="secondary" onClick={onRunDraft} disabled={loading}>
            {loading ? '处理中...' : '确认后运行'}
          </Button>
          <Button onClick={onRunDirect} disabled={loading}>
            {loading ? '执行中...' : '直接运行'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
