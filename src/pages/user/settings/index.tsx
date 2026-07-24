import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { toast } from 'sonner'
import { getNotificationConfig, updateNotificationConfig, testNotificationWebhook } from '@/api/user-settings'

export default function UserSettingsPage() {
  const [webhookUrl, setWebhookUrl] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await getNotificationConfig()
      setWebhookUrl(res.data.webhook_url ?? '')
      setEnabled(res.data.enabled)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchConfig() }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateNotificationConfig({
        webhook_url: webhookUrl.trim() || null,
        enabled,
      })
      toast.success('保存成功')
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleTest = async () => {
    if (!webhookUrl.trim()) {
      toast.error('请先输入 Webhook URL')
      return
    }
    setTesting(true)
    try {
      await testNotificationWebhook(webhookUrl.trim())
      toast.success('测试通知发送成功')
    } catch {
      toast.error('测试发送失败')
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6 h-full flex items-center justify-center text-muted-foreground">
        加载中...
      </div>
    )
  }

  return (
    <div className="p-6 h-full flex flex-col max-w-2xl">
      <h2 className="text-lg font-semibold mb-6">通知设置</h2>

      <Card className="bg-transparent shadow-none">
        <CardHeader className="px-0">
          <CardTitle>企业微信通知</CardTitle>
          <CardDescription>任务执行完成或失败时发送通知到企业微信群</CardDescription>
        </CardHeader>
        <CardContent className="px-0 space-y-6">
          <div className="flex items-center space-x-3">
            <Checkbox
              id="wechat-notification"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            <label
              htmlFor="wechat-notification"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              启用企业微信通知
            </label>
          </div>

          {enabled && (
            <div className="space-y-2 pl-7">
              <label className="text-sm font-medium">企业微信 Webhook URL</label>
              <Input
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                在群机器人中添加 Webhook 后复制地址到此
              </p>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? '保存中...' : '保存'}
            </Button>
            <Button variant="outline" onClick={handleTest} disabled={testing || !webhookUrl.trim()}>
              {testing ? '发送中...' : '测试'}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
