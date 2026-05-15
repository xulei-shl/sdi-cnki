import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Pagination } from '@/components/ui/pagination'
import { DetailPanel, DetailSection, DetailRow } from '@/components/layout/detail-panel'
import { toast } from 'sonner'
import { getTaskInstances, getTaskInstance, runTaskInstance, type TaskInstanceQuery } from '@/api/task-instances'
import type { TaskInstance, TaskStatus } from '@/types'

const STATUS_MAP: Record<TaskStatus, { label: string; variant: 'info' | 'warning' | 'success' | 'destructive' | 'secondary' | 'default' }> = {
  pending: { label: '待执行', variant: 'secondary' },
  running: { label: '检索中', variant: 'info' },
  search_completed: { label: '已检索', variant: 'info' },
  analyzing: { label: '分析中', variant: 'info' },
  analyzing_completed: { label: '审核中', variant: 'info' },
  ready_for_download: { label: '等待下载', variant: 'info' },
  downloading: { label: '下载中', variant: 'info' },
  completed: { label: '已完成', variant: 'success' },
  failed: { label: '失败', variant: 'destructive' },
  cancelled: { label: '已取消', variant: 'secondary' },
}

const STATUS_OPTIONS = [
  { label: '全部', value: '' },
  { label: '待执行', value: 'pending' },
  { label: '检索中', value: 'running' },
  { label: '已检索', value: 'search_completed' },
  { label: '分析中', value: 'analyzing' },
  { label: '审核中', value: 'analyzing_completed' },
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
    if (!confirm(`确认执行任务实例 ${inst.instance_no}？`)) return
    setRunningId(inst.id)
    try {
      await runTaskInstance(inst.id)
      toast.success('任务已加入执行队列')
      fetchInstances()
      if (selectedInstance?.id === inst.id) handleRowClick(inst.id)
    } catch {
      toast.error('执行失败')
    } finally {
      setRunningId(null)
    }
  }

  const formatDate = (d: string | null | undefined) => {
    if (!d) return '-'
    return d.slice(0, 16).replace('T', ' ')
  }

  return (
    <div className="h-full flex overflow-hidden">
      {/* Middle: List Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Search Bar */}
        <div className="p-4 border-b flex items-center gap-3 flex-wrap">
          <Input
            placeholder="实例编号搜索..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            className="max-w-[200px]"
          />
          <Input
            placeholder="关联模板名称..."
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            className="max-w-[200px]"
          />
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-[140px]">
            {STATUS_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
          <Button variant="secondary" onClick={() => { setPage(1); fetchInstances() }}>检索</Button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto p-4 pt-2">
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
                  <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">加载中...</TableCell>
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
                    <TableCell>{inst.creator_id}</TableCell>
                    <TableCell>{formatDate(inst.created_at)}</TableCell>
                    <TableCell className="text-center text-sm">
                      {inst.valid_data_count}/{inst.search_result_count}
                      {inst.duplicate_count > 0 && (
                        <span className="text-muted-foreground ml-1">(去重{inst.duplicate_count})</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); navigate(`/task-instances/${inst.id}/results`) }}>
                          查看
                        </Button>
                        {inst.status === 'pending' && !inst.auto_run && (
                          <Button variant="ghost" size="sm" onClick={(e) => handleRunInstance(e, inst)} disabled={runningId === inst.id}>
                            {runningId === inst.id ? '执行中...' : '运行'}
                          </Button>
                        )}
                        {inst.status === 'pending' && !inst.auto_run && (
                          <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); toast.info('编辑功能开发中') }}>
                            编辑
                          </Button>
                        )}
                        {inst.status === 'analyzing_completed' && (
                          <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); toast.info('下载功能开发中') }}>
                            下载
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
            </DetailSection>

            {selectedInstance.error_message && (
              <DetailSection label="错误信息">
                <p className="text-sm text-destructive">{selectedInstance.error_message}</p>
              </DetailSection>
            )}
          </>
        )}
      </DetailPanel>
    </div>
  )
}
