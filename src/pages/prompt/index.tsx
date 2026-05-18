import { useState, useEffect } from 'react'
import { useHiagentWidget } from '@/hooks/use-hiagent-widget'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Select } from '@/components/ui/select'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { DetailPanel, DetailSection, DetailRow } from '@/components/layout/detail-panel'
import { toast } from 'sonner'
import { useAuth } from '@/context/auth'
import { getSystemPrompts, createSystemPrompt, updateSystemPrompt, deleteSystemPrompt } from '@/api/system-prompts'
import { getPromptTemplates } from '@/api/prompt-templates'
import type { SystemPrompt, PromptTemplate } from '@/types'

export default function PromptPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [prompts, setPrompts] = useState<SystemPrompt[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editItem, setEditItem] = useState<SystemPrompt | null>(null)
  const [viewItem, setViewItem] = useState<SystemPrompt | null>(null)
  const [saving, setSaving] = useState(false)

  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [version, setVersion] = useState('1.0')
  const [tags, setTags] = useState('')
  const [isActive, setIsActive] = useState(true)

  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState('')

  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getSystemPrompts()
      setPrompts(res.data.items || [])
    } catch (err: any) {
      console.error('获取提示词列表失败', err)
      toast.error('加载提示词列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  useHiagentWidget(import.meta.env.VITE_HIAGENT_PROMPT_APP_KEY)

  const openCreate = async () => {
    setEditItem(null)
    setName('')
    setContent('')
    setVersion('1.0')
    setTags('')
    setIsActive(true)
    setSelectedTemplate('')
    setDialogOpen(true)
    try {
      const res = await getPromptTemplates()
      setTemplates(res.data.items?.filter(t => t.is_active) || [])
    } catch {
      setTemplates([])
    }
  }

  const openEdit = (item: SystemPrompt) => {
    setEditItem(item)
    setName(item.name)
    setContent(item.content)
    setVersion(item.version)
    setTags(item.tags || '')
    setIsActive(item.is_active)
    setSelectedTemplate('')
    setDialogOpen(true)
  }

  const handleTemplateSelect = (templateId: string) => {
    setSelectedTemplate(templateId)
    if (!templateId) return
    const template = templates.find(t => t.id === parseInt(templateId))
    if (template) {
      setContent(template.content)
    }
  }

  const handleSave = async () => {
    if (!name.trim()) { toast.error('请输入名称'); return }
    if (!content.trim()) { toast.error('请输入提示词内容'); return }
    setSaving(true)
    try {
      const data = {
        name: name.trim(),
        content: content.trim(),
        version: version.trim() || '1.0',
        tags: tags.trim(),
        is_active: isActive,
      }
      if (editItem) {
        await updateSystemPrompt(editItem.id, data)
        toast.success('更新成功')
      } else {
        await createSystemPrompt(data)
        toast.success('创建成功')
      }
      setDialogOpen(false)
      setTimeout(() => fetchData(), 0)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '操作失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteClick = (e: React.MouseEvent, id: number) => {
    e.stopPropagation()
    setConfirmDeleteId(id)
  }

  const doDelete = async () => {
    if (!confirmDeleteId) return
    setDeletingId(confirmDeleteId)
    setConfirmDeleteId(null)
    try {
      await deleteSystemPrompt(confirmDeleteId)
      toast.success('删除成功')
      fetchData()
    } catch (err: any) {
      const detail = err?.response?.data?.detail || '删除失败'
      toast.error(detail)
    } finally {
      setDeletingId(null)
    }
  }

  const formatDate = (d: string) => d?.slice(0, 16).replace('T', ' ') || '-'

  return (
    <div className="h-full flex overflow-hidden relative">
      <div className="flex-1 flex flex-col min-w-0">
        <div className="px-8 py-6 border-b flex items-center justify-between shrink-0">
          <h2 className="text-lg font-semibold">提示词</h2>
          <Button onClick={openCreate}>新建提示词</Button>
        </div>

        <div className="flex-1 overflow-auto px-8 py-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>版本</TableHead>
                <TableHead>标签</TableHead>
                {isAdmin && <TableHead>创建者</TableHead>}
                <TableHead>状态</TableHead>
                <TableHead>更新时间</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={isAdmin ? 7 : 6} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
              ) : prompts.length === 0 ? (
                <TableRow><TableCell colSpan={isAdmin ? 7 : 6} className="text-center py-8 text-muted-foreground">暂无提示词</TableCell></TableRow>
              ) : prompts.map((p) => (
                <TableRow key={p.id} className="cursor-pointer" onClick={() => setViewItem(p)}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell>{p.version}</TableCell>
                  <TableCell>
                    <div className="flex gap-1 flex-wrap">
                      {p.tags?.split(',').filter(Boolean).map((tag, i) => (
                        <Badge key={i} variant="secondary" className="text-xs">{tag.trim()}</Badge>
                      )) || '-'}
                    </div>
                  </TableCell>
                  {isAdmin && <TableCell>{p.creator_name || '-'}</TableCell>}
                  <TableCell>
                    <Badge variant={p.is_active ? 'success' : 'secondary'}>{p.is_active ? '启用' : '禁用'}</Badge>
                  </TableCell>
                  <TableCell>{formatDate(p.updated_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-3">
                      <Button variant="link" className="h-auto p-0 font-normal" onClick={(e) => { e.stopPropagation(); openEdit(p); }}>编辑</Button>
                      {p.ref_count === 0 && (
                        <Button variant="link" className="h-auto p-0 font-normal text-destructive hover:text-destructive/80" onClick={(e) => handleDeleteClick(e, p.id)}>删除</Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {/* Create/Edit Dialog */}
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editItem ? '编辑提示词' : '新建提示词'}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-2">
              {/* Prompt Template Selector (only on create) */}
              {!editItem && templates.length > 0 && (
                <div className="space-y-2">
                  <Label>提示词模板（可选）</Label>
                  <Select value={selectedTemplate} onChange={(e) => handleTemplateSelect(e.target.value)}>
                    <option value="">不选择模板，从零创建</option>
                    {templates.map(t => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </Select>
                  <p className="text-xs text-muted-foreground">选择后将自动填充提示词内容，可在此基础上编辑</p>
                </div>
              )}
              <div className="space-y-2">
                <Label>名称 <span className="text-destructive">*</span></Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>提示词内容 <span className="text-destructive">*</span></Label>
                <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={12} className="font-mono text-sm" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>版本</Label>
                  <Input value={version} onChange={(e) => setVersion(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>标签（逗号分隔）</Label>
                  <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="如 相关性评估, 默认模板" />
                </div>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <Switch checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
                <Label>启用</Label>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
              <Button onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

      </div>

      {/* Right: Detail Panel */}
      <DetailPanel
        open={!!viewItem}
        title={viewItem?.name || ''}
        onClose={() => setViewItem(null)}
      >
        {viewItem && (
          <>
            <DetailSection label="基本信息">
              <DetailRow label="版本">{viewItem.version}</DetailRow>
              <DetailRow label="状态">{viewItem.is_active ? '启用' : '禁用'}</DetailRow>
              {viewItem.tags && <DetailRow label="标签">{viewItem.tags}</DetailRow>}
              {isAdmin && viewItem.creator_name && <DetailRow label="创建者">{viewItem.creator_name}</DetailRow>}
            </DetailSection>
            <DetailSection label="内容">
              <pre className="border rounded-md p-4 text-sm whitespace-pre-wrap font-mono bg-muted/30 max-h-[60vh] overflow-y-auto">
                {viewItem.content}
              </pre>
            </DetailSection>
          </>
        )}
      </DetailPanel>

      <ConfirmDialog
        open={!!confirmDeleteId}
        onOpenChange={(o) => { if (!o) setConfirmDeleteId(null) }}
        title="确认删除"
        description="确认删除此提示词？删除后不可恢复。"
        confirmText="删除"
        variant="destructive"
        onConfirm={doDelete}
        loading={deletingId !== null}
      />
    </div>
  )
}
