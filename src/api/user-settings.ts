import http from '@/lib/http'

export function getNotificationConfig() {
  return http.get<{ webhook_url: string | null; enabled: boolean }>('/user/notification-config')
}

export function updateNotificationConfig(data: { webhook_url?: string | null; enabled?: boolean }) {
  return http.put<{ webhook_url: string | null; enabled: boolean }>('/user/notification-config', data)
}

export function testNotificationWebhook(webhook_url: string) {
  return http.post('/user/notification-config/test', { webhook_url })
}
