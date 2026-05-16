import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { DetailPanel, DetailSection, DetailRow } from '@/components/layout/detail-panel'
import { toast } from 'sonner'
import { getPromptTemplates, createPromptTemplate, updatePromptTemplate, deletePromptTemplate } from '@/api/prompt-templates'
import type { PromptTemplate } from '@/types'

export default function PromptTemplatePage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editItem, setEditItem] = useState<PromptTemplate | null>(null)
  const [viewItem, setViewItem] = useState<PromptTemplate | null>(null)
  const [saving, setSaving] = useState(false)

  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [version, setVersion] = useState('1.0')
  const [tags, setTags] = useState('')
  const [isActive, setIsActive] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getPromptTemplates()
      setTemplates(res.data.items || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const openCreate = () => {
    setEditItem(null)
    setName('')
    setContent('')
    setVersion('1.0')
    setTags('')
    setIsActive(true)
    setDialogOpen(true)
  }

  const openEdit = (item: PromptTemplate) => {
    setEditItem(item)
    setName(item.name)
    setContent(item.content)
    setVersion(item.version)
    setTags(item.tags || '')
    setIsActive(item.is_active)
    setDialogOpen(true)
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
        await updatePromptTemplate(editItem.id, data)
        toast.success('更新成功')
      } else {
        await createPromptTemplate(data)
        toast.success('创建成功')
      }
      setDialogOpen(false)
      fetchData()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '操作失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确认删除此提示词模板？')) return
    try {
      await deletePromptTemplate(id)
      toast.success('删除成功')
      fetchData()
    } catch {
      toast.error('删除失败')
    }
  }

  const formatDate = (d: string) => d?.slice(0, 16).replace('T', ' ') || '-'

  return (
    <div className="h-full flex overflow-hidden relative">
      <div className="flex-1 flex flex-col min-w-0">
        <div className="px-8 py-6 border-b flex items-center justify-between shrink-0">
          <h2 className="text-lg font-semibold">系统提示词模板</h2>
          <Button onClick={openCreate}>新建模板</Button>
        </div>

        <div className="flex-1 overflow-auto px-8 py-6">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>版本</TableHead>
                <TableHead>标签</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>更新时间</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
              ) : templates.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无模板</TableCell></TableRow>
              ) : templates.map((t) => (
                <TableRow key={t.id} className="cursor-pointer" onClick={() => setViewItem(t)}>
                  <TableCell className="font-medium">{t.name}</TableCell>
                  <TableCell>{t.version}</TableCell>
                  <TableCell>
                    <div className="flex gap-1 flex-wrap">
                      {t.tags?.split(',').filter(Boolean).map((tag, i) => (
                        <Badge key={i} variant="secondary" className="text-xs">{tag.trim()}</Badge>
                      )) || '-'}
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={t.is_active ? 'success' : 'secondary'}>{t.is_active ? '启用' : '禁用'}</Badge>
                  </TableCell>
                  <TableCell>{formatDate(t.updated_at)}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-3">
                      <Button variant="link" className="h-auto p-0 font-normal" onClick={(e) => { e.stopPropagation(); openEdit(t); }}>编辑</Button>
                      <Button variant="link" className="h-auto p-0 font-normal text-destructive hover:text-destructive/80" onClick={(e) => { e.stopPropagation(); handleDelete(t.id); }}>删除</Button>
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
              <DialogTitle>{editItem ? '编辑模板' : '新建模板'}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div className="space-y-1">
                <Label>名称 <span className="text-destructive">*</span></Label>
                <Input value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label>提示词内容 <span className="text-destructive">*</span></Label>
                <Textarea value={content} onChange={(e) => setContent(e.target.value)} rows={12} className="font-mono text-sm" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label>版本</Label>
                  <Input value={version} onChange={(e) => setVersion(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label>标签（逗号分隔）</Label>
                  <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="如 相关性评估, 默认模板" />
                </div>
              </div>
              <div className="flex items-center gap-2">
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
            </DetailSection>
            <DetailSection label="内容">
              <pre className="border rounded-md p-4 text-sm whitespace-pre-wrap font-mono bg-muted/30 max-h-[60vh] overflow-y-auto">
                {viewItem.content}
              </pre>
            </DetailSection>
          </>
        )}
      </DetailPanel>
    </div>
  )
}
