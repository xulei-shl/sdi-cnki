import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Pagination } from '@/components/ui/pagination'
import { DetailPanel, DetailSection, DetailRow } from '@/components/layout/detail-panel'
import { Separator } from '@/components/ui/separator'
import { toast } from 'sonner'
import { getTaskInstance } from '@/api/task-instances'
import { getTaskResults, markPass, batchUpdateResults, startDownload } from '@/api/task-results'
import { SseClient } from '@/lib/sse'
import { Check } from 'lucide-react'
import type { TaskInstance, TaskStatus } from '@/types'

const STEP_CONFIG: { label: string; match: TaskStatus[] }[] = [
  { label: '待执行', match: ['pending'] },
  { label: '检索中', match: ['running', 'search_completed'] },
  { label: '分析中', match: ['analyzing'] },
  { label: '审核中', match: ['analyzing_completed'] },
  { label: '等待下载', match: ['ready_for_download'] },
  { label: '下载中', match: ['downloading'] },
  { label: '已完成', match: ['completed'] },
]

const ANALYSIS_BADGE: Record<string, { label: string; variant: 'success' | 'destructive' | 'secondary' | 'info' | 'warning' }> = {
  pending: { label: '未分析', variant: 'secondary' },
  analyzing: { label: '进行中', variant: 'info' },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'destructive' },
}

const DOWNLOAD_BADGE: Record<string, { label: string; variant: 'success' | 'destructive' | 'secondary' | 'info' | 'warning' }> = {
  pending: { label: '未下载', variant: 'secondary' },
  downloading: { label: '下载中', variant: 'info' },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'destructive' },
  skipped: { label: '跳过', variant: 'warning' },
}

const REVIEW_OPTIONS = [
  { label: '全部', value: '' },
  { label: '待审核', value: 'pending' },
  { label: '已通过', value: 'passed' },
  { label: '已拒绝', value: 'rejected' },
]

const ANALYSIS_FILTER_OPTIONS = [
  { label: '全部', value: '' },
  { label: '已完成', value: 'completed' },
  { label: '未分析', value: 'pending' },
  { label: '失败', value: 'failed' },
]

export default function TaskResultPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const instanceId = Number(id)
  const [instance, setInstance] = useState<TaskInstance | null>(null)
  const [results, setResults] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [activeResult, setActiveResult] = useState<any>(null)
  const [showDetail, setShowDetail] = useState(false)

  // SSE progress state
  const [analyzeProgress, setAnalyzeProgress] = useState({ active: false, analyzed: 0, total: 0, failed: 0 })
  const [downloadProgress, setDownloadProgress] = useState({ active: false, success: 0, failed: 0, skipped: 0, total: 0 })

  // Filters
  const [reviewStatus, setReviewStatus] = useState('')
  const [analysisStatus, setAnalysisStatus] = useState('')
  const [journalKeyword, setJournalKeyword] = useState('')
  const [publishYear, setPublishYear] = useState('')
  const [minScore, setMinScore] = useState('')
  const [includeDuplicate, setIncludeDuplicate] = useState(false)

  const sseRef = useRef<SseClient | null>(null)
  const getAuthToken = () => localStorage.getItem('access_token') || ''

  const fetchInstance = useCallback(async () => {
    try {
      const res = await getTaskInstance(instanceId)
      setInstance(res.data)
    } catch { /* ignore */ }
  }, [instanceId])

  const fetchResults = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { instance_id: instanceId, page, page_size: 20 }
      if (reviewStatus) params.review_status = reviewStatus
      if (analysisStatus) params.analysis_status = analysisStatus
      if (journalKeyword) params.journal_keyword = journalKeyword
      if (publishYear) params.publish_year = parseInt(publishYear)
      if (minScore) params.min_score = parseInt(minScore)
      if (includeDuplicate) params.include_duplicate = true
      const res = await getTaskResults(params)
      setResults(res.data.items || [])
      setTotal(res.data.total || 0)
    } finally {
      setLoading(false)
    }
  }, [instanceId, page, reviewStatus, analysisStatus, journalKeyword, publishYear, minScore, includeDuplicate])

  useEffect(() => { fetchInstance(); fetchResults() }, [fetchInstance, fetchResults])

  useEffect(() => {
    const token = getAuthToken()
    if (!token || !instance) return
    if (['completed', 'failed', 'cancelled'].includes(instance.status)) return

    const sse = new SseClient(instanceId, token)
    sseRef.current = sse
    sse.on('task.progress', (data: any) => {
      if (data.status === 'analyzing') {
        setAnalyzeProgress({ active: true, analyzed: data.analyzed ?? 0, total: data.total ?? 0, failed: data.failed ?? 0 })
      } else if (['search_completed', 'analyzing_completed', 'completed'].includes(data.status)) {
        fetchInstance(); fetchResults()
      }
    })
    sse.on('download.progress', (data: any) => {
      setDownloadProgress({ active: true, success: data.success ?? 0, failed: data.failed ?? 0, skipped: data.skipped ?? 0, total: data.total ?? 0 })
    })
    sse.on('task.completed', () => { fetchInstance(); fetchResults() })
    sse.on('task.failed', () => { fetchInstance(); fetchResults() })
    sse.connect()

    return () => { sse.close() }
  }, [instanceId, instance?.status])

  const stepIndex = instance ? STEP_CONFIG.findIndex(s => s.match.includes(instance.status)) : -1

  const handleFilter = () => { setPage(1); fetchResults() }

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === results.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(results.map(r => r.id)))
    }
  }

  const handleSinglePass = async (row: any) => {
    try {
      await markPass(row.id)
      row.is_passed = row.is_passed === true ? null : true
      toast.success(row.is_passed ? '已通过' : '已取消')
    } catch { toast.error('操作失败') }
  }

  const handleSingleReject = async (row: any) => {
    try {
      await markPass(row.id)
      row.is_passed = row.is_passed === false ? null : false
      toast.success(row.is_passed === false ? '已拒绝' : '已取消')
    } catch { toast.error('操作失败') }
  }

  const handleBatchPass = async () => {
    const ids = results.filter(r => selectedIds.has(r.id) && r.is_passed !== true).map(r => r.id)
    if (!ids.length) { toast.info('已全部通过'); return }
    try {
      await batchUpdateResults(instanceId, { ids, action: 'pass' })
      toast.success(`已通过 ${ids.length} 条`)
      fetchResults()
    } catch { toast.error('批量操作失败') }
  }

  const handleBatchReject = async () => {
    const ids = results.filter(r => selectedIds.has(r.id) && r.is_passed !== false).map(r => r.id)
    if (!ids.length) { toast.info('已全部拒绝'); return }
    if (!confirm('确认批量拒绝所选结果？')) return
    try {
      await batchUpdateResults(instanceId, { ids, action: 'reject' })
      toast.success(`已拒绝 ${ids.length} 条`)
      fetchResults()
    } catch { toast.error('批量操作失败') }
  }

  const handleDownload = async () => {
    try {
      await startDownload(instanceId)
      toast.success('下载任务已加入队列')
    } catch { toast.error('启动下载失败') }
  }

  const viewDetail = (row: any) => {
    setActiveResult(row)
    setShowDetail(true)
  }

  const relevanceColor = (score: number | null) => {
    if (score === null) return ''
    if (score >= 7) return 'bg-green-500'
    if (score >= 4) return 'bg-blue-500'
    return 'bg-gray-400'
  }

  const formatDate = (d: string | null | undefined) => d ? d.slice(0, 16).replace('T', ' ') : '-'

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header Area */}
      <div className="px-8 pt-8 pb-8 border-b shrink-0 flex flex-col gap-8 bg-muted/10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={() => navigate('/task-instances')}>&lt; 返回</Button>
            <span className="font-medium text-lg">{instance?.instance_no} - {instance?.meta_task_name}</span>
            {instance?.status === 'failed' && <Badge variant="destructive">{instance.error_message}</Badge>}
            {instance?.status === 'cancelled' && <Badge variant="secondary">已取消</Badge>}
          </div>
          <span className="text-sm text-muted-foreground">{formatDate(instance?.created_at)}</span>
        </div>

        {/* Stage Indicator */}
        <div className="flex items-center justify-between max-w-3xl mx-auto w-full">
          {STEP_CONFIG.map((step, i) => {
            const isActive = i === stepIndex
            const isDone = i < stepIndex
            const isError = instance?.status === 'failed'
            return (
              <div key={step.label} className="flex flex-col items-center gap-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-medium border-2
                  ${isError && i === STEP_CONFIG.length - 1 ? 'border-destructive bg-destructive text-destructive-foreground' : ''}
                  ${isActive && !isError ? 'border-primary bg-primary text-primary-foreground shadow-sm' : ''}
                  ${isDone && !isError ? 'border-green-500 bg-green-500 text-white' : ''}
                  ${!isActive && !isDone && !(isError && i === STEP_CONFIG.length - 1) ? 'border-muted-foreground/30 text-muted-foreground' : ''}`}>
                  {isDone ? <Check className="w-4 h-4" /> : i + 1}
                </div>
                <span className={`text-xs ${isActive ? 'font-medium text-primary' : isDone ? 'text-green-600' : 'text-muted-foreground'}`}>
                  {step.label}
                </span>
              </div>
            )
          })}
        </div>
        {analyzeProgress.active && analyzeProgress.total > 0 && (
          <div className="text-center text-xs text-blue-500 animate-pulse transition-all duration-300">
            <span className="inline-block w-2 h-2 rounded-full bg-blue-500 mr-2" />
            LLM 分析进度: {analyzeProgress.analyzed} / {analyzeProgress.total} (失败 {analyzeProgress.failed})
          </div>
        )}
        {downloadProgress.active && (
          <div className="text-center text-xs text-amber-500 animate-pulse transition-all duration-300">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-2" />
            下载进度: 成功 {downloadProgress.success} / 失败 {downloadProgress.failed} / 跳过 {downloadProgress.skipped} / 总计 {downloadProgress.total}
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Results Table */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Action & Filter Toolbar */}
          <div className="px-8 py-5 border-b flex items-center justify-between flex-wrap gap-6 shrink-0">
            {/* Filters */}
            <div className="flex items-center gap-3 flex-wrap">
              <Select value={reviewStatus} onChange={(e) => setReviewStatus(e.target.value)} className="w-[120px]">
                {REVIEW_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <Select value={analysisStatus} onChange={(e) => setAnalysisStatus(e.target.value)} className="w-[120px]">
                {ANALYSIS_FILTER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <Input placeholder="期刊名称" value={journalKeyword} onChange={(e) => setJournalKeyword(e.target.value)} className="w-[150px]" />
              <Input placeholder="年份" value={publishYear} onChange={(e) => setPublishYear(e.target.value)} className="w-[80px]" />
              <Select value={minScore} onChange={(e) => setMinScore(e.target.value)} className="w-[100px]">
                <option value="">评分不限</option>
                <option value="4">≥4</option>
                <option value="6">≥6</option>
                <option value="8">≥8</option>
                <option value="9">≥9</option>
              </Select>
              <label className="flex items-center gap-1 text-sm bg-accent/50 px-2 py-1.5 rounded-md">
                <Checkbox checked={includeDuplicate} onChange={(e) => setIncludeDuplicate(e.target.checked)} />
                <span className="ml-1">含重复</span>
              </label>
              <Button size="sm" variant="secondary" onClick={handleFilter}>筛选</Button>
            </div>

            {/* Batch Actions */}
            <div className="flex items-center gap-3">
              {selectedIds.size > 0 && <span className="text-sm font-medium text-primary">已选中 {selectedIds.size} 项</span>}
              <Button size="sm" variant="secondary" disabled={selectedIds.size === 0} onClick={handleBatchPass}>批量通过</Button>
              <Button size="sm" variant="secondary" disabled={selectedIds.size === 0} onClick={handleBatchReject}>批量拒绝</Button>
              {['analyzing_completed', 'ready_for_download', 'downloading'].includes(instance?.status || '') && (
                <Button size="sm" onClick={handleDownload}>开始下载</Button>
              )}
            </div>
          </div>

          {/* Table */}
          <div className="flex-1 overflow-auto px-8 py-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={results.length > 0 && selectedIds.size === results.length}
                      onChange={toggleAll}
                    />
                  </TableHead>
                  <TableHead className="min-w-[250px]">题名</TableHead>
                  <TableHead className="w-[160px]">作者</TableHead>
                  <TableHead className="w-[180px]">期刊</TableHead>
                  <TableHead className="w-[120px]">相关性</TableHead>
                  <TableHead className="w-[80px]">分析</TableHead>
                  <TableHead className="w-[80px]">审核</TableHead>
                  <TableHead className="w-[80px]">下载</TableHead>
                  <TableHead className="w-[160px]">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={9} className="text-center py-12">
                      <div className="flex items-center justify-center gap-2 text-muted-foreground animate-pulse">
                        <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                        数据加载中...
                      </div>
                    </TableCell>
                  </TableRow>
                ) : results.length === 0 ? (
                  <TableRow><TableCell colSpan={9} className="text-center py-8 text-muted-foreground">暂无数据</TableCell></TableRow>
                ) : results.map((row) => {
                  const score = row.llm_analysis?.parsed_result?.relevance_score ?? null
                  return (
                    <TableRow key={row.id}>
                      <TableCell>
                        <Checkbox checked={selectedIds.has(row.id)} onChange={() => toggleSelect(row.id)} />
                      </TableCell>
                      <TableCell>
                        <div className="truncate max-w-[250px]" title={row.title}>
                          {row.title}
                          {row.is_duplicate && <Badge variant="warning" className="ml-1 text-xs">重复</Badge>}
                        </div>
                      </TableCell>
                      <TableCell className="truncate max-w-[160px]">{row.authors || '-'}</TableCell>
                      <TableCell className="truncate max-w-[180px]">{row.source_journal} ({row.publish_year})</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                            <div className={`h-full rounded-full transition-all ${relevanceColor(score)}`} style={{ width: `${score ? (score / 10) * 100 : 0}%` }} />
                          </div>
                          <span className="text-xs w-7 text-right">{score ?? '-'}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={ANALYSIS_BADGE[row.llm_analysis?.status || 'pending'].variant} className="text-xs">
                          {ANALYSIS_BADGE[row.llm_analysis?.status || 'pending'].label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={row.is_passed === true ? 'success' : row.is_passed === false ? 'destructive' : 'secondary'} className="text-xs">
                          {row.is_passed === true ? '通过' : row.is_passed === false ? '拒绝' : '未审'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={DOWNLOAD_BADGE[row.download?.download_status || 'pending'].variant} className="text-xs">
                          {DOWNLOAD_BADGE[row.download?.download_status || 'pending'].label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="sm" onClick={() => viewDetail(row)}>详情</Button>
                          <Button variant="ghost" size="sm" onClick={() => handleSinglePass(row)}>
                            {row.is_passed === true ? '取消' : '通过'}
                          </Button>
                          <Button variant="ghost" size="sm" onClick={() => handleSingleReject(row)}>
                            {row.is_passed === false ? '取消' : '拒绝'}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            <Pagination current={page} total={total} pageSize={20} onChange={setPage} />
          </div>
        </div>

        {/* Right Detail Panel */}
        <DetailPanel
          open={showDetail}
          title={activeResult?.title || ''}
          onClose={() => { setShowDetail(false); setActiveResult(null) }}
          width={640}
        >
          {activeResult && (
            <>
              <DetailSection label="文献信息">
                <DetailRow label="题名">{activeResult.title}</DetailRow>
                <DetailRow label="作者">{activeResult.authors || '-'}</DetailRow>
                <DetailRow label="期刊">{activeResult.source_journal} ({activeResult.publish_year})</DetailRow>
                <DetailRow label="DOI">{activeResult.doi || '-'}</DetailRow>
                <DetailRow label="关键词">{activeResult.keywords || '-'}</DetailRow>
                <div className="space-y-1 pt-1">
                  <h3 className="text-xs font-medium text-muted-foreground">摘要</h3>
                  <p className="text-sm line-clamp-4">{activeResult.abstract || '-'}</p>
                </div>
              </DetailSection>

              <Separator />

              <DetailSection label="LLM 分析结果">
                {activeResult.llm_analysis?.parsed_result ? (
                  <div className="space-y-2">
                    {Object.entries(activeResult.llm_analysis.parsed_result).map(([key, val]) => (
                      <DetailRow key={key} label={key}>
                        {['High', 'Medium', 'Low', 'Irrelevant'].includes(String(val)) ? (
                          <Badge variant={val === 'High' ? 'success' : val === 'Medium' ? 'info' : val === 'Low' ? 'secondary' : 'destructive'} className="text-xs">
                            {String(val)}
                          </Badge>
                        ) : (
                          String(val)
                        )}
                      </DetailRow>
                    ))}
                  </div>
                ) : activeResult.llm_analysis?.status === 'failed' ? (
                  <p className="text-sm text-destructive">分析失败: {activeResult.llm_analysis.error_message || '未知错误'}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">暂无分析结果</p>
                )}
              </DetailSection>

              <Separator />

              <DetailSection label="下载信息">
                <DetailRow label="下载状态">
                  <Badge variant={DOWNLOAD_BADGE[activeResult.download?.download_status || 'pending'].variant} className="text-xs">
                    {DOWNLOAD_BADGE[activeResult.download?.download_status || 'pending'].label}
                  </Badge>
                </DetailRow>
                <DetailRow label="文件路径">{activeResult.download?.pdf_path || '-'}</DetailRow>
                <DetailRow label="文件大小">
                  {activeResult.download?.file_size ? `${activeResult.download.file_size} KB` : '-'}
                </DetailRow>
              </DetailSection>
            </>
          )}
        </DetailPanel>
      </div>
    </div>
  )
}
