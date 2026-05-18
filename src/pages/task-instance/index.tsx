import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Pagination } from '@/components/ui/pagination'
import { DetailPanel, DetailSection, DetailRow } from '@/components/layout/detail-panel'
import { AxiosError } from 'axios'
import { toast } from 'sonner'
import { getTaskInstances, getTaskInstance, deleteTaskInstance, runTaskInstance, type TaskInstanceQuery } from '@/api/task-instances'
import { startExport, getExportStatus, downloadExportFile } from '@/api/task-results'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EditDialog } from './edit-dialog'
import type { TaskInstance, TaskStatus } from '@/types'

const DATE_RANGE_LABELS: Record<string, string> = {
  week: '最近一周', month: '最近一月', 'half-year': '最近半年',
  year: '最近一年', ytd: '今年迄今', 'last-year': '上一年度',
}

const STATUS_MAP: Record<TaskStatus, { label: string; variant: 'info' | 'warning' | 'success' | 'destructive' | 'secondary' | 'default' }> = {
  pending: { label: '待执行', variant: 'secondary' },
  search_queued: { label: '检索排队中', variant: 'warning' },
  running: { label: '检索中', variant: 'info' },
  search_completed: { label: '已检索', variant: 'info' },
  analyzing: { label: '分析中', variant: 'info' },
  analyzing_completed: { label: '审核中', variant: 'info' },
  download_queued: { label: '下载排队中', variant: 'warning' },
  downloading: { label: '下载中', variant: 'info' },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'destructive' },
  cancelled: { label: '已取消', variant: 'secondary' },
}

const STATUS_OPTIONS = [
  { label: '全部', value: '' },
  { label: '待执行', value: 'pending' },
  { label: '检索排队中', value: 'search_queued' },
  { label: '检索中', value: 'running' },
  { label: '已检索', value: 'search_completed' },
  { label: '分析中', value: 'analyzing' },
  { label: '审核中', value: 'analyzing_completed' },
  { label: '下载排队中', value: 'download_queued' },
  { label: '下载中', value: 'downloading' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
]

export default function TaskInstancePage() {
  const navigate = useNavigate()
  const [instances, setInstances] = useState<TaskInstance[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [templateName, setTemplateName] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedInstance, setSelectedInstance] = useState<TaskInstance | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [runningId, setRunningId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<TaskInstance | null>(null)
  const [confirmRun, setConfirmRun] = useState<TaskInstance | null>(null)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [editInstance, setEditInstance] = useState<TaskInstance | null>(null)
  const [exportingId, setExportingId] = useState<number | null>(null)

  const handleExport = async (e: React.MouseEvent, inst: TaskInstance) => {
    e.stopPropagation()
    if (exportingId === inst.id) return
    setExportingId(inst.id)
    try {
      const res = await startExport(inst.id)
      const exportId = res.data.export_id
      toast.success('导出任务已加入队列')

      const poll = async () => {
        try {
          const sr = await getExportStatus(exportId)
          if (sr.data.status === 'completed') {
            setExportingId(null)
            try { await downloadExportFile(exportId) } catch { toast.error('下载文件失败') }
            toast.success('导出完成')
          } else if (sr.data.status === 'failed') {
            setExportingId(null)
            toast.error(`导出失败: ${sr.data.error_message || '未知错误'}`)
          } else {
            setTimeout(poll, 3000)
          }
        } catch {
          setExportingId(null)
          toast.error('查询导出状态失败')
        }
      }
      setTimeout(poll, 3000)
    } catch (err) {
      setExportingId(null)
      const msg = err instanceof AxiosError ? err.response?.data?.message || err.message : '启动导出失败'
      toast.error(`导出失败: ${msg}`)
    }
  }

  const fetchInstances = useCallback(async () => {
    setLoading(true)
    try {
      const params: TaskInstanceQuery = { page, page_size: 20 }
      if (keyword) params.keyword = keyword
      if (templateName) params.template_keyword = templateName
      if (statusFilter) params.status_filter = statusFilter
      const res = await getTaskInstances(params)
      setInstances(res.data.items)
      setTotal(res.data.total)
    } finally {
      setLoading(false)
    }
  }, [page, keyword, templateName, statusFilter])

  useEffect(() => { fetchInstances() }, [fetchInstances])

  const handleRowClick = async (instanceId: number) => {
    setDetailLoading(true)
    try {
      const res = await getTaskInstance(instanceId)
      setSelectedInstance(res.data)
    } finally {
      setDetailLoading(false)
    }
  }

  const handleRunInstance = async (e: React.MouseEvent, inst: TaskInstance) => {
    e.stopPropagation()
    setConfirmRun(inst)
  }

  const doRunInstance = async () => {
    if (!confirmRun) return
    setRunningId(confirmRun.id)
    setConfirmRun(null)
    try {
      await runTaskInstance(confirmRun.id)
      toast.success('任务已加入执行队列')
      fetchInstances()
      if (selectedInstance?.id === confirmRun.id) handleRowClick(confirmRun.id)
    } catch {
      toast.error('执行失败')
    } finally {
      setRunningId(null)
    }
  }

  const handleEditInstance = async (e: React.MouseEvent, inst: TaskInstance) => {
    e.stopPropagation()
    try {
      const res = await getTaskInstance(inst.id)
      setEditInstance(res.data)
      setEditDialogOpen(true)
    } catch {
      toast.error('获取实例详情失败')
    }
  }

  const handleDeleteInstance = (e: React.MouseEvent, inst: TaskInstance) => {
    e.stopPropagation()
    setConfirmDelete(inst)
  }

  const doDeleteInstance = async () => {
    if (!confirmDelete) return
    setDeletingId(confirmDelete.id)
    setConfirmDelete(null)
    try {
      await deleteTaskInstance(confirmDelete.id)
      toast.success('实例已删除')
      fetchInstances()
      if (selectedInstance?.id === confirmDelete.id) setSelectedInstance(null)
    } catch {
      toast.error('删除失败')
    } finally {
      setDeletingId(null)
    }
  }

  const formatDate = (d: string | null | undefined) => {
    if (!d) return '-'
    return d.slice(0, 16).replace('T', ' ')
  }

  return (
    <div className="h-full flex overflow-hidden relative">
      {/* Middle: List Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Search Bar */}
        <div className="px-8 py-6 border-b flex items-center gap-4 flex-wrap">
          <Input
            placeholder="实例编号搜索..."
            value={keyword}
            onChange={(e) => { setKeyword(e.target.value); setPage(1) }}
            className="w-[240px]"
          />
          <Input
            placeholder="关联模板名称..."
            value={templateName}
            onChange={(e) => { setTemplateName(e.target.value); setPage(1) }}
            className="w-[240px]"
          />
          <Select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }} className="w-[160px]">
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto px-8 py-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>实例编号</TableHead>
                <TableHead>关联模板</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>创建者</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead className="text-center">数据统计</TableHead>
                <TableHead className="text-right">操作</TableHead>
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
              ) : instances.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">暂无任务实例</TableCell>
                </TableRow>
              ) : instances.map((inst) => {
                const statusInfo = STATUS_MAP[inst.status]
                return (
                  <TableRow
                    key={inst.id}
                    className="cursor-pointer"
                    onClick={() => handleRowClick(inst.id)}
                    data-state={selectedInstance?.id === inst.id ? 'selected' : undefined}
                  >
                    <TableCell className="font-mono text-sm">{inst.instance_no}</TableCell>
                    <TableCell className="max-w-[200px] truncate">{inst.meta_task_name}</TableCell>
                    <TableCell>
                      <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                    </TableCell>
                    <TableCell>{inst.creator_name || inst.creator_id}</TableCell>
                    <TableCell>{formatDate(inst.created_at)}</TableCell>
                    <TableCell className="text-center text-sm">
                      {inst.valid_data_count}/{inst.search_result_count}
                      {inst.duplicate_count > 0 && (
                        <span className="text-muted-foreground ml-1">(去重{inst.duplicate_count})</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-3">
                        <Button variant="link" className="h-auto p-0 font-normal" onClick={(e) => { e.stopPropagation(); navigate(`/task-instances/${inst.id}/results`) }}>
                          明细
                        </Button>
                        {inst.status === 'pending' && !inst.auto_run && (
                          <Button variant="link" className="h-auto p-0 font-normal" onClick={(e) => handleRunInstance(e, inst)} disabled={runningId === inst.id}>
                            {runningId === inst.id ? '执行中...' : '运行'}
                          </Button>
                        )}
                        {inst.status === 'pending' && !inst.auto_run && (
                          <Button variant="link" className="h-auto p-0 font-normal" onClick={(e) => handleEditInstance(e, inst)}>
                            编辑
                          </Button>
                        )}
                        {(inst.status === 'pending' || inst.search_result_count === 0) && (
                          <Button variant="link" className="h-auto p-0 font-normal text-destructive hover:text-destructive/80" onClick={(e) => handleDeleteInstance(e, inst)} disabled={deletingId === inst.id}>
                            {deletingId === inst.id ? '删除中...' : '删除'}
                          </Button>
                        )}
                        {['analyzing_completed', 'download_queued', 'downloading', 'completed', 'failed'].includes(inst.status) && (
                          <Button variant="link" className="h-auto p-0 font-normal" onClick={(e) => handleExport(e, inst)} disabled={exportingId === inst.id}>
                            {exportingId === inst.id ? '导出中...' : '导出'}
                          </Button>
                        )}
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

      {/* Right: Detail Panel */}
      <DetailPanel
        open={!!selectedInstance}
        title={selectedInstance?.instance_no || ''}
        onClose={() => setSelectedInstance(null)}
      >
        {detailLoading ? (
          <div className="text-center text-muted-foreground py-8">加载中...</div>
        ) : selectedInstance && (
          <>
            <DetailSection label="基本信息">
              <DetailRow label="实例编号">{selectedInstance.instance_no}</DetailRow>
              <DetailRow label="关联模板">{selectedInstance.meta_task_name}</DetailRow>
              <DetailRow label="状态">
                <Badge variant={STATUS_MAP[selectedInstance.status].variant}>
                  {STATUS_MAP[selectedInstance.status].label}
                </Badge>
              </DetailRow>
              <DetailRow label="执行模式">{selectedInstance.auto_run ? '直接运行' : '手动确认'}</DetailRow>
            </DetailSection>

            <DetailSection label="检索参数">
              <DetailRow label="检索词">{(selectedInstance as any).execution_params?.search_params?.query || '-'}</DetailRow>
              <DetailRow label="起始年份">{(selectedInstance as any).execution_params?.search_params?.year_from ?? '-'}</DetailRow>
              <DetailRow label="结束年份">{(selectedInstance as any).execution_params?.search_params?.year_to ?? '-'}</DetailRow>
              <DetailRow label="更新时间范围">{DATE_RANGE_LABELS[(selectedInstance as any).execution_params?.search_params?.date_range as string] || '-'}</DetailRow>
              <DetailRow label="核心期刊">{(selectedInstance as any).execution_params?.search_params?.core_only ? '是' : '否'}</DetailRow>
              <DetailRow label="同义词扩展">{(selectedInstance as any).execution_params?.search_params?.synonym_extend ? '是' : '否'}</DetailRow>
              {/* <DetailRow label="包含无全文">{(selectedInstance as any).execution_params?.search_params?.include_no_fulltext ? '是' : '否'}</DetailRow> */}
              <DetailRow label="导出上限">{(selectedInstance as any).execution_params?.search_params?.max_export ?? '-'}</DetailRow>
            </DetailSection>

            <DetailSection label="阶段时间">
              <DetailRow label="创建时间">{formatDate(selectedInstance.created_at)}</DetailRow>
              <DetailRow label="开始时间">{formatDate(selectedInstance.started_at)}</DetailRow>
              <DetailRow label="检索完成">{formatDate(selectedInstance.search_completed_at)}</DetailRow>
              <DetailRow label="分析完成">{formatDate(selectedInstance.analysis_completed_at)}</DetailRow>
              <DetailRow label="下载开始">{formatDate(selectedInstance.download_started_at)}</DetailRow>
              <DetailRow label="全部完成">{formatDate(selectedInstance.completed_at)}</DetailRow>
            </DetailSection>

            <DetailSection label="数据统计">
              <DetailRow label="检索总数">{selectedInstance.search_result_count}</DetailRow>
              <DetailRow label="有效数据">{selectedInstance.valid_data_count}</DetailRow>
              <DetailRow label="重复数">{selectedInstance.duplicate_count}</DetailRow>
              <DetailRow label="LLM分析">
                已完成 {selectedInstance.llm_analysis_completed_count ?? 0}
                <span className="text-muted-foreground">（通过 {selectedInstance.llm_analysis_passed_count ?? 0}/拒绝 {selectedInstance.llm_analysis_rejected_count ?? 0}）</span>
                失败 {selectedInstance.llm_analysis_failed_count ?? 0}
              </DetailRow>
              <DetailRow label="人工审核">
                通过 {selectedInstance.manual_review_passed_count ?? 0}
                <span className="text-muted-foreground"> / </span>
                拒绝 {selectedInstance.manual_review_rejected_count ?? 0}
              </DetailRow>
              <DetailRow label="下载">
                成功 {selectedInstance.download_success_count ?? 0}
                <span className="text-muted-foreground"> / </span>
                失败 {selectedInstance.download_failed_count ?? 0}
                {selectedInstance.download_skipped_count ? (
                  <>
                    <span className="text-muted-foreground"> / </span>
                    跳过 {selectedInstance.download_skipped_count}
                  </>
                ) : null}
              </DetailRow>
            </DetailSection>

            {selectedInstance.error_message && (
              <DetailSection label="错误信息">
                <p className="text-sm text-destructive">{selectedInstance.error_message}</p>
              </DetailSection>
            )}
          </>
        )}
      </DetailPanel>

      <ConfirmDialog
        open={!!confirmDelete}
        onOpenChange={(o) => { if (!o) setConfirmDelete(null) }}
        title="确认删除"
        description={`确认删除任务实例 ${confirmDelete?.instance_no}？删除后不可恢复。`}
        confirmText="删除"
        variant="destructive"
        onConfirm={doDeleteInstance}
        loading={deletingId !== null}
      />

      <ConfirmDialog
        open={!!confirmRun}
        onOpenChange={(o) => { if (!o) setConfirmRun(null) }}
        title="确认执行"
        description={`确认执行任务实例 ${confirmRun?.instance_no}？`}
        confirmText="执行"
        onConfirm={doRunInstance}
        loading={runningId !== null}
      />

      <EditDialog
        open={editDialogOpen}
        onOpenChange={(o) => { if (!o) setEditDialogOpen(false) }}
        instance={editInstance}
        onSuccess={() => { setEditDialogOpen(false); fetchInstances() }}
      />
    </div>
  )
}
