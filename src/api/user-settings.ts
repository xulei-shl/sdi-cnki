import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'

export const getNotificationConfig = withCache(
  () => http.get<{ webhook_url: string | null; enabled: boolean }>('/user/notification-config'),
  () => {
    const user = JSON.parse(localStorage.getItem('user') || '{}')
    return `user:notification-config:${user.id}`
  }
)

export function invalidateNotificationConfigCache() {
  clearCache('user:')
}

export function updateNotificationConfig(data: { webhook_url?: string | null; enabled?: boolean }) {
  return http.put<{ webhook_url: string | null; enabled: boolean }>('/user/notification-config', data)
}

export function testNotificationWebhook(webhook_url: string) {
  return http.post('/user/notification-config/test', { webhook_url })
}
