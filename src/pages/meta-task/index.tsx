import { useState, useEffect, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Pagination } from '@/components/ui/pagination'
import { DetailPanel, DetailSection, DetailRow } from '@/components/layout/detail-panel'
import { toast } from 'sonner'
import { getMetaTasks, getMetaTask, deleteMetaTask, executeMetaTask, type MetaTaskQuery } from '@/api/meta-tasks'
import { getLlmConfigs } from '@/api/llm-configs'
import { getSystemPrompts } from '@/api/system-prompts'
import { MetaTaskDialog } from './dialog'
import { ExecuteDialog } from './execute-dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import type { MetaTask, LlmConfig, SystemPrompt } from '@/types'

const DATE_RANGE_LABELS: Record<string, string> = {
  week: '最近一周', month: '最近一月', 'half-year': '最近半年',
  year: '最近一年', ytd: '今年迄今', 'last-year': '上一年度',
}

export default function MetaTaskPage() {
  const [tasks, setTasks] = useState<MetaTask[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedTask, setSelectedTask] = useState<MetaTask | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editTask, setEditTask] = useState<MetaTask | null>(null)
  const [executeOpen, setExecuteOpen] = useState(false)
  const [executeTaskId, setExecuteTaskId] = useState<number | null>(null)
  const [executing, setExecuting] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [llmConfigs, setLlmConfigs] = useState<LlmConfig[]>([])
  const [prompts, setPrompts] = useState<SystemPrompt[]>([])

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    try {
      const params: MetaTaskQuery = { page, page_size: 20 }
      if (searchKeyword) params.keyword = searchKeyword
      const res = await getMetaTasks(params)
      setTasks(res.data.items)
      setTotal(res.data.total)
    } finally {
      setLoading(false)
    }
  }, [page, searchKeyword])

  useEffect(() => { fetchTasks() }, [fetchTasks])

  const handleSearch = () => {
    setPage(1)
    setSearchKeyword(keyword)
  }

  const handleRowClick = async (taskId: number) => {
    const existing = tasks.find(t => t.id === taskId)
    if (existing) {
      setDetailLoading(true)
      try {
        const res = await getMetaTask(taskId)
        setSelectedTask({ ...existing, ...res.data })
      } finally {
        setDetailLoading(false)
      }
    }
  }

  const openCreate = async () => {
    const [llmRes, promptRes] = await Promise.all([
      getLlmConfigs(),
      getSystemPrompts(),
    ])
    setLlmConfigs(llmRes.data.items || [])
    setPrompts(promptRes.data.items || [])
    setEditTask(null)
    setDialogOpen(true)
  }

  const openEdit = async (e: React.MouseEvent, task: MetaTask) => {
    e.stopPropagation()
    const [llmRes, promptRes, detailRes] = await Promise.all([
      getLlmConfigs(),
      getSystemPrompts(),
      getMetaTask(task.id),
    ])
    setLlmConfigs(llmRes.data.items || [])
    setPrompts(promptRes.data.items || [])
    setEditTask({ ...task, ...detailRes.data })
    setDialogOpen(true)
  }

  const handleDelete = (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    setConfirmDeleteId(id)
  }

  const doDelete = async () => {
    if (!confirmDeleteId) return
    setDeletingId(confirmDeleteId)
    setConfirmDeleteId(null)
    try {
      await deleteMetaTask(confirmDeleteId)
      toast.success('删除成功')
      fetchTasks()
      if (selectedTask?.id === confirmDeleteId) setSelectedTask(null)
    } catch {
      toast.error('删除失败，请检查是否有关联的实例')
    } finally {
      setDeletingId(null)
    }
  }

  const handleExecute = (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    setExecuteTaskId(id)
    setExecuteOpen(true)
  }

  const confirmExecute = async (autoRun: boolean) => {
    if (!executeTaskId) return
    setExecuting(executeTaskId)
    try {
      await executeMetaTask(executeTaskId, autoRun)
      toast.success(autoRun ? '任务已开始执行' : '任务实例已创建')
      fetchTasks()
      setExecuteOpen(false)
    } catch {
      toast.error('执行失败')
    } finally {
      setExecuting(null)
    }
  }

  const formatDate = (d: string | null | undefined) => {
    if (!d) return '-'
    return d.slice(0, 16).replace('T', ' ')
  }

  const statusVariant = (isActive: boolean | undefined) =>
    isActive ? 'success' as const : 'secondary' as const
  const statusLabel = (isActive: boolean | undefined) =>
    isActive ? '启用' : '禁用'

  return (
    <div className="h-full flex overflow-hidden relative">
      {/* Middle: List Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Search Bar */}
        <div className="px-8 py-6 border-b flex items-center gap-4">
          <Input
            placeholder="按任务名称搜索..."
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="w-[320px]"
          />
          <Button variant="secondary" onClick={handleSearch}>检索</Button>
          <div className="flex-1" />
          <Button onClick={openCreate}>新建任务</Button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-auto px-8 py-6">
          <Table className="table-fixed">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[180px]">任务名称</TableHead>
                <TableHead>描述</TableHead>
                <TableHead className="w-[130px]">LLM 配置</TableHead>
                <TableHead className="w-[72px]">创建者</TableHead>
                <TableHead className="w-[120px]">创建时间</TableHead>
                <TableHead className="w-[80px] text-center">执行次数</TableHead>
                <TableHead className="w-[80px]">状态</TableHead>
                <TableHead className="w-[120px]">最后执行</TableHead>
                <TableHead className="w-[140px] text-right">操作</TableHead>
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
              ) : tasks.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-8 text-muted-foreground">暂无任务模板</TableCell>
                </TableRow>
              ) : tasks.map((task) => (
                <TableRow
                  key={task.id}
                  className="cursor-pointer"
                  onClick={() => handleRowClick(task.id)}
                  data-state={selectedTask?.id === task.id ? 'selected' : undefined}
                >
                  <TableCell className="font-medium truncate">{task.name}</TableCell>
                  <TableCell className="truncate text-muted-foreground">{task.description || '-'}</TableCell>
                  <TableCell>
                    <div className="flex gap-1 flex-wrap">
                      {task.llm_configs?.map((c) => (
                        <Badge key={c.id} variant="secondary" className="text-xs">{c.name}</Badge>
                      )) || (task as any).llm_config_names?.map((n: string, i: number) => (
                        <Badge key={i} variant="secondary" className="text-xs">{n}</Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell>{task.creator_name || '-'}</TableCell>
                  <TableCell>{formatDate(task.created_at)}</TableCell>
                  <TableCell className="text-center">{task.execution_count}</TableCell>
                  <TableCell>
                    <Badge variant={statusVariant(task.is_active)}>{statusLabel(task.is_active)}</Badge>
                  </TableCell>
                  <TableCell>{formatDate(task.last_executed_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={(e) => openEdit(e, task)}>编辑</Button>
                      <Button variant="ghost" size="sm" onClick={(e) => handleExecute(e, task.id)}>运行</Button>
                      {task.execution_count === 0 && (
                        <Button variant="ghost" size="sm" className="text-destructive" onClick={(e) => handleDelete(e, task.id)}>删除</Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <Pagination current={page} total={total} pageSize={20} onChange={setPage} />
        </div>
      </div>

      {/* Right: Detail Panel */}
      <DetailPanel
        open={!!selectedTask}
        title={selectedTask?.name || ''}
        onClose={() => setSelectedTask(null)}
      >
        {detailLoading ? (
          <div className="text-center text-muted-foreground py-8">加载中...</div>
        ) : selectedTask && (
          <>
            <DetailSection label="基本信息">
              <DetailRow label="任务名称">{selectedTask.name}</DetailRow>
              <DetailRow label="描述">{selectedTask.description || '-'}</DetailRow>
              <DetailRow label="创建者">{selectedTask.creator_name || String(selectedTask.creator_id)}</DetailRow>
              <DetailRow label="创建时间">{formatDate(selectedTask.created_at)}</DetailRow>
              <DetailRow label="最后执行">{formatDate(selectedTask.last_executed_at)}</DetailRow>
            </DetailSection>

            <DetailSection label="检索参数">
              <DetailRow label="检索词">{(selectedTask as any).search_params?.query || '-'}</DetailRow>
              <DetailRow label="起始年份">{(selectedTask as any).search_params?.year_from ?? '-'}</DetailRow>
              <DetailRow label="结束年份">{(selectedTask as any).search_params?.year_to ?? '-'}</DetailRow>
              <DetailRow label="更新时间范围">{DATE_RANGE_LABELS[(selectedTask as any).search_params?.date_range as string] || '-'}</DetailRow>
              <DetailRow label="核心期刊">{(selectedTask as any).search_params?.core_only ? '是' : '否'}</DetailRow>
              <DetailRow label="同义词扩展">{(selectedTask as any).search_params?.synonym_extend ? '是' : '否'}</DetailRow>
              <DetailRow label="包含无全文">{(selectedTask as any).search_params?.include_no_fulltext ? '是' : '否'}</DetailRow>
              <DetailRow label="导出上限">{(selectedTask as any).search_params?.max_export ?? '-'}</DetailRow>
            </DetailSection>

            <DetailSection label="LLM 分析配置">
              {selectedTask.llm_configs?.length ? (
                selectedTask.llm_configs.map((c) => (
                  <DetailRow key={c.id} label={`优先级 ${c.priority + 1}`}>{c.name}</DetailRow>
                ))
              ) : (
                <div className="text-sm text-muted-foreground">无配置</div>
              )}
              <DetailRow label="提示词模板">{selectedTask.prompt_template_name || '未选择'}</DetailRow>
            </DetailSection>

            <DetailSection label="执行历史">
              {(selectedTask as any).recent_instances?.length ? (
                (selectedTask as any).recent_instances.map((inst: any) => (
                  <div key={inst.id} className="flex justify-between py-1 text-sm border-b last:border-0">
                    <span className="text-muted-foreground">{inst.instance_no}</span>
                    <Badge variant="secondary" className="text-xs">{inst.status}</Badge>
                  </div>
                ))
              ) : (
                <div className="text-sm text-muted-foreground">暂无执行记录</div>
              )}
            </DetailSection>
          </>
        )}
      </DetailPanel>

      {/* Dialogs */}
      <MetaTaskDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        editTask={editTask}
        llmConfigs={llmConfigs}
        prompts={prompts}
        onSuccess={() => { fetchTasks(); setSelectedTask(null) }}
      />

      <ExecuteDialog
        open={executeOpen}
        onOpenChange={setExecuteOpen}
        onRunDirect={() => confirmExecute(true)}
        onRunDraft={() => confirmExecute(false)}
        loading={executing !== null}
      />

      <ConfirmDialog
        open={!!confirmDeleteId}
        onOpenChange={(o) => { if (!o) setConfirmDeleteId(null) }}
        title="确认删除"
        description="确认删除该任务模板？删除后不可恢复。"
        confirmText="删除"
        variant="destructive"
        onConfirm={doDelete}
        loading={deletingId !== null}
      />
    </div>
  )
}
