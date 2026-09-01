import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AxiosError } from 'axios'
import { toast } from 'sonner'
import { getTaskInstance, importExcelResults } from '@/api/task-instances'
import { getTaskResults, markPass, markReject, batchUpdateResults, startDownload, startExport, getExportStatus, retryAnalysis, downloadExportFile, retryDownload, getDownloadProgress, invalidateTaskResultsCache } from '@/api/task-results'
import { SseClient } from '@/lib/sse'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { STEP_CONFIG } from './constants'
import { TaskHeader } from './task-header'
import { ExcelUpload } from './excel-upload'
import { FilterToolbar } from './filter-toolbar'
import { ResultTable } from './result-table'
import { ResultDetailPanel } from './result-detail-panel'
import type { TaskInstance } from '@/types'

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
  const [downloadingIds, setDownloadingIds] = useState<Set<number>>(new Set())
  const [processingIds, setProcessingIds] = useState<Set<number>>(new Set())

  // SSE progress state
  const [analyzeProgress, setAnalyzeProgress] = useState({ active: false, analyzed: 0, total: 0, failed: 0 })
  const [downloadProgress, setDownloadProgress] = useState({ active: false, success: 0, failed: 0, total: 0 })

  // Filters
  const [reviewStatus, setReviewStatus] = useState('')
  const [analysisStatus, setAnalysisStatus] = useState('')
  const [analysisResult, setAnalysisResult] = useState('')
  const [keyword, setKeyword] = useState('')
  const [publishYear, setPublishYear] = useState('')
  const [minScore, setMinScore] = useState('')
  const [includeDuplicate, setIncludeDuplicate] = useState(false)
  const [downloadStatus, setDownloadStatus] = useState('')
  const [moreOpen, setMoreOpen] = useState(false)

  const [exporting, setExporting] = useState(false)
  const [exportDownloadProgress, setExportDownloadProgress] = useState<{ loaded: number; total: number } | null>(null)
  const [includePdfs, setIncludePdfs] = useState(true)
  const [retrying, setRetrying] = useState(false)
  const [confirmAction, setConfirmAction] = useState<{ type: string; count?: number } | null>(null)
  const [importing, setImporting] = useState(false)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const sseRef = useRef<SseClient | null>(null)
  const getAuthToken = () => localStorage.getItem('access_token') || ''

  const resetPage = () => setPage(1)

  const fetchInstance = useCallback(async () => {
    // Not cached — getTaskInstance is a detail endpoint called on row clicks
    // and SSE events, so caching would add stale-data risk with little benefit.
    try {
      const res = await getTaskInstance(instanceId)
      setInstance(res.data)
    } catch { /* ignore */ }
  }, [instanceId])

  const fetchResults = useCallback(async (opts?: { fresh?: boolean }) => {
    if (opts?.fresh) invalidateTaskResultsCache(instanceId)
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
      if (downloadStatus) params.download_status = downloadStatus
      const res = await getTaskResults(instanceId, params)
      setResults(res.data.items || [])
      setTotal(res.data.total || 0)
    } finally {
      setLoading(false)
    }
  }, [instanceId, page, reviewStatus, analysisStatus, analysisResult, keyword, publishYear, minScore, includeDuplicate, downloadStatus])

  useEffect(() => { fetchInstance(); fetchResults() }, [fetchInstance, fetchResults])

  useEffect(() => {
    const token = getAuthToken()
    if (!token || !instance) return
    if (['completed', 'failed', 'cancelled'].includes(instance.status)) return

    const sse = new SseClient(instanceId, getAuthToken)
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
      setDownloadProgress({ active: true, success: data.success ?? 0, failed: data.failed ?? 0, total: data.total ?? 0 })
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
        setExportDownloadProgress({ loaded: 0, total: 0 })
        try {
          await downloadExportFile(data.export_id, (loaded, total) => {
            setExportDownloadProgress({ loaded, total })
          })
        } catch { toast.error('下载文件失败') }
        setExportDownloadProgress(null)
      }
      toast.success('导出完成')
    })
    sse.on('export.failed', (data: any) => {
      setExporting(false)
      toast.error(`导出失败: ${data?.error_message || ''}`)
    })
    sse.connect()

    return () => { sse.close() }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instanceId, instance?.status])

  const stepIndex = instance ? STEP_CONFIG.findIndex(s => s.match.includes(instance.status)) : -1

  // ── Selection ──
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

  // ── Single row actions ──
  const handleSinglePass = async (row: any) => {
    if (processingIds.has(row.id)) return
    setProcessingIds(prev => new Set(prev).add(row.id))
    try { await markPass(row.id); toast.success('已通过'); setResults(prev => prev.map(r => r.id === row.id ? { ...r, is_passed: true } : r)) }
    catch { toast.error('操作失败') }
    finally { setProcessingIds(prev => { const next = new Set(prev); next.delete(row.id); return next }) }
  }

  const handleSingleReject = async (row: any) => {
    if (processingIds.has(row.id)) return
    setProcessingIds(prev => new Set(prev).add(row.id))
    try { await markReject(row.id); toast.success('已拒绝'); setResults(prev => prev.map(r => r.id === row.id ? { ...r, is_passed: false } : r)) }
    catch { toast.error('操作失败') }
    finally { setProcessingIds(prev => { const next = new Set(prev); next.delete(row.id); return next }) }
  }

  const handleSingleDownload = async (row: any) => {
    if (downloadingIds.has(row.id)) return
    setDownloadingIds(prev => new Set(prev).add(row.id))
    try {
      const res = await retryDownload(instanceId, row.id)
      const downloadStatus = res.data.download_status
      if (downloadStatus === 'completed') toast.success('下载成功')
      else if (downloadStatus === 'failed') toast.error('下载失败')
      setResults(prev => prev.map(r => r.id === row.id ? { ...r, download: { ...r.download, download_status: downloadStatus, pdf_path: res.data.pdf_path ?? r.download?.pdf_path, file_size: res.data.file_size ?? r.download?.file_size } } : r))
    } catch { toast.error('下载请求失败') }
    finally {
      setDownloadingIds(prev => {
        const next = new Set(prev)
        next.delete(row.id)
        return next
      })
    }
  }

  // ── Detail navigation ──
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

  const viewDetail = (row: any) => {
    const idx = results.findIndex(r => r.id === row.id)
    setActiveIndex(idx >= 0 ? idx : 0)
    setActiveResult(row)
    setShowDetail(true)
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

  // ── Batch & command actions ──
  const handleBatchPass = () => {
    if (!selectedIds.size) { toast.info('请先选择要操作的项'); return }
    setConfirmAction({ type: 'batch-pass', count: selectedIds.size })
  }

  const handleBatchReject = () => {
    if (!selectedIds.size) { toast.info('请先选择要操作的项'); return }
    setConfirmAction({ type: 'batch-reject', count: selectedIds.size })
  }

  const handleDownload = () => {
    const unreviewedCount = results.filter(r =>
      r.llm_analysis?.parsed_result?.is_target_topic === true &&
      r.is_passed === null
    ).length
    if (unreviewedCount > 0) {
      setConfirmAction({ type: 'download-unreviewed', count: unreviewedCount })
    } else {
      setConfirmAction({ type: 'download' })
    }
  }
  const handleRetryAnalysis = () => { if (!retrying) setConfirmAction({ type: 'retry-analysis' }) }
  const handleExport = () => { if (!exporting) setConfirmAction({ type: 'export' }) }

  const handleImportExcel = async () => {
    if (!uploadFile || importing) return
    setImporting(true)
    setImportError(null)
    try {
      const res = await importExcelResults(instanceId, uploadFile)
      const d = res.data
      toast.success(`导入成功：共 ${d.total} 条，有效 ${d.valid} 条，重复 ${d.duplicate} 条`)
      setUploadFile(null)
      fetchInstance()
      fetchResults({ fresh: true })
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || '导入失败'
      setImportError(msg)
      toast.error(msg)
    } finally { setImporting(false) }
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
          setResults(prev => prev.map(r => ids.includes(r.id) ? { ...r, is_passed: true } : r))
          break
        }
        case 'batch-reject': {
          const ids = Array.from(selectedIds)
          if (!ids.length) break
          await batchUpdateResults(instanceId, { result_ids: ids, action: 'reject' })
          toast.success(`已拒绝 ${ids.length} 条`)
          setSelectedIds(new Set())
          setResults(prev => prev.map(r => ids.includes(r.id) ? { ...r, is_passed: false } : r))
          break
        }
        case 'download': {
          await startDownload(instanceId)
          toast.success('下载任务已加入队列')
          break
        }
        case 'download-unreviewed': {
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
            const res = await startExport(instanceId, includePdfs)
            const exportId = res.data.export_id
            toast.success('导出任务已加入队列')
            const poll = async () => {
              try {
                const sr = await getExportStatus(exportId)
                if (sr.data.status === 'completed') {
                  setExporting(false)
                  setExportDownloadProgress({ loaded: 0, total: 0 })
                  try {
                    await downloadExportFile(exportId, (loaded, total) => {
                      setExportDownloadProgress({ loaded, total })
                    })
                  } catch { toast.error('下载文件失败') }
                  setExportDownloadProgress(null)
                  toast.success('导出完成')
                } else if (sr.data.status === 'failed') {
                  setExporting(false)
                  toast.error(`导出失败: ${sr.data.error_message || ''}`)
                } else { setTimeout(poll, 3000) }
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
    } catch { toast.error('操作失败') }
  }

  // ── Derived flags ──
  const instanceStatus = instance?.status || ''
  const isEditableStatus = ['analyzing_completed', 'downloading'].includes(instanceStatus)
  const isMoreMenuVisible = ['analyzing_completed', 'download_queued', 'downloading', 'completed', 'failed'].includes(instanceStatus)
  const canRetryAnalysis = ['analyzing_completed', 'downloading', 'completed', 'failed'].includes(instanceStatus)

  // ── Download progress recovery ──
  // 挂载/状态变化时从 DB 恢复累计进度（SSE 事件到达后继续覆盖更新），
  // 解决“刷新页面后要等第一条 download.progress 事件才出现进度条”的问题。
  useEffect(() => {
    if (!['download_queued', 'downloading'].includes(instanceStatus)) return
    let cancelled = false
    getDownloadProgress(instanceId)
      .then((res) => {
        if (cancelled) return
        const d = res.data || {}
        setDownloadProgress({ active: true, success: d.success ?? 0, failed: d.failed ?? 0, total: d.total ?? 0 })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [instanceStatus, instanceId])

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <TaskHeader
        instance={instance}
        stepIndex={stepIndex}
        analyzeProgress={analyzeProgress}
        downloadProgress={downloadProgress}
        onBack={() => navigate('/task-instances')}
      />

      <div className="flex-1 flex overflow-hidden relative">
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {instance?.status === 'pending' && !instance?.auto_run ? (
            <ExcelUpload
              uploadFile={uploadFile}
              importing={importing}
              importError={importError}
              onFileChange={(f) => { setUploadFile(f); setImportError(null) }}
              onImport={handleImportExcel}
            />
          ) : (
            <>
              <FilterToolbar
                analysisStatus={analysisStatus}
                analysisResult={analysisResult}
                minScore={minScore}
                reviewStatus={reviewStatus}
                downloadStatus={downloadStatus}
                keyword={keyword}
                publishYear={publishYear}
                includeDuplicate={includeDuplicate}
                includePdfs={includePdfs}
                exportDownloadProgress={exportDownloadProgress}
                selectedCount={selectedIds.size}
                moreOpen={moreOpen}
                exporting={exporting}
                retrying={retrying}
                canDownload={isEditableStatus}
                canShowMore={isMoreMenuVisible}
                canRetryAnalysis={canRetryAnalysis}
                onAnalysisStatusChange={(v) => { setAnalysisStatus(v); resetPage() }}
                onAnalysisResultChange={(v) => { setAnalysisResult(v); resetPage() }}
                onMinScoreChange={(v) => { setMinScore(v); resetPage() }}
                onReviewStatusChange={(v) => { setReviewStatus(v); resetPage() }}
                onDownloadStatusChange={(v) => { setDownloadStatus(v); resetPage() }}
                onKeywordChange={(v) => { setKeyword(v); resetPage() }}
                onPublishYearChange={(v) => { setPublishYear(v); resetPage() }}
                onIncludeDuplicateChange={(v) => { setIncludeDuplicate(v); resetPage() }}
                onIncludePdfsChange={setIncludePdfs}
                onBatchPass={handleBatchPass}
                onBatchReject={handleBatchReject}
                onDownload={handleDownload}
                onExport={handleExport}
                onRetryAnalysis={handleRetryAnalysis}
                onMoreToggle={() => setMoreOpen(v => !v)}
                onMoreClose={() => setMoreOpen(false)}
              />
              <ResultTable
                results={results}
                loading={loading}
                total={total}
                page={page}
                selectedIds={selectedIds}
                downloadingIds={downloadingIds}
                processingIds={processingIds}
                onToggleSelect={toggleSelect}
                onToggleAll={toggleAll}
                onClearSelection={() => setSelectedIds(new Set())}
                onViewDetail={viewDetail}
                onSinglePass={handleSinglePass}
                onSingleReject={handleSingleReject}
                onSingleDownload={handleSingleDownload}
                onPageChange={setPage}
              />
            </>
          )}
        </div>

        <ResultDetailPanel
          showDetail={showDetail}
          activeResult={activeResult}
          activeIndex={activeIndex}
          totalResults={results.length}
          onClose={() => { setShowDetail(false); setActiveResult(null) }}
          onPass={handleDetailPass}
          onReject={handleDetailReject}
          onPrev={goToPrev}
          onNext={goToNext}
        />
      </div>

      <ConfirmDialog
        open={!!confirmAction}
        onOpenChange={(o) => { if (!o) setConfirmAction(null) }}
        title={
          confirmAction?.type === 'batch-pass' ? '批量通过' :
            confirmAction?.type === 'batch-reject' ? '批量拒绝' :
              confirmAction?.type === 'export' ? '导出确认' :
                confirmAction?.type === 'retry-analysis' ? 'LLM 分析确认' :
                  confirmAction?.type === 'download-unreviewed' ? '存在未审核记录' :
                    '下载确认'
        }
        description={
          confirmAction?.type === 'batch-pass' ? `确认批量通过选中的 ${confirmAction.count} 项结果？` :
            confirmAction?.type === 'batch-reject' ? `确认批量拒绝选中的 ${confirmAction.count} 项结果？` :
              confirmAction?.type === 'export' ? '确认导出当前任务的所有搜索结果？此操作将导出数据为 Excel 文件。' :
                confirmAction?.type === 'retry-analysis' ? '确认重新运行 LLM 分析？此操作将重新分析所有搜索结果。' :
                  confirmAction?.type === 'download-unreviewed' ? `存在 ${confirmAction.count} 条LLM分析通过但未人工审核的记录，请先完成人工审核后再执行批量下载。` :
                    '确认下载所有结果的 PDF 文件？'
        }
        variant={confirmAction?.type === 'batch-reject' || confirmAction?.type === 'download-unreviewed' ? 'destructive' : 'default'}
        confirmText="确认"
        onConfirm={doConfirm}
      />
    </div>
  )
}
