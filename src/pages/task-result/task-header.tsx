import { Check } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { STEP_CONFIG, formatDate } from './constants'
import type { TaskInstance } from '@/types'

interface TaskHeaderProps {
  instance: TaskInstance | null
  stepIndex: number
  analyzeProgress: { active: boolean; analyzed: number; total: number; failed: number }
  downloadProgress: { active: boolean; success: number; failed: number; total: number }
  onBack: () => void
}

export function TaskHeader({ instance, stepIndex, analyzeProgress, downloadProgress, onBack }: TaskHeaderProps) {
  return (
    <div className="px-8 pt-5 pb-5 border-b shrink-0 flex flex-col gap-5 bg-muted/10">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack}>&lt; 返回</Button>
          <span className="font-medium text-lg">{instance?.instance_no} - {instance?.meta_task_name}</span>
          {instance?.status === 'failed' && <Badge variant="destructive">{instance.error_message}</Badge>}
          {instance?.status === 'cancelled' && <Badge variant="secondary">已取消</Badge>}
        </div>
        <span className="text-sm text-muted-foreground">{formatDate(instance?.created_at)}</span>
      </div>

      {/* Stage Indicator */}
      <div className="flex items-center justify-between max-w-4xl mx-auto w-full">
        {STEP_CONFIG.map((step, i) => {
          const isActive = i === stepIndex
          const isDone = i < stepIndex
          const isError = instance?.status === 'failed'
          return (
            <div key={step.label} className="flex flex-col items-center gap-1.5">
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium border
                  ${isError && i === STEP_CONFIG.length - 1 ? 'border-destructive bg-destructive text-destructive-foreground' : ''}
                  ${isActive && !isError ? 'border-primary bg-primary text-primary-foreground shadow-sm' : ''}
                  ${isDone && !isError ? 'border-green-500 bg-green-500 text-white' : ''}
                  ${!isActive && !isDone && !(isError && i === STEP_CONFIG.length - 1) ? 'border-muted-foreground/30 text-muted-foreground' : ''}`}
              >
                {isDone ? <Check className="w-3.5 h-3.5" /> : i + 1}
              </div>
              <span className={`text-[11px] ${isActive ? 'font-medium text-primary' : isDone ? 'text-green-600' : 'text-muted-foreground'}`}>
                {step.label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Progress Indicators */}
      {analyzeProgress.active && analyzeProgress.total > 0 && (
        <div className="text-center text-xs text-blue-500 animate-pulse transition-all duration-300">
          <span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-2" />
          LLM 分析进度: {analyzeProgress.analyzed} / {analyzeProgress.total} (失败 {analyzeProgress.failed})
        </div>
      )}
      {downloadProgress.active && (
        <div className="text-center text-xs text-amber-500 animate-pulse transition-all duration-300">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-2" />
          下载进度: 成功 {downloadProgress.success} / 失败 {downloadProgress.failed} / 总计 {downloadProgress.total}
        </div>
      )}
    </div>
  )
}
