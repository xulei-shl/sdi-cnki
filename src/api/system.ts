import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
import type { SystemConfig } from '@/types'

export const getSystemConfigs = withCache(
  () => http.get<{ items: SystemConfig[] }>('/system/configs'),
  () => 'system:configs'
)

export function invalidateSystemConfigsCache() {
  clearCache('system:')
}

export function updateSystemConfig(key: string, value: string) {
  return http.put(`/system/configs/${key}`, { value })
}

export function testWebhookConfig(key: string, value: string) {
  return http.post(`/system/configs/${key}/test`, { value })
}

export function getSystemStats() {
  return http.get('/system/stats')
}
