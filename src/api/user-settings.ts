import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'

export interface NotificationConfig {
  webhook_url: string | null
  enabled: boolean
  email_enabled: boolean
  email_to: string | null
  module_flags: string | null
  email_module_flags: string | null
}

export const getNotificationConfig = withCache(
  () => http.get<NotificationConfig>('/user/notification-config'),
  () => {
    const user = JSON.parse(localStorage.getItem('user') || '{}')
    return `user:notification-config:${user.id}`
  }
)

export function invalidateNotificationConfigCache() {
  clearCache('user:')
}

export function updateNotificationConfig(data: Partial<NotificationConfig>) {
  return http.put<NotificationConfig>('/user/notification-config', data)
}

export function testNotificationWebhook(webhook_url: string) {
  return http.post('/user/notification-config/test', { webhook_url })
}

export function testEmailNotification(email_to: string) {
  return http.post('/user/notification-config/test-email', { email_to })
}