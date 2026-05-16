import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { toast } from 'sonner'
import { getSystemConfigs, updateSystemConfig } from '@/api/system'

interface ConfigEntry {
  key: string
  value: string
  description: string
  updated_by: number
  updated_at: string
}

export default function SystemConfigPage() {
  const [configs, setConfigs] = useState<ConfigEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<Record<string, string>>({})
  const [filterKey, setFilterKey] = useState('')

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getSystemConfigs()
      const items = res.data?.items ?? []
      setConfigs(items)
      const editMap: Record<string, string> = {}
      items.forEach((c: ConfigEntry) => { editMap[c.key] = c.value })
      setEditing(editMap)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const filteredConfigs = filterKey
    ? configs.filter(c => c.key.toLowerCase().includes(filterKey.toLowerCase()))
    : configs

  const handleSave = async (key: string) => {
    try {
      await updateSystemConfig(key, editing[key])
      toast.success('保存成功')
      fetchData()
    } catch {
      toast.error('保存失败')
    }
  }

  const formatDate = (d: string) => d?.slice(0, 16).replace('T', ' ') || '-'

  const configLabels: Record<string, string> = {
    webhook_enterprise_wechat: '企业微信 Webhook URL',
    cnki_search_timeout: 'CNKI 检索超时（秒）',
    llm_analysis_batch_size: 'LLM 分析并发数',
    cnki_queue_concurrency: 'CNKI 队列并发数',
    llm_queue_concurrency: 'LLM 队列并发数',
    download_queue_concurrency: '下载队列并发数',
    export_queue_concurrency: '导出队列并发数',
  }

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">系统配置</h2>
        <Input
          placeholder="搜索配置项..."
          value={filterKey}
          onChange={(e) => setFilterKey(e.target.value)}
          className="max-w-xs"
        />
      </div>

      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>配置项</TableHead>
              <TableHead>当前值</TableHead>
              <TableHead>最后更新</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
            ) : filteredConfigs.length === 0 ? (
              <TableRow><TableCell colSpan={4} className="text-center py-8 text-muted-foreground">暂无配置</TableCell></TableRow>
            ) : filteredConfigs.map((cfg) => (
              <TableRow key={cfg.key}>
                <TableCell>
                  <div className="text-sm font-medium">{configLabels[cfg.key] || cfg.key}</div>
                  <div className="text-xs text-muted-foreground">{cfg.description}</div>
                </TableCell>
                <TableCell>
                  <Input
                    value={editing[cfg.key] || ''}
                    onChange={(e) => setEditing(prev => ({ ...prev, [cfg.key]: e.target.value }))}
                    className="min-w-[300px]"
                  />
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {formatDate(cfg.updated_at)}
                </TableCell>
                <TableCell className="text-right">
                  <Button size="sm" onClick={() => handleSave(cfg.key)}>保存</Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
