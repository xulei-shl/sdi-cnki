import http from '@/lib/http'
import type { SystemPrompt, PaginatedResponse } from '@/types'

export function getSystemPrompts(params = {}) {
  return http.get<PaginatedResponse<SystemPrompt>>('/system-prompts', { params })
}

export function createSystemPrompt(data: Partial<SystemPrompt>) {
  return http.post<SystemPrompt>('/system-prompts', data)
}

export function updateSystemPrompt(id: number, data: Partial<SystemPrompt>) {
  return http.put<SystemPrompt>(`/system-prompts/${id}`, data)
}

export function deleteSystemPrompt(id: number) {
  return http.delete(`/system-prompts/${id}`)
}
