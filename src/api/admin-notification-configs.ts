import http from '@/lib/http'

export interface UserNotificationConfigItem {
  user_id: number
  username: string
  email: string | null
  role: string
  is_active: boolean
  webhook_url: string | null
  enabled: boolean
  updated_at: string | null
}

export function getAllNotificationConfigs() {
  return http.get<{ items: UserNotificationConfigItem[]; total: number }>('/admin/user-notification-configs')
}
