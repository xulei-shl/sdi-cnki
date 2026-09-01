import type { TaskStatus } from '@/types'

export const STEP_CONFIG: { label: string; match: TaskStatus[] }[] = [
  { label: '待执行', match: ['pending'] },
  { label: '检索排队中', match: ['search_queued'] },
  { label: '检索中', match: ['running', 'search_completed'] },
  { label: '分析中', match: ['analyzing'] },
  { label: '审核中', match: ['analyzing_completed'] },
  { label: '下载排队中', match: ['download_queued'] },
  { label: '下载中', match: ['downloading'] },
  { label: '已完成', match: ['completed'] },
]

export const DOWNLOAD_BADGE: Record<string, { label: string; variant: 'success' | 'destructive' | 'secondary' | 'info' | 'warning' }> = {
  pending: { label: '未下载', variant: 'secondary' },
  downloading: { label: '下载中', variant: 'info' },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'destructive' },
  skipped: { label: '跳过', variant: 'secondary' },
}

export const ANALYSIS_FILTER_OPTIONS = [
  { label: '分析状态', value: '' },
  { label: '已完成', value: 'completed' },
  { label: '未分析', value: 'pending' },
  { label: '失败', value: 'failed' },
]

export const ANALYSIS_RESULT_OPTIONS = [
  { label: '分析结论', value: '' },
  { label: '通过', value: 'passed' },
  { label: '拒绝', value: 'rejected' },
]

export const REVIEW_OPTIONS = [
  { label: '审核结论', value: '' },
  { label: '待审核', value: 'pending' },
  { label: '已通过', value: 'passed' },
  { label: '已拒绝', value: 'rejected' },
]

export const DOWNLOAD_STATUS_OPTIONS = [
  { label: '下载状态', value: '' },
  { label: '未下载', value: 'pending' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
  { label: '跳过', value: 'skipped' },
]

export const SCORE_OPTIONS = [
  { label: '评分', value: '' },
  { label: '≥4', value: '4' },
  { label: '≥6', value: '6' },
  { label: '≥8', value: '8' },
  { label: '≥9', value: '9' },
]

export function analysisTextColor(status?: string, isTargetTopic?: boolean | null): string {
  if (status === 'failed') return 'text-red-500'
  if (status === 'analyzing') return 'text-blue-500'
  if (status === 'completed') {
    if (isTargetTopic === true) return 'text-green-600'
    if (isTargetTopic === false) return 'text-amber-500'
    return 'text-muted-foreground'
  }
  return 'text-muted-foreground'
}

export function reviewTextColor(isPassed: boolean | null): string {
  if (isPassed === true) return 'text-green-600'
  if (isPassed === false) return 'text-amber-500'
  return 'text-muted-foreground'
}

export function downloadTextColor(status?: string): string {
  if (status === 'completed') return 'text-green-600'
  if (status === 'failed') return 'text-red-500'
  if (status === 'downloading') return 'text-blue-500'
  if (status === 'skipped') return 'text-muted-foreground'
  return 'text-muted-foreground'
}

export function getAnalysisLabel(status?: string, parsedResult?: any): string {
  if (status === 'failed') return '失败'
  if (status === 'analyzing') return '进行中'
  if (status === 'completed') {
    if (parsedResult?.is_target_topic === true) return '通过'
    if (parsedResult?.is_target_topic === false) return '拒绝'
    return '已完成'
  }
  return '未分析'
}

export function relevanceColor(score: number | null): string {
  if (score === null) return 'text-muted-foreground'
  if (score >= 7) return 'text-green-600 font-medium'
  if (score >= 4) return 'text-blue-600'
  return 'text-gray-400'
}

export function formatDate(d: string | null | undefined): string {
  return d ? d.slice(0, 16).replace('T', ' ') : '-'
}
