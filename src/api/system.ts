import http from '@/lib/http'
import type { SystemConfig } from '@/types'

export function getSystemConfigs() {
  return http.get<SystemConfig[]>('/system/configs')
}

export function updateSystemConfig(key: string, value: string) {
  return http.put(`/system/configs/${key}`, { value })
}

export function getSystemStats() {
  return http.get('/system/stats')
}
