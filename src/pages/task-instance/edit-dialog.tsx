import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
  const [query, setQuery] = useState('')
  const [yearFrom, setYearFrom] = useState<string>('')
  const [yearTo, setYearTo] = useState<string>('')
  const [dateRange, setDateRange] = useState('')
  const [coreOnly, setCoreOnly] = useState(false)
  const [synonymExtend, setSynonymExtend] = useState(false)
  // const [includeNoFulltext, setIncludeNoFulltext] = useState(false)
  const [maxExport, setMaxExport] = useState(500)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (open && instance) {
      const sp = instance.execution_params?.search_params || {}
      setQuery(sp.query || '')
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
    if (!query.trim()) errs.query = '请输入检索词'
    if (dateRange && (yearFrom || yearTo)) errs.dateRange = '与出版年份互斥'
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSave = async () => {
    if (!validate() || !instance) return
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
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>编辑检索参数</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground -mt-2">
          实例：{instance?.instance_no}（编辑后的参数将覆盖模板中的参数）
        </p>

        <div className="space-y-6 py-2">
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

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
