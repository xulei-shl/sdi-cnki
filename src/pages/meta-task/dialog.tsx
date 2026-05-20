import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { Select } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
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
  const [query, setQuery] = useState('')
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

  const isEdit = !!editTask
  const activeLlmConfigs = llmConfigs.filter(c => c.is_active)

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
        setQuery(sp.query || '')
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
        setQuery('')
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
    if (!query.trim()) errs.query = '请输入检索词'
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
        query: query.trim(),
        max_export: maxExport,
        core_only: coreOnly,
        synonym_extend: synonymExtend,
        // include_no_fulltext: includeNoFulltext,
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
                <Label>检索词 <span className="text-destructive">*</span></Label>
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入检索关键词" />
                {errors.query && <p className="text-xs text-destructive">{errors.query}</p>}
              </div>

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
              <div className="border rounded-md p-3 space-y-1">
                {dedupCandidates.filter(c => c.id !== editTask?.id).length === 0 ? (
                  <p className="text-sm text-muted-foreground">无可选任务模板</p>
                ) : (
                  dedupCandidates.filter(c => c.id !== editTask?.id).map(c => {
                    const checked = dedupScopeMetaTaskIds.includes(c.id)
                    return (
                      <label key={c.id} className="flex items-center gap-2 text-sm py-0.5 cursor-pointer hover:text-primary">
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => {
                            setDedupScopeMetaTaskIds(prev =>
                              checked ? prev.filter(x => x !== c.id) : [...prev, c.id]
                            )
                          }}
                        />
                        {c.name}（{c.creator_name}）
                      </label>
                    )
                  })
                )}
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
