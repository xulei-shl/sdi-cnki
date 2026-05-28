import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Plus, X } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { Select } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { updateTaskInstanceParams } from '@/api/task-instances'
import type { TaskInstance } from '@/types'

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

interface EditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  instance: TaskInstance | null
  onSuccess: () => void
}

export function EditDialog({ open, onOpenChange, instance, onSuccess }: EditDialogProps) {
  const [searchMode, setSearchMode] = useState<'basic' | 'professional'>('basic')
  const [queries, setQueries] = useState<string[]>([''])
  const [queryGroupA, setQueryGroupA] = useState<string[]>([''])
  const [queryGroupB, setQueryGroupB] = useState<string[]>([''])
  const [auGroup, setAuGroup] = useState<string[]>([])
  const [fuGroup, setFuGroup] = useState<string[]>([])
  const [yearFrom, setYearFrom] = useState<string>('')
  const [yearTo, setYearTo] = useState<string>('')
  const [dateRange, setDateRange] = useState('')
  const [coreOnly, setCoreOnly] = useState(false)
  const [synonymExtend, setSynonymExtend] = useState(false)
  // const [includeNoFulltext, setIncludeNoFulltext] = useState(false)
  const [maxExport, setMaxExport] = useState(500)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

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

  const addAuthor = () => setAuGroup(prev => [...prev, ''])
  const removeAuthor = (idx: number) => {
    if (auGroup.length <= 1) return
    setAuGroup(prev => prev.filter((_, i) => i !== idx))
  }
  const updateAuthor = (idx: number, value: string) => {
    setAuGroup(prev => prev.map((a, i) => i === idx ? value : a))
  }

  const addFund = () => setFuGroup(prev => [...prev, ''])
  const removeFund = (idx: number) => {
    if (fuGroup.length <= 1) return
    setFuGroup(prev => prev.filter((_, i) => i !== idx))
  }
  const updateFund = (idx: number, value: string) => {
    setFuGroup(prev => prev.map((f, i) => i === idx ? value : f))
  }

  useEffect(() => {
    if (open && instance) {
      const sp = instance.execution_params?.search_params || {}
      const mode = sp.search_mode === 'professional' ? 'professional' : 'basic'
      setSearchMode(mode)
      if (mode === 'professional') {
        setQueryGroupA(sp.query_group_a?.length ? sp.query_group_a : [''])
        setQueryGroupB(sp.query_group_b?.length ? sp.query_group_b : [''])
        setAuGroup(sp.au_group?.length ? sp.au_group : [])
        setFuGroup(sp.fu_group?.length ? sp.fu_group : [])
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
      setErrors({})
    }
  }, [open, instance])

  const validate = () => {
    const errs: Record<string, string> = {}
    if (searchMode === 'professional') {
      const ga = queryGroupA.filter(q => q.trim())
      const gb = queryGroupB.filter(q => q.trim())
      const au = auGroup.filter(a => a.trim())
      const fu = fuGroup.filter(f => f.trim())
      if (ga.length === 0 && gb.length === 0 && au.length === 0 && fu.length === 0) {
        errs.queryGroupA = '检索词/作者/基金至少需要填写一项'
      }
    } else {
      const nonEmpty = queries.filter(q => q.trim())
      if (nonEmpty.length === 0) errs.queries = '请至少输入一个检索词'
    }
    if (dateRange && (yearFrom || yearTo)) errs.dateRange = '与出版年份互斥'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSave = async () => {
    if (!validate() || !instance) return
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
        const au = auGroup.filter(a => a.trim())
        if (au.length) searchParams.au_group = au
        const fu = fuGroup.filter(f => f.trim())
        if (fu.length) searchParams.fu_group = fu
      } else {
        searchParams.queries = queries.filter(q => q.trim())
      }
      if (dateRange) {
        searchParams.date_range = dateRange
      } else {
        searchParams.year_from = yearFrom ? parseInt(yearFrom) : null
        searchParams.year_to = yearTo ? parseInt(yearTo) : null
      }

      await updateTaskInstanceParams(instance.id, searchParams)
      toast.success('检索参数已更新')
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
      <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>编辑检索参数</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground -mt-2">
          实例：{instance?.instance_no}（编辑后的参数将覆盖模板中的参数）
        </p>

        <div className="space-y-6 py-2">
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
            <div className="search-params-container space-y-4" style={{ containerType: 'inline-size' }}>
              {/* Theme Domain: A + B side by side */}
              <div className="topic-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {/* Theme A */}
                <div className="space-y-2.5 border rounded-lg p-3.5 bg-muted/20" style={{ borderColor: 'var(--theme-a-bg)' }}>
                  <Label style={{ color: 'var(--theme-a)' }} className="font-semibold text-sm">主题A 关键词组</Label>
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

                {/* Theme B */}
                <div className="space-y-2.5 border rounded-lg p-3.5 bg-muted/20" style={{ borderColor: 'var(--theme-b-bg)' }}>
                  <Label style={{ color: 'var(--theme-b)' }} className="font-semibold text-sm">主题B 关键词组</Label>
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
              </div>

              {/* AND divider between theme and filter domains */}
              <div className="flex items-center gap-3 text-sm">
                <span className="h-px flex-1 bg-border" />
                <span className="font-semibold tracking-wider text-foreground/40 text-xs">AND</span>
                <span className="h-px flex-1 bg-border" />
              </div>

              {/* Filter Domain: AU + FU side by side, lighter style */}
              <div className="filter-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                {/* Author */}
                <div className="space-y-2 rounded-lg p-3 bg-muted/10">
                  <Label className="font-medium text-sm text-muted-foreground">作者（可选）</Label>
                  <p className="text-xs text-muted-foreground">多个作者用 OR 连接</p>
                  {auGroup.map((au, idx) => (
                    <div key={idx} className="flex items-center gap-2 group/row">
                      <span className="flex items-center justify-center w-5 h-5 rounded text-[11px] font-medium shrink-0 bg-muted-foreground/10 text-muted-foreground">
                        {idx + 1}
                      </span>
                      <Input value={au} onChange={(e) => updateAuthor(idx, e.target.value)} placeholder={`作者姓名 ${idx + 1}`} className="flex-1" />
                      <button
                        type="button"
                        onClick={() => removeAuthor(idx)}
                        className="text-muted-foreground/30 hover:text-destructive opacity-0 group-hover/row:opacity-100 transition-all shrink-0"
                        disabled={auGroup.length <= 1}
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  <button type="button" onClick={addAuthor} className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-opacity hover:opacity-80">
                    <Plus className="w-4 h-4" />
                    添加作者
                  </button>
                </div>

                {/* Fund */}
                <div className="space-y-2 rounded-lg p-3 bg-muted/10">
                  <Label className="font-medium text-sm text-muted-foreground">基金（可选）</Label>
                  <p className="text-xs text-muted-foreground">多个基金用 OR 连接</p>
                  {fuGroup.map((fu, idx) => (
                    <div key={idx} className="flex items-center gap-2 group/row">
                      <span className="flex items-center justify-center w-5 h-5 rounded text-[11px] font-medium shrink-0 bg-muted-foreground/10 text-muted-foreground">
                        {idx + 1}
                      </span>
                      <Input value={fu} onChange={(e) => updateFund(idx, e.target.value)} placeholder={`基金名称 ${idx + 1}`} className="flex-1" />
                      <button
                        type="button"
                        onClick={() => removeFund(idx)}
                        className="text-muted-foreground/30 hover:text-destructive opacity-0 group-hover/row:opacity-100 transition-all shrink-0"
                        disabled={fuGroup.length <= 1}
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  <button type="button" onClick={addFund} className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground transition-opacity hover:opacity-80">
                    <Plus className="w-4 h-4" />
                    添加基金
                  </button>
                </div>
              </div>

              {/* Search logic hint - simplified */}
              <div className="text-xs leading-relaxed text-muted-foreground bg-muted/50 rounded-lg px-3 py-2 border border-border/50">
                表达式：<code className="text-foreground font-medium">(SU=A×B) OR (TKA=A×B)</code> · 组内 OR · 组间 AND
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

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
