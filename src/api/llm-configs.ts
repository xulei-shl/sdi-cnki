import http from '@/lib/http'
import type { LlmConfig } from '@/types'

export function getLlmConfigs() {
  return http.get<LlmConfig[]>('/llm-configs')
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
