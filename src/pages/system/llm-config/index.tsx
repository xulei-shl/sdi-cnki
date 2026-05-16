import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { toast } from 'sonner'
import { getLlmConfigs, createLlmConfig, updateLlmConfig, deleteLlmConfig, testLlmConfig, testLlmConfigById } from '@/api/llm-configs'
import type { LlmConfig } from '@/types'

export default function LlmConfigPage() {
  const [configs, setConfigs] = useState<LlmConfig[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editItem, setEditItem] = useState<LlmConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testingId, setTestingId] = useState<number | null>(null)

  const [name, setName] = useState('')
  const [modelName, setModelName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiEndpoint, setApiEndpoint] = useState('')
  const [isActive, setIsActive] = useState(true)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getLlmConfigs()
      setConfigs(res.data.items || [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const openCreate = () => {
    setEditItem(null)
    setName('')
    setModelName('')
    setApiKey('')
    setApiEndpoint('')
    setIsActive(true)
    setDialogOpen(true)
  }

  const openEdit = (item: LlmConfig) => {
    setEditItem(item)
    setName(item.name)
    setModelName(item.model_name)
    setApiKey('')
    setApiEndpoint(item.api_endpoint)
    setIsActive(item.is_active)
    setDialogOpen(true)
  }

  const handleSave = async () => {
    if (!name.trim()) { toast.error('请输入名称'); return }
    if (!modelName.trim()) { toast.error('请输入模型名称'); return }
    setSaving(true)
    try {
      const data: any = {
        name: name.trim(),
        model_name: modelName.trim(),
        api_endpoint: apiEndpoint.trim(),
        is_active: isActive,
      }
      if (apiKey) data.api_key = apiKey

      if (editItem) {
        await updateLlmConfig(editItem.id, data)
        toast.success('更新成功')
      } else {
        await createLlmConfig(data)
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
    if (!confirm('确认删除此配置？')) return
    try {
      await deleteLlmConfig(id)
      toast.success('删除成功')
      fetchData()
    } catch {
      toast.error('删除失败')
    }
  }

  const handleTestDialog = async () => {
    if (!apiEndpoint.trim()) { toast.error('请输入 API 端点'); return }
    if (!modelName.trim()) { toast.error('请输入模型名称'); return }
    setTesting(true)
    try {
      if (editItem) {
        await testLlmConfigById(editItem.id)
      } else {
        if (!apiKey.trim()) { toast.error('请输入 API Key'); setTesting(false); return }
        await testLlmConfig({
          model_name: modelName.trim(),
          api_endpoint: apiEndpoint.trim(),
          api_key: apiKey,
        })
      }
      toast.success('连接成功')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '连接测试失败')
    } finally {
      setTesting(false)
    }
  }

  const handleTestById = async (id: number) => {
    setTestingId(id)
    try {
      await testLlmConfigById(id)
      toast.success('连接成功')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '连接测试失败')
    } finally {
      setTestingId(null)
    }
  }

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">大模型管理</h2>
        <Button onClick={openCreate}>新建配置</Button>
      </div>

      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>名称</TableHead>
              <TableHead>模型名称</TableHead>
              <TableHead>API 端点</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
            ) : configs.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无配置</TableCell></TableRow>
            ) : configs.map((cfg) => (
              <TableRow key={cfg.id}>
                <TableCell className="font-medium">{cfg.name}</TableCell>
                <TableCell>{cfg.model_name}</TableCell>
                <TableCell className="max-w-[200px] truncate text-muted-foreground">{cfg.api_endpoint}</TableCell>
                <TableCell>
                  <Badge variant={cfg.is_active ? 'success' : 'secondary'}>
                    {cfg.is_active ? '启用' : '禁用'}
                  </Badge>
                </TableCell>
                <TableCell>{cfg.created_at?.slice(0, 16).replace('T', ' ') || '-'}</TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-3">
                    <Button variant="link" className="h-auto p-0 font-normal" onClick={() => handleTestById(cfg.id)} disabled={testingId === cfg.id}>{testingId === cfg.id ? '测试中' : '测试'}</Button>
                    <Button variant="link" className="h-auto p-0 font-normal" onClick={() => openEdit(cfg)}>编辑</Button>
                    <Button variant="link" className="h-auto p-0 font-normal text-destructive hover:text-destructive/80" onClick={() => handleDelete(cfg.id)}>删除</Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editItem ? '编辑配置' : '新建配置'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1">
              <Label>名称 <span className="text-destructive">*</span></Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 GPT-4o" />
            </div>
            <div className="space-y-1">
              <Label>模型名称 <span className="text-destructive">*</span></Label>
              <Input value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="如 gpt-4o" />
            </div>
            <div className="space-y-1">
              <Label>API Key {!editItem && <span className="text-destructive">*</span>}</Label>
              <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder={editItem ? '留空不修改' : ''} />
            </div>
            <div className="space-y-1">
              <Label>API 端点 <span className="text-destructive">*</span></Label>
              <Input value={apiEndpoint} onChange={(e) => setApiEndpoint(e.target.value)} placeholder="https://api.openai.com/v1" />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={isActive} onChange={(e) => setIsActive(e.target.checked)} />
              <Label>启用</Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>取消</Button>
            <Button variant="outline" onClick={handleTestDialog} disabled={testing}>{testing ? '测试中...' : '测试连接'}</Button>
            <Button onClick={handleSave} disabled={saving}>{saving ? '保存中...' : '保存'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
