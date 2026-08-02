import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { MessageSquare, Mail, Play } from 'lucide-react'
import { toast } from 'sonner'
import { getNotificationConfig, updateNotificationConfig, testNotificationWebhook, testEmailNotification } from '@/api/user-settings'
import type { NotificationConfig } from '@/api/user-settings'

interface StageDef {
  key: string
  label: string
  moduleKey: string
}

const STAGES: StageDef[] = [
  { key: 'search', label: '检索', moduleKey: '检索' },
  { key: 'analysis', label: '分析', moduleKey: '分析' },
  { key: 'download', label: '下载', moduleKey: '下载' },
]

function parseFlags(raw: string | null): Record<string, boolean> {
  if (!raw) return {}
  try { return JSON.parse(raw) } catch { return {} }
}

function serializeFlags(flags: Record<string, boolean>): string {
  const hasAny = Object.values(flags).some(Boolean)
  if (!hasAny) return ''
  return JSON.stringify(flags)
}

export default function UserSettingsPage() {
  const [config, setConfig] = useState<NotificationConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testingWebhook, setTestingWebhook] = useState(false)
  const [testingEmail, setTestingEmail] = useState(false)

  const [webhookUrl, setWebhookUrl] = useState('')
  const [wechatEnabled, setWechatEnabled] = useState(false)
  const [moduleFlags, setModuleFlags] = useState<Record<string, boolean>>({})

  const [emailEnabled, setEmailEnabled] = useState(false)
  const [emailTo, setEmailTo] = useState('')
  const [emailModuleFlags, setEmailModuleFlags] = useState<Record<string, boolean>>({})

  const fetchConfig = async () => {
    setLoading(true)
    try {
      const res = await getNotificationConfig()
      const data = res.data
      setConfig(data)
      setWebhookUrl(data.webhook_url ?? '')
      setWechatEnabled(data.enabled)
      setModuleFlags(parseFlags(data.module_flags))
      setEmailEnabled(data.email_enabled)
      setEmailTo(data.email_to ?? '')
      setEmailModuleFlags(parseFlags(data.email_module_flags))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchConfig() }, [])

  const handleSaveWechat = async () => {
    setSaving(true)
    try {
      const res = await updateNotificationConfig({
        webhook_url: webhookUrl.trim() || null,
        enabled: wechatEnabled,
        module_flags: serializeFlags(moduleFlags),
      })
      setConfig(res.data)
      toast.success('企微通知保存成功')
    } catch { toast.error('保存失败') }
    finally { setSaving(false) }
  }

  const handleSaveEmail = async () => {
    setSaving(true)
    try {
      const res = await updateNotificationConfig({
        email_enabled: emailEnabled,
        email_to: emailTo.trim() || null,
        email_module_flags: serializeFlags(emailModuleFlags),
      })
      setConfig(res.data)
      toast.success('邮件通知保存成功')
    } catch { toast.error('保存失败') }
    finally { setSaving(false) }
  }

  const handleTestWebhook = async () => {
    if (!webhookUrl.trim()) { toast.error('请先输入 Webhook URL'); return }
    setTestingWebhook(true)
    try { await testNotificationWebhook(webhookUrl.trim()); toast.success('测试通知发送成功') }
    catch { toast.error('测试发送失败') }
    finally { setTestingWebhook(false) }
  }

  const handleTestEmail = async () => {
    const email = emailTo.trim()
    if (!email) { toast.error('请先输入邮箱地址'); return }
    setTestingEmail(true)
    try { await testEmailNotification(email); toast.success('测试邮件发送成功') }
    catch { toast.error('测试发送失败') }
    finally { setTestingEmail(false) }
  }

  const toggleModuleFlag = (stageKey: string, channel: 'wechat' | 'email') => {
    if (channel === 'wechat') {
      setModuleFlags((prev) => ({ ...prev, [stageKey]: !prev[stageKey] }))
    } else {
      setEmailModuleFlags((prev) => ({ ...prev, [stageKey]: !prev[stageKey] }))
    }
  }

  const handleSaveModules = async () => {
    setSaving(true)
    try {
      const res = await updateNotificationConfig({
        module_flags: serializeFlags(moduleFlags),
        email_module_flags: serializeFlags(emailModuleFlags),
      })
      setConfig(res.data)
      toast.success('模块通知配置保存成功')
    } catch { toast.error('保存失败') }
    finally { setSaving(false) }
  }

  if (loading) {
    return <div className="p-6 h-full flex items-center justify-center text-muted-foreground">加载中...</div>
  }

  return (
    <div className="p-6 h-full flex flex-col gap-6 overflow-auto">
      {/* 通知渠道配置 — 左右双卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* 企业微信 */}
        <div className="rounded-lg border bg-muted/10 p-5 space-y-4">
          <div className="flex items-center gap-2 text-base font-semibold text-foreground">
            <MessageSquare className="h-5 w-5 text-primary" />
            企业微信
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-muted-foreground">Webhook URL</label>
            <Input
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
              placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."
              className="font-mono text-sm"
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-2.5">
              <Switch
                checked={wechatEnabled}
                onChange={(e) => setWechatEnabled(e.target.checked)}
                className="h-[20px] w-[36px]"
              />
              <span className="text-sm">启用企业微信通知</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestWebhook}
              disabled={testingWebhook || !webhookUrl.trim()}
            >
              <Play className="h-3.5 w-3.5 mr-1.5" />
              测试
            </Button>
          </div>
        </div>

        {/* 邮件 */}
        <div className="rounded-lg border bg-muted/10 p-5 space-y-4">
          <div className="flex items-center gap-2 text-base font-semibold text-foreground">
            <Mail className="h-5 w-5 text-primary" />
            邮件
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium text-muted-foreground">收件邮箱</label>
            <Input
              value={emailTo}
              onChange={(e) => setEmailTo(e.target.value)}
              placeholder="your@email.com"
              className="font-mono text-sm"
              type="email"
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="flex items-center gap-2.5">
              <Switch
                checked={emailEnabled}
                onChange={(e) => setEmailEnabled(e.target.checked)}
                className="h-[20px] w-[36px]"
              />
              <span className="text-sm">启用邮件通知</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestEmail}
              disabled={testingEmail || !emailTo.trim()}
            >
              <Play className="h-3.5 w-3.5 mr-1.5" />
              测试
            </Button>
          </div>
        </div>
      </div>

      {/* 模块通知配置 */}
      <div className="rounded-lg border bg-muted/10">
        <div className="flex items-center justify-between px-5 pt-4 pb-2">
          <h3 className="text-base font-semibold text-foreground">模块通知配置</h3>
          <span className="text-xs text-muted-foreground">
            独立控制每个模块在微信和邮件渠道的推送开关
          </span>
        </div>

        <div className="px-5 pb-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>模块名称</TableHead>
                <TableHead>路径</TableHead>
                <TableHead className="text-center">
                  <span className="inline-flex items-center gap-1.5">
                    <MessageSquare className="h-4 w-4 text-primary" />
                    企业微信
                  </span>
                </TableHead>
                <TableHead className="text-center">
                  <span className="inline-flex items-center gap-1.5">
                    <Mail className="h-4 w-4 text-primary" />
                    邮件
                  </span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {STAGES.map((stage) => (
                <TableRow key={stage.key}>
                  <TableCell className="font-medium text-foreground">{stage.label}</TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">{stage.key}</TableCell>
                  <TableCell className="text-center">
                    <Switch
                      checked={!!moduleFlags[stage.moduleKey]}
                      onChange={() => toggleModuleFlag(stage.moduleKey, 'wechat')}
                      className="h-[18px] w-[32px]"
                    />
                  </TableCell>
                  <TableCell className="text-center">
                    <Switch
                      checked={!!emailModuleFlags[stage.moduleKey]}
                      onChange={() => toggleModuleFlag(stage.moduleKey, 'email')}
                      className="h-[18px] w-[32px]"
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="flex justify-end mt-3">
            <Button
              onClick={handleSaveModules}
              disabled={saving}
              size="sm"
            >
              {saving ? '保存中...' : '保存'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}