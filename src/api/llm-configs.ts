import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
import type { LlmConfig, PaginatedResponse } from '@/types'

export const getLlmConfigs = withCache(
  (params = {}) => http.get<PaginatedResponse<LlmConfig>>('/llm-configs', { params }),
  (params = {}) => `llm-configs:list:${JSON.stringify(params)}`
)

export function invalidateLlmConfigsCache() {
  clearCache('llm-configs:')
}

export function createLlmConfig(data: Partial<LlmConfig>) {
  return http.post<LlmConfig>('/llm-configs', data)
}

export function updateLlmConfig(id: number, data: Partial<LlmConfig>) {
  return http.put<LlmConfig>(`/llm-configs/${id}`, data)
}

export function deleteLlmConfig(id: number) {
  return http.delete(`/llm-configs/${id}`)
}

export function testLlmConfig(data: { model_name: string; api_endpoint: string; api_key: string }) {
  return http.post('/llm-configs/test', data)
}

export function testLlmConfigById(id: number) {
  return http.post(`/llm-configs/${id}/test`)
}
