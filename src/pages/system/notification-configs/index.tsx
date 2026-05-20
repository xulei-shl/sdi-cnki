import { useState, useEffect } from 'react'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { getAllNotificationConfigs, UserNotificationConfigItem } from '@/api/admin-notification-configs'

export default function AdminNotificationConfigsPage() {
  const [items, setItems] = useState<UserNotificationConfigItem[]>([])
  const [loading, setLoading] = useState(false)

  const fetchData = async () => {
    setLoading(true)
    try {
      const res = await getAllNotificationConfigs()
      setItems(res.data?.items ?? [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  const formatDate = (d: string | null) => d?.slice(0, 16).replace('T', ' ') || '-'

  const statusBadge = (item: UserNotificationConfigItem) => {
    if (!item.webhook_url) {
      return <Badge variant="secondary">未配置</Badge>
    }
    return item.enabled
      ? <Badge className="bg-green-100 text-green-700 hover:bg-green-100">已启用</Badge>
      : <Badge variant="outline">已关闭</Badge>
  }

  return (
    <div className="p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">通知配置</h2>
      </div>

      <div className="flex-1 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>用户名</TableHead>
              <TableHead>邮箱</TableHead>
              <TableHead>角色</TableHead>
              <TableHead>Webhook URL</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>最后更新</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">加载中...</TableCell></TableRow>
            ) : items.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无数据</TableCell></TableRow>
            ) : items.map((item) => (
              <TableRow key={item.user_id}>
                <TableCell>
                  <div className="text-sm font-medium">{item.username}</div>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{item.email || '-'}</TableCell>
                <TableCell>
                  <Badge variant={item.role === 'admin' ? 'default' : 'secondary'} className="text-xs">
                    {item.role === 'admin' ? 'Admin' : 'User'}
                  </Badge>
                </TableCell>
                <TableCell className="max-w-[300px]">
                  <div className="text-sm truncate font-mono" title={item.webhook_url || ''}>
                    {item.webhook_url || '-'}
                  </div>
                </TableCell>
                <TableCell>{statusBadge(item)}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{formatDate(item.updated_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
