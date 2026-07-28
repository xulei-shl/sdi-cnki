import http from '@/lib/http'
import { withCache, clearCache } from '@/lib/cache'
import type { SystemPrompt, PaginatedResponse } from '@/types'

export const getSystemPrompts = withCache(
  (params = {}) => http.get<PaginatedResponse<SystemPrompt>>('/system-prompts', { params }),
  (params = {}) => {
    const user = JSON.parse(localStorage.getItem('user') || '{}')
    return `system-prompts:list:${user.id}:${JSON.stringify(params)}`
  }
)

export function invalidateSystemPromptsCache() {
  clearCache('system-prompts:')
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
