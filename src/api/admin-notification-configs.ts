import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'

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

export const getAllNotificationConfigs = withCache(
  () => http.get<{ items: UserNotificationConfigItem[]; total: number }>('/admin/user-notification-configs'),
  () => 'admin:notification-configs'
)

export function invalidateNotificationConfigsCache() {
  clearCache('admin:')
}
