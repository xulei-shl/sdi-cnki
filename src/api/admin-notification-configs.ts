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
  email_enabled: boolean
  email_to: string | null
  module_flags: string | null
  email_module_flags: string | null
  updated_at: string | null
}

export const getAllNotificationConfigs = withCache(
  () => http.get<{ items: UserNotificationConfigItem[]; total: number }>('/admin/user-notification-configs'),
  () => 'admin:notification-configs'
)

export function invalidateNotificationConfigsCache() {
  clearCache('admin:')
}