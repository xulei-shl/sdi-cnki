import http from '@/lib/http'
import type { SystemConfig } from '@/types'

export function getSystemConfigs() {
  return http.get<{ items: SystemConfig[] }>('/system/configs')
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
