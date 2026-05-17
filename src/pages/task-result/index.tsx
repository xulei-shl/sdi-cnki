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
import { AxiosError } from 'axios'
import { toast } from 'sonner'
import { getTaskInstance } from '@/api/task-instances'
import { getTaskResults, markPass, markReject, batchUpdateResults, startDownload, startExport, getExportStatus, retryAnalysis, downloadExportFile } from '@/api/task-results'
import { SseClient } from '@/lib/sse'
import { Check, ChevronLeft, ChevronRight, X } from 'lucide-react'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import type { TaskInstance, TaskStatus } from '@/types'

const STEP_CONFIG: { label: string; match: TaskStatus[] }[] = [
  { label: '待执行', match: ['pending'] },
  { label: '检索排队中', match: ['search_queued'] },
  { label: '检索中', match: ['running', 'search_completed'] },
  { label: '分析中', match: ['analyzing'] },
  { label: '审核中', match: ['analyzing_completed'] },
  { label: '下载排队中', match: ['download_queued'] },
  { label: '下载中', match: ['downloading'] },
  { label: '已完成', match: ['completed'] },
]

const analysisTextColor = (status?: string, isTargetTopic?: boolean | null) => {
  if (status === 'failed') return 'text-red-500'
  if (status === 'analyzing') return 'text-blue-500'
  if (status === 'completed') {
    if (isTargetTopic === true) return 'text-green-600'
    if (isTargetTopic === false) return 'text-amber-500'
    return 'text-muted-foreground'
  }
  return 'text-muted-foreground'
}

const reviewTextColor = (isPassed: boolean | null) => {
  if (isPassed === true) return 'text-green-600'
  if (isPassed === false) return 'text-amber-500'
  return 'text-muted-foreground'
}

const downloadTextColor = (status?: string) => {
  if (status === 'completed') return 'text-green-600'
  if (status === 'failed') return 'text-red-500'
  if (status === 'downloading') return 'text-blue-500'
  if (status === 'skipped') return 'text-yellow-600'
  return 'text-muted-foreground'
}

const getAnalysisLabel = (status?: string, parsedResult?: any) => {
  if (status === 'failed') return '失败'
  if (status === 'analyzing') return '进行中'
  if (status === 'completed') {
    if (parsedResult?.is_target_topic === true) return '通过'
    if (parsedResult?.is_target_topic === false) return '拒绝'
    return '已完成'
  }
  return '未分析'
}

const DOWNLOAD_BADGE: Record<string, { label: string; variant: 'success' | 'destructive' | 'secondary' | 'info' | 'warning' }> = {
  pending: { label: '未下载', variant: 'secondary' },
  downloading: { label: '下载中', variant: 'info' },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'destructive' },
  skipped: { label: '跳过', variant: 'warning' },
}

const ANALYSIS_FILTER_OPTIONS = [
  { label: '分析状态', value: '' },
  { label: '已完成', value: 'completed' },
  { label: '未分析', value: 'pending' },
  { label: '失败', value: 'failed' },
]

const ANALYSIS_RESULT_OPTIONS = [
  { label: '分析结论', value: '' },
  { label: '通过', value: 'passed' },
  { label: '拒绝', value: 'rejected' },
]

const REVIEW_OPTIONS = [
  { label: '审核结论', value: '' },
  { label: '待审核', value: 'pending' },
  { label: '已通过', value: 'passed' },
  { label: '已拒绝', value: 'rejected' },
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
  const [activeIndex, setActiveIndex] = useState(0)
  const [showDetail, setShowDetail] = useState(false)

  // SSE progress state
  const [analyzeProgress, setAnalyzeProgress] = useState({ active: false, analyzed: 0, total: 0, failed: 0 })
  const [downloadProgress, setDownloadProgress] = useState({ active: false, success: 0, failed: 0, skipped: 0, total: 0 })

  // Filters
  const [reviewStatus, setReviewStatus] = useState('')
  const [analysisStatus, setAnalysisStatus] = useState('')
  const [analysisResult, setAnalysisResult] = useState('')
  const [keyword, setKeyword] = useState('')
  const [publishYear, setPublishYear] = useState('')
  const [minScore, setMinScore] = useState('')
  const [includeDuplicate, setIncludeDuplicate] = useState(false)

  const [exporting, setExporting] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [confirmAction, setConfirmAction] = useState<{ type: string; count?: number } | null>(null)
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
      const params: any = { page, page_size: 20 }
      if (reviewStatus) params.review_status = reviewStatus
      if (analysisStatus) params.analysis_status = analysisStatus
      if (analysisResult) params.analysis_result = analysisResult
      if (keyword) params.keyword = keyword
      if (publishYear) params.publish_year = parseInt(publishYear)
      if (minScore) params.min_score = parseInt(minScore)
      if (includeDuplicate) params.include_duplicate = true
      const res = await getTaskResults(instanceId, params)
      setResults(res.data.items || [])
      setTotal(res.data.total || 0)
    } finally {
      setLoading(false)
    }
  }, [instanceId, page, reviewStatus, analysisStatus, analysisResult, keyword, publishYear, minScore, includeDuplicate])

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
      } else if (['search_completed', 'analyzing_completed', 'download_queued', 'completed'].includes(data.status)) {
        setRetrying(false)
        setAnalyzeProgress({ active: false, analyzed: 0, total: 0, failed: 0 })
        fetchInstance(); fetchResults()
      }
    })
    sse.on('download.progress', (data: any) => {
      setDownloadProgress({ active: true, success: data.success ?? 0, failed: data.failed ?? 0, skipped: data.skipped ?? 0, total: data.total ?? 0 })
    })
    sse.on('task.completed', () => {
      setRetrying(false)
      setAnalyzeProgress({ active: false, analyzed: 0, total: 0, failed: 0 })
      fetchInstance(); fetchResults()
    })
    sse.on('task.failed', () => {
      setRetrying(false)
      setAnalyzeProgress({ active: false, analyzed: 0, total: 0, failed: 0 })
      fetchInstance(); fetchResults()
    })
    sse.on('export.completed', async (data: any) => {
      setExporting(false)
      if (data?.export_id) {
        try { await downloadExportFile(data.export_id) } catch { toast.error('下载文件失败') }
      }
      toast.success('导出完成')
    })
    sse.on('export.failed', (data: any) => {
      setExporting(false)
      toast.error(`导出失败: ${data?.error_message || ''}`)
    })
    sse.connect()

    return () => { sse.close() }
  }, [instanceId, instance?.status])

  const stepIndex = instance ? STEP_CONFIG.findIndex(s => s.match.includes(instance.status)) : -1



  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    const currentIds = results.map(r => r.id)
    const allSelectedOnPage = currentIds.every(id => selectedIds.has(id))
    if (allSelectedOnPage) {
      setSelectedIds(prev => {
        const next = new Set(prev)
        currentIds.forEach(id => next.delete(id))
        return next
      })
    } else {
      setSelectedIds(prev => {
        const next = new Set(prev)
        currentIds.forEach(id => next.add(id))
        return next
      })
    }
  }

  const handleSinglePass = async (row: any) => {
    try {
      await markPass(row.id)
      toast.success('已通过')
      fetchResults()
    } catch { toast.error('操作失败') }
  }

  const handleSingleReject = async (row: any) => {
    try {
      await markReject(row.id)
      toast.success('已拒绝')
      fetchResults()
    } catch { toast.error('操作失败') }
  }

  const goToPrev = () => {
    if (activeIndex <= 0) return
    const newIdx = activeIndex - 1
    setActiveIndex(newIdx)
    setActiveResult(results[newIdx])
  }

  const goToNext = () => {
    if (activeIndex >= results.length - 1) return
    const newIdx = activeIndex + 1
    setActiveIndex(newIdx)
    setActiveResult(results[newIdx])
  }

  const handleDetailPass = async () => {
    if (!activeResult) return
    try {
      await markPass(activeResult.id)
      toast.success('已通过')
      setResults(prev => prev.map(r => r.id === activeResult.id ? { ...r, is_passed: true } : r))
      setActiveResult((prev: any) => prev ? { ...prev, is_passed: true } : prev)
      goToNext()
    } catch { toast.error('操作失败') }
  }

  const handleDetailReject = async () => {
    if (!activeResult) return
    try {
      await markReject(activeResult.id)
      toast.success('已拒绝')
      setResults(prev => prev.map(r => r.id === activeResult.id ? { ...r, is_passed: false } : r))
      setActiveResult((prev: any) => prev ? { ...prev, is_passed: false } : prev)
      goToNext()
    } catch { toast.error('操作失败') }
  }

  const handleBatchPass = () => {
    if (!selectedIds.size) { toast.info('请先选择要操作的项'); return }
    setConfirmAction({ type: 'batch-pass', count: selectedIds.size })
  }

  const handleBatchReject = () => {
    if (!selectedIds.size) { toast.info('请先选择要操作的项'); return }
    setConfirmAction({ type: 'batch-reject', count: selectedIds.size })
  }

  const handleDownload = () => {
    setConfirmAction({ type: 'download' })
  }

  const handleRetryAnalysis = () => {
    if (retrying) return
    setConfirmAction({ type: 'retry-analysis' })
  }

  const handleExport = () => {
    if (exporting) return
    setConfirmAction({ type: 'export' })
  }

  const doConfirm = async () => {
    if (!confirmAction) return
    const { type } = confirmAction
    setConfirmAction(null)

    try {
      switch (type) {
        case 'batch-pass': {
          const ids = Array.from(selectedIds)
          if (!ids.length) break
          await batchUpdateResults(instanceId, { result_ids: ids, action: 'pass' })
          toast.success(`已通过 ${ids.length} 条`)
          setSelectedIds(new Set())
          fetchResults()
          break
        }
        case 'batch-reject': {
          const ids = Array.from(selectedIds)
          if (!ids.length) break
          await batchUpdateResults(instanceId, { result_ids: ids, action: 'reject' })
          toast.success(`已拒绝 ${ids.length} 条`)
          setSelectedIds(new Set())
          fetchResults()
          break
        }
        case 'download': {
          await startDownload(instanceId)
          toast.success('下载任务已加入队列')
          break
        }
        case 'retry-analysis': {
          setRetrying(true)
          setAnalyzeProgress({ active: true, analyzed: 0, total: 0, failed: 0 })
          try {
            await retryAnalysis(instanceId)
            toast.success('LLM 分析任务已加入队列')
            fetchInstance()
          } catch {
            toast.error('启动 LLM 分析失败')
            setAnalyzeProgress({ active: false, analyzed: 0, total: 0, failed: 0 })
            setRetrying(false)
          }
          break
        }
        case 'export': {
          setExporting(true)
          try {
            const res = await startExport(instanceId)
            const exportId = res.data.export_id
            toast.success('导出任务已加入队列')
            const poll = async () => {
              try {
                const sr = await getExportStatus(exportId)
                if (sr.data.status === 'completed') {
                  setExporting(false)
                  try { await downloadExportFile(exportId) } catch { toast.error('下载文件失败') }
                  toast.success('导出完成')
                } else if (sr.data.status === 'failed') {
                  setExporting(false)
                  toast.error(`导出失败: ${sr.data.error_message || ''}`)
                } else {
                  setTimeout(poll, 3000)
                }
              } catch {
                setExporting(false)
                toast.error('查询导出状态失败')
              }
            }
            setTimeout(poll, 3000)
          } catch (err) {
            setExporting(false)
            const msg = err instanceof AxiosError ? err.response?.data?.message || err.message : '启动导出失败'
            toast.error(`导出失败: ${msg}`)
          }
          break
        }
      }
    } catch {
      toast.error('操作失败')
    }
  }

  const viewDetail = (row: any) => {
    const idx = results.findIndex(r => r.id === row.id)
    setActiveIndex(idx >= 0 ? idx : 0)
    setActiveResult(row)
    setShowDetail(true)
  }

  const relevanceColor = (score: number | null) => {
    if (score === null) return 'text-muted-foreground'
    if (score >= 7) return 'text-green-600 font-medium'
    if (score >= 4) return 'text-blue-600'
    return 'text-gray-400'
  }

  const formatDate = (d: string | null | undefined) => d ? d.slice(0, 16).replace('T', ' ') : '-'

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header Area */}
      <div className="px-8 pt-5 pb-5 border-b shrink-0 flex flex-col gap-5 bg-muted/10">
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
        <div className="flex items-center justify-between max-w-4xl mx-auto w-full">
          {STEP_CONFIG.map((step, i) => {
            const isActive = i === stepIndex
            const isDone = i < stepIndex
            const isError = instance?.status === 'failed'
            return (
              <div key={step.label} className="flex flex-col items-center gap-1.5">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-medium border
                  ${isError && i === STEP_CONFIG.length - 1 ? 'border-destructive bg-destructive text-destructive-foreground' : ''}
                  ${isActive && !isError ? 'border-primary bg-primary text-primary-foreground shadow-sm' : ''}
                  ${isDone && !isError ? 'border-green-500 bg-green-500 text-white' : ''}
                  ${!isActive && !isDone && !(isError && i === STEP_CONFIG.length - 1) ? 'border-muted-foreground/30 text-muted-foreground' : ''}`}>
                  {isDone ? <Check className="w-3.5 h-3.5" /> : i + 1}
                </div>
                <span className={`text-[11px] ${isActive ? 'font-medium text-primary' : isDone ? 'text-green-600' : 'text-muted-foreground'}`}>
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
              <Select value={analysisStatus} onChange={(e) => { setAnalysisStatus(e.target.value); setPage(1) }} className="w-[120px]">
                {ANALYSIS_FILTER_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <Select value={analysisResult} onChange={(e) => { setAnalysisResult(e.target.value); setPage(1) }} className="w-[120px]">
                {ANALYSIS_RESULT_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <Select value={minScore} onChange={(e) => { setMinScore(e.target.value); setPage(1) }} className="w-[100px]">
                <option value="">分析评分</option>
                <option value="4">≥4</option>
                <option value="6">≥6</option>
                <option value="8">≥8</option>
                <option value="9">≥9</option>
              </Select>
              <Select value={reviewStatus} onChange={(e) => { setReviewStatus(e.target.value); setPage(1) }} className="w-[120px]">
                {REVIEW_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <Input placeholder="题名关键词" value={keyword} onChange={(e) => { setKeyword(e.target.value); setPage(1) }} className="w-[150px]" />
              <Input placeholder="年份" value={publishYear} onChange={(e) => { setPublishYear(e.target.value); setPage(1) }} className="w-[80px]" />
              <label className="flex items-center gap-1 text-sm bg-accent/50 px-2 py-1.5 rounded-md cursor-pointer hover:bg-accent/80 transition-colors">
                <Checkbox checked={includeDuplicate} onChange={(e) => { setIncludeDuplicate(e.target.checked); setPage(1) }} />
                <span className="ml-1">含重复</span>
              </label>
            </div>

            {/* Batch Actions */}
            <div className="flex items-center gap-3">
              {selectedIds.size > 0 && (
                <>
                  <span className="text-sm font-medium text-primary">已选中 {selectedIds.size} 项</span>
                  <button
                    onClick={() => setSelectedIds(new Set())}
                    className="p-1 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors text-muted-foreground"
                    title="清空选择"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </>
              )}
              <Button size="sm" variant="outline" disabled={selectedIds.size === 0} onClick={handleBatchPass}>批量通过</Button>
              <Button size="sm" variant="outline" disabled={selectedIds.size === 0} onClick={handleBatchReject}>批量拒绝</Button>
              {['analyzing_completed', 'download_queued', 'downloading', 'completed', 'failed'].includes(instance?.status || '') && (
                <Button size="sm" variant="outline" onClick={handleExport} disabled={exporting}>
                  {exporting ? '导出中...' : '结果导出'}
                </Button>
              )}
              {['analyzing_completed', 'downloading', 'completed', 'failed'].includes(instance?.status || '') && (
                <Button size="sm" variant="outline" onClick={handleRetryAnalysis} disabled={retrying}>
                  {retrying ? '分析中...' : 'LLM 分析'}
                </Button>
              )}
              {['analyzing_completed', 'downloading'].includes(instance?.status || '') && (
                <Button size="sm" variant="outline" onClick={handleDownload}>PDF 下载</Button>
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
                      checked={results.length > 0 && results.every(r => selectedIds.has(r.id))}
                      ref={el => { if (el) el.indeterminate = results.some(r => selectedIds.has(r.id)) && !results.every(r => selectedIds.has(r.id)) }}
                      onChange={toggleAll}
                    />
                  </TableHead>
                  <TableHead className="min-w-[350px] flex-1">题名</TableHead>
                  <TableHead className="w-[180px]">期刊</TableHead>
                  <TableHead className="w-[70px] text-center">出版年</TableHead>
                  <TableHead className="w-[120px] text-center">相关性</TableHead>
                  <TableHead className="w-[180px]">状态 <span className="text-xs font-normal text-muted-foreground">(分析/审核/下载)</span></TableHead>
                  <TableHead className="w-[160px] text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-12">
                      <div className="flex items-center justify-center gap-2 text-muted-foreground animate-pulse">
                        <div className="w-4 h-4 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                        数据加载中...
                      </div>
                    </TableCell>
                  </TableRow>
                ) : results.length === 0 ? (
                  <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">暂无数据</TableCell></TableRow>
                ) : results.map((row) => {
                  const score = row.llm_analysis?.parsed_result?.relevance_score ?? null
                  return (
                    <TableRow key={row.id} className="cursor-pointer" onClick={() => viewDetail(row)}>
                      <TableCell onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                        <Checkbox checked={selectedIds.has(row.id)} onChange={() => toggleSelect(row.id)} />
                      </TableCell>
                      <TableCell>
                        <div className="truncate max-w-none" title={row.title}>
                          {row.title}
                          {row.is_duplicate && <Badge variant="warning" className="ml-1 text-xs">重复</Badge>}
                        </div>
                      </TableCell>
                      <TableCell className="truncate max-w-[180px]">{row.source_journal || '-'}</TableCell>
                      <TableCell className="text-center">{row.publish_year ?? '-'}</TableCell>
                      <TableCell className="text-center">
                        <span className={`text-xs ${relevanceColor(score)}`}>{score ?? '-'}</span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1 text-xs">
                          <span className={analysisTextColor(row.llm_analysis?.status, row.llm_analysis?.parsed_result?.is_target_topic)}>
                            {getAnalysisLabel(row.llm_analysis?.status, row.llm_analysis?.parsed_result)}
                          </span>
                          <span className="text-muted-foreground">/</span>
                          <span className={reviewTextColor(row.is_passed)}>
                            {row.is_passed === true ? '通过' : row.is_passed === false ? '拒绝' : '未审'}
                          </span>
                          <span className="text-muted-foreground">/</span>
                          <span className={downloadTextColor(row.download?.download_status)}>
                            {DOWNLOAD_BADGE[row.download?.download_status || 'pending'].label}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell onClick={(e: React.MouseEvent) => e.stopPropagation()}>
                        <div className="flex justify-end gap-3">
                          <Button variant="link" className="h-auto p-0 font-normal" onClick={() => handleSinglePass(row)}>通过</Button>
                          <Button variant="link" className="h-auto p-0 font-normal text-destructive hover:text-destructive/80" onClick={() => handleSingleReject(row)}>拒绝</Button>
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
          headerActions={
            <div className="flex items-center gap-1.5">
              <button
                onClick={handleDetailPass}
                disabled={!activeResult || activeResult.is_passed === true}
                className="text-xs font-medium text-green-600 hover:text-green-700 transition-colors px-2 py-1 rounded-md hover:bg-green-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                通过
              </button>
              <button
                onClick={handleDetailReject}
                disabled={!activeResult || activeResult.is_passed === false}
                className="text-xs font-medium text-destructive hover:text-destructive/80 transition-colors px-2 py-1 rounded-md hover:bg-destructive/5 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                拒绝
              </button>
              <div className="w-px h-4 bg-border mx-0.5" />
              <button
                onClick={goToPrev}
                disabled={activeIndex <= 0}
                className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                title="上一条"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={goToNext}
                disabled={activeIndex >= results.length - 1}
                className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                title="下一条"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
              {results.length > 0 && (
                <span className="text-xs text-muted-foreground tabular-nums whitespace-nowrap min-w-[3.5rem] text-center">
                  {activeIndex + 1}/{results.length}
                </span>
              )}
            </div>
          }
        >
          {activeResult && (
            <>
              <DetailSection label="文献信息">
                <DetailRow label="题名" layout="vertical">{activeResult.title}</DetailRow>
                <DetailRow label="摘要" layout="vertical">
                  {activeResult.abstract || '-'}
                </DetailRow>
                <DetailRow label="关键词" layout="vertical">{activeResult.keywords || '-'}</DetailRow>
                <DetailRow label="作者" valueAlign="left">{activeResult.authors || '-'}</DetailRow>
                <DetailRow label="期刊" valueAlign="left">{activeResult.source_journal || '-'}</DetailRow>
                <DetailRow label="出版年" valueAlign="left">{activeResult.publish_year ?? '-'}</DetailRow>
                <DetailRow label="作者单位" layout="vertical">{activeResult.organ || '-'}</DetailRow>
                <DetailRow label="基金" layout="vertical">{activeResult.fund || '-'}</DetailRow>
                <DetailRow label="原文链接" valueAlign="left">
                  {activeResult.original_url ? (
                    <a href={activeResult.original_url} target="_blank" rel="noopener noreferrer" className="text-primary underline hover:text-primary/80 transition-colors truncate block max-w-[420px]" title={activeResult.original_url}>
                      {activeResult.original_url}
                    </a>
                  ) : '-'}
                </DetailRow>
              </DetailSection>

              <Separator />

              <DetailSection label="LLM 分析结果">
                {activeResult.llm_analysis?.parsed_result ? (
                  <div className="space-y-0.5">
                    {Object.entries(activeResult.llm_analysis.parsed_result).map(([key, val]) => {
                      const isLongText = typeof val === 'string' && val.length > 30
                      return (
                        <DetailRow key={key} label={key} layout={isLongText ? 'vertical' : 'horizontal'} valueAlign="left">
                          {['High', 'Medium', 'Low', 'Irrelevant'].includes(String(val)) ? (
                            <Badge variant={val === 'High' ? 'success' : val === 'Medium' ? 'info' : val === 'Low' ? 'secondary' : 'destructive'} className="text-xs">
                              {String(val)}
                            </Badge>
                          ) : (
                            String(val)
                          )}
                        </DetailRow>
                      )
                    })}
                  </div>
                ) : activeResult.llm_analysis?.status === 'failed' ? (
                  <p className="text-sm text-destructive px-3 py-2">分析失败: {activeResult.llm_analysis.error_message || '未知错误'}</p>
                ) : (
                  <p className="text-sm text-muted-foreground px-3 py-2">暂无分析结果</p>
                )}
              </DetailSection>

              <Separator />

              <DetailSection label="下载信息">
                <DetailRow label="下载状态" valueAlign="left">
                  <Badge variant={DOWNLOAD_BADGE[activeResult.download?.download_status || 'pending'].variant} className="text-xs">
                    {DOWNLOAD_BADGE[activeResult.download?.download_status || 'pending'].label}
                  </Badge>
                </DetailRow>
                <DetailRow label="文件路径" layout="vertical">{activeResult.download?.pdf_path || '-'}</DetailRow>
                <DetailRow label="文件大小" valueAlign="left">
                  {activeResult.download?.file_size ? `${activeResult.download.file_size} KB` : '-'}
                </DetailRow>
              </DetailSection>
            </>
          )}
        </DetailPanel>
      </div>

      <ConfirmDialog
        open={!!confirmAction}
        onOpenChange={(o) => { if (!o) setConfirmAction(null) }}
        title={
          confirmAction?.type === 'batch-pass' ? '批量通过' :
            confirmAction?.type === 'batch-reject' ? '批量拒绝' :
              confirmAction?.type === 'export' ? '导出确认' :
                confirmAction?.type === 'retry-analysis' ? 'LLM 分析确认' :
                  '下载确认'
        }
        description={
          confirmAction?.type === 'batch-pass' ? `确认批量通过选中的 ${confirmAction.count} 项结果？` :
            confirmAction?.type === 'batch-reject' ? `确认批量拒绝选中的 ${confirmAction.count} 项结果？` :
              confirmAction?.type === 'export' ? '确认导出当前任务的所有搜索结果？此操作将导出数据为 Excel 文件。' :
                confirmAction?.type === 'retry-analysis' ? '确认重新运行 LLM 分析？此操作将重新分析所有搜索结果。' :
                  '确认下载所有结果的 PDF 文件？'
        }
        variant={confirmAction?.type === 'batch-reject' ? 'destructive' : 'default'}
        confirmText="确认"
        onConfirm={doConfirm}
      />
    </div>
  )
}
