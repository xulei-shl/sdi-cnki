import { useState, useEffect, useMemo } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Select } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Plus, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { toast } from 'sonner'
import { createMetaTask, updateMetaTask, getDedupCandidates } from '@/api/meta-tasks'
import type { MetaTask, LlmConfig, SystemPrompt, DedupCandidate } from '@/types'

const MAX_EXPORT_OPTIONS = [50, 100, 150, 200, 250, 300, 350, 400, 450, 500]
const DATE_RANGE_OPTIONS = [
  { label: '不使用', value: '' },
  { label: '最近一周', value: 'week' },
  { label: '最近一月', value: 'month' },
  { label: '最近半年', value: 'half-year' },
  { label: '最近一年', value: 'year' },
  { label: '今年迄今', value: 'ytd' },
  { label: '上一年度', value: 'last-year' },
]

interface MetaTaskDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  editTask: MetaTask | null
  llmConfigs: LlmConfig[]
  prompts: SystemPrompt[]
  onSuccess: () => void
}

export function MetaTaskDialog({ open, onOpenChange, editTask, llmConfigs, prompts, onSuccess }: MetaTaskDialogProps) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [searchMode, setSearchMode] = useState<'basic' | 'professional'>('basic')
  const [queries, setQueries] = useState<string[]>([''])
  const [queryGroupA, setQueryGroupA] = useState<string[]>([''])
  const [queryGroupB, setQueryGroupB] = useState<string[]>([''])
  const [yearFrom, setYearFrom] = useState<string>('')
  const [yearTo, setYearTo] = useState<string>('')
  const [dateRange, setDateRange] = useState('')
  const [coreOnly, setCoreOnly] = useState(false)
  const [synonymExtend, setSynonymExtend] = useState(false)
  // const [includeNoFulltext, setIncludeNoFulltext] = useState(false)
  const [maxExport, setMaxExport] = useState(500)
  const [llmConfigIds, setLlmConfigIds] = useState<number[]>([])
  const [promptTemplateId, setPromptTemplateId] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [dedupScopeMetaTaskIds, setDedupScopeMetaTaskIds] = useState<number[]>([])
  const [dedupCandidates, setDedupCandidates] = useState<DedupCandidate[]>([])
  const [dedupSearch, setDedupSearch] = useState('')

  const isEdit = !!editTask
  const activeLlmConfigs = llmConfigs.filter(c => c.is_active)

  const addQuery = () => setQueries(prev => [...prev, ''])
  const removeQuery = (idx: number) => {
    if (queries.length <= 1) return
    setQueries(prev => prev.filter((_, i) => i !== idx))
  }
  const updateQuery = (idx: number, value: string) => {
    setQueries(prev => prev.map((q, i) => i === idx ? value : q))
  }

  const addGroupA = () => setQueryGroupA(prev => [...prev, ''])
  const removeGroupA = (idx: number) => {
    if (queryGroupA.length <= 1) return
    setQueryGroupA(prev => prev.filter((_, i) => i !== idx))
  }
  const updateGroupA = (idx: number, value: string) => {
    setQueryGroupA(prev => prev.map((q, i) => i === idx ? value : q))
  }

  const addGroupB = () => setQueryGroupB(prev => [...prev, ''])
  const removeGroupB = (idx: number) => {
    if (queryGroupB.length <= 1) return
    setQueryGroupB(prev => prev.filter((_, i) => i !== idx))
  }
  const updateGroupB = (idx: number, value: string) => {
    setQueryGroupB(prev => prev.map((q, i) => i === idx ? value : q))
  }

  useEffect(() => {
    if (open) {
      getDedupCandidates().then(res => {
        setDedupCandidates(res.data)
      }).catch(() => {
        setDedupCandidates([])
      })
      if (editTask) {
        setName(editTask.name)
        setDescription(editTask.description || '')
        const sp = (editTask as any).search_params || {}
        const mode = sp.search_mode === 'professional' ? 'professional' : 'basic'
        setSearchMode(mode)
        if (mode === 'professional') {
          setQueryGroupA(sp.query_group_a?.length ? sp.query_group_a : [''])
          setQueryGroupB(sp.query_group_b?.length ? sp.query_group_b : [''])
          setQueries([''])
        } else {
          const savedQueries = sp.queries?.length ? sp.queries : (sp.query ? [sp.query] : [''])
          setQueries(savedQueries)
          setQueryGroupA([''])
          setQueryGroupB([''])
        }
        setYearFrom(sp.year_from?.toString() || '')
        setYearTo(sp.year_to?.toString() || '')
        setDateRange(sp.date_range || '')
        setCoreOnly(sp.core_only || false)
        setSynonymExtend(sp.synonym_extend || false)
        // setIncludeNoFulltext(sp.include_no_fulltext || false)
        setMaxExport(sp.max_export || 500)
        setLlmConfigIds(editTask.llm_configs?.map(c => c.id) || [])
        setPromptTemplateId(editTask.prompt_template_id?.toString() || '')
        setDedupScopeMetaTaskIds(editTask.dedup_scope_meta_task_ids || [])
      } else {
        setName('')
        setDescription('')
        setSearchMode('basic')
        setQueries([''])
        setQueryGroupA([''])
        setQueryGroupB([''])
        setYearFrom('')
        setYearTo('')
        setDateRange('')
        setCoreOnly(false)
        setSynonymExtend(false)
        // setIncludeNoFulltext(false)
        setMaxExport(500)
        setLlmConfigIds([])
        setPromptTemplateId('')
        setDedupScopeMetaTaskIds([])
      }
      setErrors({})
    }
  }, [open, editTask])

  const validate = () => {
    const errs: Record<string, string> = {}
    if (!name.trim()) errs.name = '请输入任务名称'
    if (searchMode === 'professional') {
      const ga = queryGroupA.filter(q => q.trim())
      const gb = queryGroupB.filter(q => q.trim())
      if (ga.length === 0) errs.queryGroupA = '主题A 至少需要1个检索词'
      if (gb.length === 0) errs.queryGroupB = '主题B 至少需要1个检索词'
    } else {
      const nonEmpty = queries.filter(q => q.trim())
      if (nonEmpty.length === 0) errs.queries = '请至少输入一个检索词'
    }
    if (llmConfigIds.length === 0) errs.llmConfig = '请至少选择一个 LLM 配置'
    if (dateRange && (yearFrom || yearTo)) errs.dateRange = '与出版年份互斥'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const toggleLlmConfig = (id: number) => {
    setLlmConfigIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  const moveLlmConfig = (id: number, direction: -1 | 1) => {
    const idx = llmConfigIds.indexOf(id)
    if (idx === -1) return
    const newIdx = idx + direction
    if (newIdx < 0 || newIdx >= llmConfigIds.length) return
    const newArr = [...llmConfigIds]
      ;[newArr[idx], newArr[newIdx]] = [newArr[newIdx], newArr[idx]]
    setLlmConfigIds(newArr)
  }

  const handleSave = async () => {
    if (!validate()) return
    setSaving(true)
    try {
      const searchParams: any = {
        search_mode: searchMode,
        max_export: maxExport,
        core_only: coreOnly,
        synonym_extend: synonymExtend,
        // include_no_fulltext: includeNoFulltext,
      }
      if (searchMode === 'professional') {
        searchParams.query_group_a = queryGroupA.filter(q => q.trim())
        searchParams.query_group_b = queryGroupB.filter(q => q.trim())
      } else {
        searchParams.queries = queries.filter(q => q.trim())
      }
      if (dateRange) {
        searchParams.date_range = dateRange
      } else {
        searchParams.year_from = yearFrom ? parseInt(yearFrom) : null
        searchParams.year_to = yearTo ? parseInt(yearTo) : null
      }

      const data = {
        name: name.trim(),
        description: description.trim() || null,
        search_params: searchParams,
        llm_config_ids: llmConfigIds,
        prompt_template_id: promptTemplateId ? parseInt(promptTemplateId) : null,
        dedup_scope_meta_task_ids: dedupScopeMetaTaskIds,
      }

      if (isEdit) {
        await updateMetaTask(editTask!.id, data)
        toast.success('更新成功')
      } else {
        await createMetaTask(data)
        toast.success('创建成功')
      }
      onOpenChange(false)
      onSuccess()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const hasDateRange = dateRange !== ''
  const hasYearRange = yearFrom !== '' || yearTo !== ''

  const dedupFiltered = useMemo(() => {
    const q = dedupSearch.trim().toLowerCase()
    return dedupCandidates.filter(c => {
      if (c.id === editTask?.id) return false
      if (!q) return true
      return c.name.toLowerCase().includes(q)
    })
  }, [dedupCandidates, dedupSearch, editTask])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? '编辑任务模板' : '新建任务模板'}</DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Basic Info */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3 uppercase">基础信息</h3>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>任务名称 <span className="text-destructive">*</span></Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="最多 200 字" />
                {errors.name && <p className="text-xs text-destructive">{errors.name}</p>}
              </div>
              <div className="space-y-2">
                <Label>描述</Label>
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
              </div>
            </div>
          </div>

          {/* CNKI Search Params */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3 uppercase">CNKI 检索参数</h3>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>检索模式</Label>
                <div className="flex gap-1 border rounded-lg p-0.5 bg-muted/50 w-fit">
                  <button
                    type="button"
                    onClick={() => setSearchMode('basic')}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors ${searchMode === 'basic' ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    普通检索
                  </button>
                  <button
                    type="button"
                    onClick={() => setSearchMode('professional')}
                    className={`px-3 py-1.5 text-sm rounded-md transition-colors ${searchMode === 'professional' ? 'bg-background shadow-sm font-medium' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    专业检索
                  </button>
                </div>
              </div>

              {searchMode === 'professional' ? (
                <div className="space-y-5 border rounded-lg p-4 bg-muted/20">
                  <div className="space-y-3">
                    <Label style={{ color: 'var(--theme-a)' }} className="font-semibold">主题A 关键词组</Label>
                    <p className="text-xs text-muted-foreground">同义词/术语集合（如：阅读推广、全民阅读）</p>
                    {queryGroupA.map((q, idx) => (
                      <div key={idx} className="flex items-center gap-2 group/row">
                        <span
                          className="flex items-center justify-center w-5 h-5 rounded text-[11px] font-medium shrink-0"
                          style={{ backgroundColor: 'var(--theme-a-bg)', color: 'var(--theme-a)' }}
                        >
                          {idx + 1}
                        </span>
                        <Input value={q} onChange={(e) => updateGroupA(idx, e.target.value)} placeholder={`主题A 关键词 ${idx + 1}`} className="flex-1" />
                        <button
                          type="button"
                          onClick={() => removeGroupA(idx)}
                          className="text-muted-foreground/30 hover:text-destructive opacity-0 group-hover/row:opacity-100 transition-all shrink-0"
                          disabled={queryGroupA.length <= 1}
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={addGroupA} className="flex items-center gap-1.5 text-sm font-medium transition-opacity hover:opacity-80" style={{ color: 'var(--theme-a)' }}>
                      <Plus className="w-4 h-4" />
                      添加关键词
                    </button>
                    {errors.queryGroupA && <p className="text-xs text-destructive">{errors.queryGroupA}</p>}
                  </div>

                  <div className="flex items-center gap-3 text-sm">
                    <span className="h-px flex-1 bg-border" />
                    <span className="flex items-center gap-2 text-muted-foreground/60">
                      <span className="w-1 h-1 rounded-full bg-border" />
                      <span className="font-semibold tracking-wider text-foreground/50">AND</span>
                      <span className="w-1 h-1 rounded-full bg-border" />
                    </span>
                    <span className="h-px flex-1 bg-border" />
                  </div>

                  <div className="space-y-3">
                    <Label style={{ color: 'var(--theme-b)' }} className="font-semibold">主题B 关键词组</Label>
                    <p className="text-xs text-muted-foreground">同义词/术语集合（如：AI、大模型、AIGC）</p>
                    {queryGroupB.map((q, idx) => (
                      <div key={idx} className="flex items-center gap-2 group/row">
                        <span
                          className="flex items-center justify-center w-5 h-5 rounded text-[11px] font-medium shrink-0"
                          style={{ backgroundColor: 'var(--theme-b-bg)', color: 'var(--theme-b)' }}
                        >
                          {idx + 1}
                        </span>
                        <Input value={q} onChange={(e) => updateGroupB(idx, e.target.value)} placeholder={`主题B 关键词 ${idx + 1}`} className="flex-1" />
                        <button
                          type="button"
                          onClick={() => removeGroupB(idx)}
                          className="text-muted-foreground/30 hover:text-destructive opacity-0 group-hover/row:opacity-100 transition-all shrink-0"
                          disabled={queryGroupB.length <= 1}
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                    <button type="button" onClick={addGroupB} className="flex items-center gap-1.5 text-sm font-medium transition-opacity hover:opacity-80" style={{ color: 'var(--theme-b)' }}>
                      <Plus className="w-4 h-4" />
                      添加关键词
                    </button>
                    {errors.queryGroupB && <p className="text-xs text-destructive">{errors.queryGroupB}</p>}
                  </div>

                  <div className="text-xs leading-relaxed text-muted-foreground bg-muted/50 rounded-lg px-3 py-2 border border-border/50">
                    检索逻辑：<code className="text-foreground font-medium">(SU=A×B) OR (TKA=A×B)</code>，每组内关键词用 OR 连接，两组间用 AND 连接
                  </div>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label>检索词 <span className="text-destructive">*</span></Label>
                  {queries.map((q, idx) => (
                    <div key={idx} className="flex items-center gap-2">
                      <div className="flex items-center gap-1.5 shrink-0">
                        <span className="text-xs text-muted-foreground w-4">{idx + 1}</span>
                        <svg className="w-3.5 h-3.5 text-muted-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                        </svg>
                      </div>
                      <Input value={q} onChange={(e) => updateQuery(idx, e.target.value)} placeholder={`输入检索关键词 ${idx + 1}`} className="flex-1" />
                      <button
                        type="button"
                        onClick={() => removeQuery(idx)}
                        className="text-muted-foreground hover:text-destructive shrink-0"
                        disabled={queries.length <= 1}
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                  <button type="button" onClick={addQuery} className="flex items-center gap-1 text-sm text-primary hover:text-primary/80">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    添加检索词
                  </button>
                  {errors.queries && <p className="text-xs text-destructive">{errors.queries}</p>}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label>起始年份</Label>
                  <Input type="number" value={yearFrom} onChange={(e) => setYearFrom(e.target.value)} disabled={hasDateRange} placeholder="如 2020" />
                </div>
                <div className="space-y-2">
                  <Label>结束年份</Label>
                  <Input type="number" value={yearTo} onChange={(e) => setYearTo(e.target.value)} disabled={hasDateRange} placeholder="如 2025" />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">与更新时间范围互斥</p>

              <div className="space-y-2">
                <Label>更新时间范围</Label>
                <Select value={dateRange} onChange={(e) => setDateRange(e.target.value)} disabled={hasYearRange}>
                  {DATE_RANGE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </Select>
                <p className="text-xs text-muted-foreground">与出版年份互斥</p>
                {errors.dateRange && <p className="text-xs text-destructive">{errors.dateRange}</p>}
              </div>

              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={coreOnly} onChange={(e) => setCoreOnly(e.target.checked)} />
                  仅核心来源
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={synonymExtend} onChange={(e) => setSynonymExtend(e.target.checked)} />
                  同义词扩展
                </label>
                {/* <label className="flex items-center gap-2 text-sm">
                  <Checkbox checked={includeNoFulltext} onChange={(e) => setIncludeNoFulltext(e.target.checked)} />
                  包含无全文
                </label> */}
              </div>

              <div className="space-y-2">
                <Label>导出上限 <span className="text-destructive">*</span></Label>
                <Select value={maxExport} onChange={(e) => setMaxExport(Number(e.target.value))}>
                  {MAX_EXPORT_OPTIONS.map(v => (
                    <option key={v} value={v}>{v} 条</option>
                  ))}
                </Select>
              </div>
            </div>
          </div>

          {/* 去重范围 */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3 uppercase">去重配置</h3>
            <div className="space-y-2">
              <Label>去重范围（可选，多选）</Label>

              <Input
                placeholder="搜索任务模板..."
                value={dedupSearch}
                onChange={e => setDedupSearch(e.target.value)}
              />

              <ScrollArea className="border rounded-md p-2 max-h-48">
                {dedupFiltered.length === 0 ? (
                  <p className="text-sm text-muted-foreground py-2 text-center">
                    {dedupCandidates.length === 0 ? '无可选任务模板' : '无匹配模板'}
                  </p>
                ) : (
                  <div className="space-y-0.5">
                    {dedupFiltered.map(c => {
                      const checked = dedupScopeMetaTaskIds.includes(c.id)
                      return (
                        <label
                          key={c.id}
                          className="flex items-center gap-2 text-sm py-1 px-1 rounded cursor-pointer hover:bg-accent"
                        >
                          <Checkbox
                            checked={checked}
                            onChange={() => {
                              setDedupScopeMetaTaskIds(prev =>
                                checked ? prev.filter(x => x !== c.id) : [...prev, c.id]
                              )
                            }}
                          />
                          <span className="truncate">{c.name}</span>
                          <span className="text-xs text-muted-foreground shrink-0">（{c.creator_name}）</span>
                        </label>
                      )
                    })}
                  </div>
                )}
              </ScrollArea>

              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground">共 {dedupFiltered.length} 个模板，已选 {dedupScopeMetaTaskIds.length} 个</p>
              </div>

              <p className="text-xs text-muted-foreground">选择后，检索结果将与所选模板的所有历史数据比对去重，默认始终执行当前模板下的去重</p>
            </div>
          </div>

          {/* LLM Config */}
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3 uppercase">LLM 分析配置</h3>
            <div className="space-y-3">
              <div className="space-y-1">
                <Label>LLM 配置优先级 <span className="text-destructive">*</span></Label>
                <div className="border rounded-md p-3 space-y-2">
                  {llmConfigIds.length === 0 ? (
                    <p className="text-sm text-muted-foreground">请从下方选择 LLM 配置</p>
                  ) : (
                    <div className="space-y-1">
                      {llmConfigIds.map((id, idx) => {
                        const config = activeLlmConfigs.find(c => c.id === id)
                        return (
                          <div key={id} className="flex items-center justify-between bg-muted px-2 py-1 rounded">
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-muted-foreground w-4">{idx + 1}</span>
                              <span className="text-sm">{config?.name || id}</span>
                            </div>
                            <div className="flex gap-1">
                              <button className="text-xs px-1 hover:text-primary" disabled={idx === 0} onClick={() => moveLlmConfig(id, -1)}>↑</button>
                              <button className="text-xs px-1 hover:text-primary" disabled={idx === llmConfigIds.length - 1} onClick={() => moveLlmConfig(id, 1)}>↓</button>
                              <button className="text-xs px-1 hover:text-destructive" onClick={() => setLlmConfigIds(prev => prev.filter(x => x !== id))}>×</button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-1 pt-2 border-t">
                    {activeLlmConfigs.filter(c => !llmConfigIds.includes(c.id)).map(config => (
                      <Badge key={config.id} variant="outline" className="cursor-pointer hover:bg-accent" onClick={() => toggleLlmConfig(config.id)}>
                        {config.name}
                      </Badge>
                    ))}
                  </div>
                </div>
                {errors.llmConfig && <p className="text-xs text-destructive">{errors.llmConfig}</p>}
              </div>

              <div className="space-y-2">
                <Label>提示词模板</Label>
                <Select value={promptTemplateId} onChange={(e) => setPromptTemplateId(e.target.value)}>
                  <option value="">不选择</option>
                  {prompts.filter(p => p.is_active).map(p => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </Select>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
