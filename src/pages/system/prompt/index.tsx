import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { getSystemPrompts, createSystemPrompt, updateSystemPrompt, deleteSystemPrompt } from '@/api/system-prompts'
import type { SystemPrompt } from '@/types'

export default function PromptPage() {
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

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getSystemPrompts()
      setPrompts(res.data.items || [])
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

  const openEdit = (item: SystemPrompt) => {
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
        await updateSystemPrompt(editItem.id, data)
        toast.success('更新成功')
      } else {
        await createSystemPrompt(data)
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
    if (!confirm('确认删除此提示词？')) return
    try {
      await deleteSystemPrompt(id)
      toast.success('删除成功')
      fetchData()
    } catch {
      toast.error('删除失败')
    }
  }

  const formatDate = (d: string) => d?.slice(0, 16).replace('T', ' ') || '-'

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">提示词管理</h2>
        <Button onClick={openCreate}>新建提示词</Button>
      </div>

      <div className="flex-1 overflow-auto">
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
            ) : prompts.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无提示词</TableCell></TableRow>
            ) : prompts.map((p) => (
              <TableRow key={p.id}>
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell>{p.version}</TableCell>
                <TableCell>
                  <div className="flex gap-1 flex-wrap">
                    {p.tags?.split(',').filter(Boolean).map((tag, i) => (
                      <Badge key={i} variant="secondary" className="text-xs">{tag.trim()}</Badge>
                    )) || '-'}
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={p.is_active ? 'success' : 'secondary'}>{p.is_active ? '启用' : '禁用'}</Badge>
                </TableCell>
                <TableCell>{formatDate(p.updated_at)}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    <Button variant="ghost" size="sm" onClick={() => setViewItem(p)}>查看</Button>
                    <Button variant="ghost" size="sm" onClick={() => openEdit(p)}>编辑</Button>
                    <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleDelete(p.id)}>删除</Button>
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

      {/* View Dialog */}
      <Dialog open={!!viewItem} onOpenChange={(o) => { if (!o) setViewItem(null) }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{viewItem?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex gap-2 text-sm text-muted-foreground">
              <span>版本: {viewItem?.version}</span>
              <span>|</span>
              <span>状态: {viewItem?.is_active ? '启用' : '禁用'}</span>
              {viewItem?.tags && (
                <>
                  <span>|</span>
                  <span>标签: {viewItem.tags}</span>
                </>
              )}
            </div>
            <pre className="border rounded-md p-4 text-sm whitespace-pre-wrap font-mono bg-muted/30 max-h-96 overflow-y-auto">
              {viewItem?.content}
            </pre>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
